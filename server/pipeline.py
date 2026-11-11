"""Speech to English text: Silero VAD cuts speech at pauses, Parakeet v3 recognises each
piece, and a quickmt (CTranslate2) pack translates it. Models are loaded from the paths in
config.json; see config.example.json."""
import json
import os
import re
import time
from collections import deque

import ctranslate2
import numpy as np
import sentencepiece as spm
import sherpa_onnx
import soxr

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET_RATE = 16000
VAD_WINDOW = 512
HISTORY_SECONDS = 40

_ES_WORDS = set(
    "el la los las de del que y en un una es no por con para se lo como más pero su al me te mi "
    "qué está estoy eres son muy ya sí porque cuando donde también hay esto eso nos le les".split()
)
_EN_WORDS = set(
    "the and is are you to of it that in for on with this was have not but be at he she we they "
    "what do does did my your".split()
)
# Polish: letters that exist in no other language this program handles, plus very common words
# ("to", "no" and "co" are left out because English and Spanish use them too).
_PL_LETTERS = "ąćęłńśźż"
_PL_WORDS = set(
    "nie jest się na że do jak ale tak już czy dla ten tego jestem jesteś są był była było być "
    "bardzo tylko może mnie ciebie jego jej nas was ich tutaj teraz dlaczego dobrze dziękuję proszę "
    "przepraszam tam wiem chcę mam masz mamy".split()
)


def load_config(path=None):
    # utf-8-sig also accepts files saved with a hidden byte-order mark (some editors add one)
    with open(path or os.path.join(HERE, "config.json"), encoding="utf-8-sig") as f:
        return json.load(f)


def _abs(path):
    return path if os.path.isabs(path) else os.path.join(HERE, path)


_UKRAINIAN_LETTERS = re.compile("[іїєґІЇЄҐ]")


def is_cyrillic(text):
    letters = [ch for ch in text if ch.isalpha()]
    return sum(1 for ch in letters if "Ѐ" <= ch <= "ӿ") > len(letters) / 2


def guess_language(text, latin_default="es"):
    """Cyrillic text -> 'ru'. Latin text -> 'pl', 'es' or 'en' by common words and letters
    (latin_default on a tie)."""
    if is_cyrillic(text):
        return "ru"
    lowered = text.lower()
    words = re.findall(r"[^\W\d_]+", lowered)
    scores = {  # order matters: on a tie with no default among the leaders, the first one wins
        "pl": sum(w in _PL_WORDS for w in words) + 2 * sum(ch in _PL_LETTERS for ch in lowered),
        "es": sum(w in _ES_WORDS for w in words) + 2 * sum(ch in "ñ¿¡" for ch in lowered),
        "en": sum(w in _EN_WORDS for w in words),
    }
    best = max(scores.values())
    leaders = [lang for lang, score in scores.items() if score == best]
    if best == 0 or len(leaders) > 1:
        return latin_default if latin_default in leaders or best == 0 else leaders[0]
    return leaders[0]


_FILLERS = {"mm", "mmm", "hm", "hmm", "mhm", "uh", "um", "eh", "ah", "oh", "ay", "ээ", "эм", "мм", "хм", "ам"}

# Web-page phrases the translation model invents when it is given a very short, unclear scrap
# of speech (seen in the log: 'Poubyć.' -> 'Skip to content'). Nobody says these on a video.
_BOILERPLATE = {"skip to content", "skip to main content"}


def sound_tag(text):
    """'[музыка]' / '(applause)' / '♪ ... ♪' -> the words inside; None if it is ordinary text."""
    stripped = text.strip()
    m = re.fullmatch(r"[\[\(\*]\s*(.+?)\s*[\]\)\*]\.?", stripped)
    if m:
        return m.group(1)
    if "♪" in stripped:
        return "music"
    return None


def is_filler(text):
    stripped = text.strip()
    # Whisper writes sound descriptions such as "[музыка]" or "(applause)" for non-speech.
    if re.fullmatch(r"[\[\(\*♪].*[\]\)\*♪]\.?", stripped) or "♪" in stripped:
        return True
    words = re.findall(r"[^\W\d_]+", stripped.lower())
    return not words or all(w in _FILLERS for w in words)


