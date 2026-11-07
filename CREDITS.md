# Credits and licences

Live Video Translator is built on the work below. Thank you to everyone involved.
Licence information was read from each project's own page (the model card or repository) when
this file was written.

## Models

These are **not** stored in this repository. `setup.bat` downloads them to your computer.

| Model | Used for | By | Licence |
|---|---|---|---|
| [Parakeet TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) | speech recognition (Russian, Ukrainian, Spanish and more) | NVIDIA | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| [quickmt-ru-en](https://huggingface.co/quickmt/quickmt-ru-en) | Russian to English translation | the [quickmt](https://github.com/quickmt/quickmt) project | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| [quickmt-uk-en](https://huggingface.co/quickmt/quickmt-uk-en) | Ukrainian to English translation | the quickmt project | CC BY 4.0 |
| [quickmt-es-en](https://huggingface.co/quickmt/quickmt-es-en) | Spanish to English translation | the quickmt project | CC BY 4.0 |
| [Silero VAD](https://github.com/snakers4/silero-vad) | finding where speech starts and stops | Silero Team | MIT |
| [Whisper small](https://huggingface.co/openai/whisper-small) (optional) | a second opinion on unclear lines | OpenAI | Apache 2.0 |

**Changes made to the models (as CC BY 4.0 asks us to say):**
- The Parakeet model is used in the int8-quantised ONNX form published by the
  [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) project. We did not change it further.
- The three quickmt models were converted to the CTranslate2 format with int8 quantisation so
  they run fast on an ordinary CPU. Their SentencePiece tokenizer files are unchanged. Each
  translation pack contains an `ATTRIBUTION.txt` with these details.
- The authors of these models are not affiliated with this project and do not endorse it.

## Software libraries

Installed by `setup.bat`; not part of this repository.

| Library | Used for | Licence |
|---|---|---|
| [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) | running the speech and voice models | Apache 2.0 |
| [CTranslate2](https://github.com/OpenNMT/CTranslate2) | running the translation models | MIT |
| [SentencePiece](https://github.com/google/sentencepiece) | splitting text for the translation models | Apache 2.0 |
| [python-soxr](https://github.com/dofuuz/python-soxr) | converting the sample rate of the audio | LGPL 2.1 or later |
| [NumPy](https://numpy.org/) | numerical work | BSD 3-Clause (and others, see NumPy) |
| [websockets](https://github.com/python-websockets/websockets) | talking to the browser extension | BSD 3-Clause |

## This project

The code in this repository is released under the MIT licence (see [LICENSE](LICENSE)).