def collapse_repeats(text):
    """'Yes yes yes yes yes' or 'Come on, come on, come on.' (a translation glitch on very short
    audio) -> 'Yes' / 'Come on.'  A word or a phrase of up to 4 words repeated 3+ times in a row
    is cut to one copy; the sentence's closing punctuation is kept."""
    def key(word):
        return re.sub(r"\W+", "", word.lower())

    words = text.split()
    for size in (1, 2, 3, 4):
        out = []
        i = 0
        while i < len(words):
            group_key = [key(w) for w in words[i : i + size]]
            run = 1
            while (
                len(group_key) == size
                and i + (run + 1) * size <= len(words)
                and [key(w) for w in words[i + run * size : i + (run + 1) * size]] == group_key
            ):
                run += 1
            if run >= 3 and size <= len(words) - i:
                group = words[i : i + size]
                closing = re.search(r"[^\w]+$", words[i + run * size - 1])
                group[-1] = re.sub(r"[^\w]+$", "", group[-1]) + (closing.group(0) if closing else "")
                out.extend(group)
                i += run * size
            else:
                out.append(words[i])
                i += 1
        words = out
    return " ".join(words)


def is_looping(text):
    """True when a speech model has got stuck repeating itself ('estar aquí, estar aquí, estar
    aquí...' or 'no no no no no no'): a word 5+ times in a row, or a 2-4 word phrase 3+ times."""
    words = [re.sub(r"\W+", "", w.lower()) for w in text.split()]
    words = [w for w in words if w]
    for size, needed in ((1, 5), (2, 3), (3, 3), (4, 3)):
        for start in range(len(words) - size * needed + 1):
            chunk = words[start : start + size]
            if all(words[start + k * size : start + (k + 1) * size] == chunk for k in range(1, needed)):
                return True
    return False


def tidy_translation(source, english):
    """Removes repeated sentences, and the made-up extra sentences a translator sometimes
    adds after a very short fragment ('de París.' -> 'of Paris. I'm sorry to hear that.')."""
    sentences = re.split(r"(?<=[.!?])\s+", english.strip())
    kept = [s for i, s in enumerate(sentences) if i == 0 or s.lower() != sentences[i - 1].lower()]
    source_words = len(re.findall(r"[^\W\d_]+", source))
    if source_words <= 3 and len(kept) > 1 and len(" ".join(kept).split()) > 2 * source_words + 2:
        kept = kept[:1]
    return " ".join(kept)


class Translator:
    def __init__(self, model_dir, spm_dir, threads, beam_size):
        self.sp_src = spm.SentencePieceProcessor(model_file=os.path.join(_abs(spm_dir), "src.spm.model"))
        self.sp_tgt = spm.SentencePieceProcessor(model_file=os.path.join(_abs(spm_dir), "tgt.spm.model"))
        self.translator = ctranslate2.Translator(
            _abs(model_dir), device="cpu", compute_type="int8", inter_threads=1, intra_threads=threads
        )
        self.beam_size = beam_size

    def translate(self, text):
        # The end-of-sentence marker tells the model the sentence is over. Without it very
        # short fragments ("trabajadores.") often turn into invented sentences, but on full
        # sentences it can drop words (a Russian greeting lost "Good afternoon,"), so it is
        # only used for short fragments.
        tokens = self.sp_src.encode(text, out_type=str)
        if len(re.findall(r"[^\W\d_]+", text)) <= 3:
            tokens = tokens + ["</s>"]
        result = self.translator.translate_batch([tokens], beam_size=self.beam_size, max_decoding_length=256)
        return self.sp_tgt.decode(result[0].hypotheses[0])


class Stream:
    """One live audio stream: resamples to 16 kHz and cuts it into speech pieces.

    Pieces normally end at a pause (found by the voice detector). A speaker who never pauses,
    like a news reader, would otherwise produce one huge piece, so after `force_cut` seconds of
    unbroken speech the stream is cut at its quietest moment and the detector is restarted.
    All pieces are taken from a rolling history of the audio, so a piece that starts at a
    forced cut begins exactly where the previous one ended (nothing lost or repeated)."""

    def __init__(self, pipeline, sample_rate):
        self.pipeline = pipeline
        self.resampler = None
        if sample_rate != TARGET_RATE:
            self.resampler = soxr.ResampleStream(sample_rate, TARGET_RATE, 1, dtype="float32")
        self.vad = pipeline.make_vad()
        self.vad_offset = 0  # samples fed before the current detector was created
        self.fed = 0  # samples fed to the detectors so far
        self.carry = np.zeros(0, dtype=np.float32)
        self.history = np.zeros(0, dtype=np.float32)
        self.history_start = 0  # absolute index of history[0]
        self.received = 0  # 16 kHz samples received so far
        self.speech_began = None  # when the current unbroken stretch of speech started
        self.cut_at = None  # where the last forced cut happened
        self.loud_run = 0.0  # seconds of sound in a row with no speech (music, noise)
        self.no_speech_announced = False
        self.no_speech_event = False

    def take_no_speech_event(self):
        """True once when a long stretch of sound with no speech has been going on."""
        event, self.no_speech_event = self.no_speech_event, False
        return event

    def _watch_for_no_speech(self, samples):
        pipeline = self.pipeline
        if pipeline.no_speech_seconds <= 0:
            return
        level = float(np.sqrt(np.mean(samples**2)))
        if self.vad.is_speech_detected() or level < pipeline.sound_level:
            self.loud_run = 0.0
            self.no_speech_announced = False
            return
        self.loud_run += len(samples) / TARGET_RATE
        if self.loud_run >= pipeline.no_speech_seconds and not self.no_speech_announced:
            self.no_speech_announced = True
            self.no_speech_event = True

    def feed(self, samples):
        if self.resampler is not None:
            samples = self.resampler.resample_chunk(samples)
        if len(samples) == 0:
            return []
        self.received += len(samples)
        self.history = np.concatenate([self.history, samples])
        buf = np.concatenate([self.carry, samples])
        usable = (len(buf) // VAD_WINDOW) * VAD_WINDOW
        for i in range(0, usable, VAD_WINDOW):
            self.vad.accept_waveform(buf[i : i + VAD_WINDOW])
        self.fed += usable
        self.carry = buf[usable:]
        pieces = self._drain()
        pieces += self._force_cut()
        self._watch_for_no_speech(samples)
        max_history = HISTORY_SECONDS * TARGET_RATE
        if len(self.history) > max_history:
            cut = len(self.history) - max_history
            self.history = self.history[cut:]
            self.history_start += cut
        return pieces

    def flush(self):
        self.vad.flush()
        return self._drain()

    def _lead_in(self, start):
        """Where a piece that the detector says begins at `start` really starts."""
        if self.cut_at is not None and abs(start - self.cut_at) < TARGET_RATE:
            return self.cut_at  # continues straight on from a forced cut
        return start - self.pipeline.preroll  # normal: a little lead-in (detector fires late)

    def _slice(self, lo, hi):
        lo = max(lo, self.history_start)
        return self.history[lo - self.history_start : max(lo, hi) - self.history_start]

    def _drain(self):
        """Returns (speech, pause_wait_seconds) pairs; the wait is how long after the speech
        ended the voice detector decided the piece was complete."""
        pieces = []
        while not self.vad.empty():
            segment = self.vad.front
            start = segment.start + self.vad_offset
            end = start + len(segment.samples)
            self.vad.pop()
            speech = self._slice(self._lead_in(start), end)
            self.cut_at = None
            if len(speech) >= 1600:
                pieces.append((speech, max(0.0, (self.received - end) / TARGET_RATE)))
        return pieces

    def _force_cut(self):
        if not self.vad.is_speech_detected():
            self.speech_began = None
            return []
        if self.speech_began is None:
            self.speech_began = self.received
            return []
        if (self.received - self.speech_began) / TARGET_RATE < self.pipeline.force_cut:
            return []
        # Cut at the quietest 50 ms in the last `cut_search` seconds, so a word is unlikely to
        # be split (a shorter search means the caption is sent sooner after the cut).
        window, stride = 800, 400
        search_from = max(self.speech_began, self.received - int(self.pipeline.cut_search * TARGET_RATE))
        tail = self._slice(search_from, self.received)
        energies = [float(np.sum(tail[i : i + window] ** 2)) for i in range(0, len(tail) - window, stride)]
        cut = search_from + (int(np.argmin(energies)) * stride + window // 2 if energies else len(tail))
        piece = self._slice(self._lead_in(self.speech_began), cut)
        # Restart the detector at the cut and replay the audio received since then, so the
        # new piece is found right away and nothing between the cut and "now" is lost.
        self.vad = self.pipeline.make_vad()
        self.vad_offset = cut
        remainder = self._slice(cut, self.received)
        usable = (len(remainder) // VAD_WINDOW) * VAD_WINDOW
        for i in range(0, usable, VAD_WINDOW):
            self.vad.accept_waveform(remainder[i : i + VAD_WINDOW])
        self.fed = cut + usable
        self.carry = remainder[usable:]
        self.cut_at = cut
        self.speech_began = cut if self.vad.is_speech_detected() else None
        if len(piece) < 1600:
            return []
        return [(piece, (self.received - cut) / TARGET_RATE)]


def _family(text):
    """Which alphabet the text is written in: 'cyr' (Russian/Ukrainian) or 'lat' (Spanish/English)."""
    return "cyr" if is_cyrillic(text) else "lat"


class Pipeline:
    def __init__(self, config):
        self.config = config
        asr = _abs(config["asr_dir"])
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=os.path.join(asr, "encoder.int8.onnx"),
            decoder=os.path.join(asr, "decoder.int8.onnx"),
            joiner=os.path.join(asr, "joiner.int8.onnx"),
            tokens=os.path.join(asr, "tokens.txt"),
            num_threads=config["asr_threads"],
            model_type="nemo_transducer",
        )
        # Parakeet chooses the language itself and sometimes writes speech in the wrong script.
        # Whisper can be told which language to listen for, so it is the second opinion.
        self.fallbacks = {}
        whisper_dir = config.get("fallback_whisper_dir")
        mode = config["language"]
        known = [lang for lang in ("ru", "es", "pl") if lang in config["packs"]]
        wanted = known if mode == "auto" else ([mode] if mode in known else [])
        if whisper_dir:
            for lang in wanted:
                self.fallbacks[lang] = self._load_whisper(_abs(whisper_dir), lang)
        self.translators = {
            lang: Translator(p["model"], p["spm"], config["mt_threads"], config["beam_size"])
            for lang, p in config["packs"].items()
        }
        self.preroll = config["preroll_samples"]
        vad = config["vad"]
        self.force_cut = vad.get("force_cut", 5.0)
        self.cut_search = vad.get("cut_search", 1.0)
        self.vad_config = sherpa_onnx.VadModelConfig()
        self.vad_config.silero_vad.model = _abs(config["vad_model"])
        self.vad_config.silero_vad.threshold = vad["threshold"]
        self.vad_config.silero_vad.min_silence_duration = vad["min_silence"]
        self.vad_config.silero_vad.min_speech_duration = vad["min_speech"]
        self.vad_config.silero_vad.max_speech_duration = vad["max_speech"]
        self.vad_config.sample_rate = TARGET_RATE
        # Automatic mode: text in a different alphabet from what the stream has been using
        # is treated as a mishearing when it is short or the speech model is unsure of it.
        self.junk_words = config.get("junk_max_words", 3)
        self.junk_confidence = config.get("junk_confidence", -0.30)
        markers = config.get("markers", {})
        self.unclear_confidence = markers.get("unclear_confidence", -0.35)
        # Sound with no speech: how loud (0-1 scale) and for how long before saying so.
        self.sound_level = markers.get("sound_level", 0.02)
        self.no_speech_seconds = markers.get("no_speech_seconds", 4.0)  # 0 turns it off
        self.recent = deque(maxlen=6)  # alphabet of the last few captions
        self.last_latin = config["latin_default"]  # es or pl: the Latin-alphabet language heard last

    def _load_whisper(self, whisper_dir, language):
        return sherpa_onnx.OfflineRecognizer.from_whisper(
            encoder=os.path.join(whisper_dir, "small-encoder.int8.onnx"),
            decoder=os.path.join(whisper_dir, "small-decoder.int8.onnx"),
            tokens=os.path.join(whisper_dir, "small-tokens.txt"),
            language=language,
            task="transcribe",
            num_threads=self.config["asr_threads"],
        )

    def make_vad(self):
        return sherpa_onnx.VoiceActivityDetector(self.vad_config, buffer_size_in_seconds=30)

    def new_stream(self, sample_rate):
        self.recent.clear()
        self.last_latin = self.config["latin_default"]
        return Stream(self, sample_rate)

    @staticmethod
    def _decode(recognizer, speech):
        stream = recognizer.create_stream()
        stream.accept_waveform(TARGET_RATE, speech)
        recognizer.decode_stream(stream)
        result = stream.result
        log_probs = list(getattr(result, "ys_log_probs", None) or [])
        # Mean log-probability of the words written: 0 is certain, more negative is less sure.
        confidence = float(np.mean(log_probs)) if log_probs else None
        return result.text.strip(), confidence

    def _wrong_script(self, text):
        """In a language-locked mode, text in the other script is not what the speaker said."""
        lang = self.config["language"]
        return lang != "auto" and (lang == "ru") != is_cyrillic(text)

    def _dominant_family(self):
        """The alphabet most of the recent captions used, or None if there is no clear one yet."""
        if len(self.recent) < 3:
            return None
        for family in ("cyr", "lat"):
            if sum(1 for f in self.recent if f == family) >= 0.6 * len(self.recent):
                return family
        return None

    def _looks_like_junk(self, text, confidence):
        words = re.findall(r"[^\W\d_]+", text)
        return len(words) <= self.junk_words or (confidence is not None and confidence < self.junk_confidence)

    def process(self, speech):
        """Recognise and translate one speech piece. Returns a result dict, or
        {"skipped": reason} when there is nothing to show."""
        t0 = time.time()
        original, confidence = self._decode(self.recognizer, speech)
        mode = self.config["language"]
        dominant = self._dominant_family() if mode == "auto" else None
        heard = None  # what Parakeet wrote, when Whisper was asked to listen again
        if original and sound_tag(original) is None and not is_filler(original):
            redo = None
            if mode != "auto":
                if self._wrong_script(original):
                    redo = mode
            elif dominant and _family(original) != dominant and self._looks_like_junk(original, confidence):
                redo = "ru" if dominant == "cyr" else self.last_latin
            if redo in self.fallbacks:
                redone, redone_confidence = self._decode(self.fallbacks[redo], speech)
                # Whisper, forced to a language that is not being spoken, tends to invent text and
                # loop ("estar aquí" 100 times). A looping answer is thrown away: Parakeet's stays.
                if not is_looping(redone):
                    heard = original
                    original, confidence = redone, redone_confidence
        t1 = time.time()
        if not original:
            return {"skipped": "nothing recognised" + (f" (Parakeet had written {heard!r})" if heard else "")}
        sound = sound_tag(original)
        if sound is None and is_filler(original):
            return {"skipped": f"filler sound {original!r}"}
        if mode != "auto":
            if self._wrong_script(original):
                return {"skipped": f"wrong script for {mode}-only mode: {original!r}"}
        elif sound is None and dominant and _family(original) != dominant and self._looks_like_junk(original, confidence):
            return {"skipped": f"off-language text ignored while the stream is mostly {dominant}: {original!r}"}
        lang = mode
        if lang == "auto":
            lang = guess_language(original, self.last_latin)
        # Only real sentences say what language the stream is in. A stray "Yeah." or "Okay" in a
        # Russian video must not make the stream look Latin (that sent real Russian to Whisper
        # as "Spanish" and produced nonsense), and English is not a language we translate from.
        votes = sound is None and lang != "en" and len(re.findall(r"[^\W\d_]+", original)) > self.junk_words
        if votes and lang in ("es", "pl"):
            self.last_latin = lang
        if lang == "ru" and "uk" in self.translators and _UKRAINIAN_LETTERS.search(original):
            lang = "uk"  # Russian streams often slip into Ukrainian; і ї є ґ give it away
        translator = self.translators.get(lang)
        if sound is not None:
            # A description of the sound ("[музыка]"), not speech: show it as a marker.
            meaning = (translator.translate(sound) if translator else sound).strip(" .").lower()
            english = "♪ music ♪" if "music" in meaning else f"[{meaning}]"
        else:
            english = translator.translate(original) if translator else original
            english = tidy_translation(original, collapse_repeats(english))
            if english.strip(" .!?").lower() in _BOILERPLATE:
                return {"skipped": f"translation was web-page text ({english!r}) for {original!r}"}
            if votes:
                self.recent.append(_family(original))
        t2 = time.time()
        return {
            "lang": lang,
            "original": original,
            "text": english,
            "speech_seconds": len(speech) / TARGET_RATE,
            "asr_seconds": t1 - t0,
            "translate_seconds": t2 - t1,
            "fallback_used": heard is not None,
            "heard": heard,
            "confidence": confidence,
            "sound": sound is not None,
            # The speech model was not sure of its own words (Whisper gives no confidence).
            "unclear": sound is None and confidence is not None and confidence < self.unclear_confidence,
        }
