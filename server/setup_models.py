"""Downloads the speech and translation models into server/models and creates config.json.

Normally run for you by setup.bat. It is safe to run again: anything already downloaded and
checked is kept.

  python setup_models.py                    the models needed to run (about 1.1 GB to download)
  python setup_models.py --with-whisper     also the optional Whisper "second opinion" (+640 MB)
  python setup_models.py --packs-from X     take the translation packs from a folder or web
                                            address X instead of the project's release page
"""
import argparse
import hashlib
import json
import shutil
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODELS = HERE / "models"

SHERPA_RELEASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models"
# Where the translation packs (ru-en.zip, uk-en.zip, es-en.zip) are published.
PACKS_BASE_URL = "https://github.com/ukpolska/live-video-translator/releases/download/models-v1"

VAD = {"file": "silero_vad.onnx", "bytes": 643854,
       "sha256": "9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6"}
PARAKEET = {"file": "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8.tar.bz2", "bytes": 487200000,
            "sha256": "1495e91b59d7fc53ddca91f3431758ec99f8fa253fdb0e1e851be0f72b14b0f9"}
WHISPER = {"file": "sherpa-onnx-whisper-small.tar.bz2", "bytes": 639400000, "sha256": None}
PACKS = {
    "ru-en": {"bytes": 189062202, "sha256": "3ff5b49043acf538cee5a2065d04a0fba06d5046e7527340ccd213d89b7e3590"},
    "uk-en": {"bytes": 184677754, "sha256": "541e143ac3cdf05e0d487c0fb38b9811d5ed02d44fba86c72e41dc954411677b"},
    "es-en": {"bytes": 186321131, "sha256": "39ac015e326f8d75145ccba0d98ceb2cf46edb836a338e4b276ffafb8bd4ac81"},
}
PARAKEET_FILES = ["encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt"]
WHISPER_FILES = ["small-encoder.int8.onnx", "small-decoder.int8.onnx", "small-tokens.txt"]


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def is_good(path, info):
    """True if the file is there and matches its checksum (or, with none known, is large enough)."""
    path = Path(path)
    if not path.exists():
        return False
    if info.get("sha256"):
        return sha256_of(path) == info["sha256"]
    return path.stat().st_size > info["bytes"] * 0.9


def fetch(source, name, info, folder, label):
    """Gets `name` from a web address or local folder into `folder`, with a progress display."""
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / name
    if is_good(dest, info):
        print(f"  {label}: already downloaded.")
        return dest
    part = folder / (name + ".part")
    for attempt in range(1, 4):
        try:
            if str(source).startswith(("http://", "https://")):
                request = urllib.request.Request(f"{source}/{name}", headers={"User-Agent": "live-video-translator-setup"})
                with urllib.request.urlopen(request, timeout=60) as response, open(part, "wb") as out:
                    total = int(response.headers.get("Content-Length") or info["bytes"])
                    done, last = 0, -1
                    while True:
                        block = response.read(1 << 20)
                        if not block:
                            break
                        out.write(block)
                        done += len(block)
                        percent = int(done * 100 / total)
                        if percent != last:
                            print(f"\r  {label}: {percent:3d}%  ({done / 1e6:.0f} of {total / 1e6:.0f} MB)", end="", flush=True)
                            last = percent
                print()
            else:
                print(f"  {label}: copying from {source}")
                shutil.copyfile(Path(source) / name, part)
            part.replace(dest)
            if not is_good(dest, info):
                dest.unlink()
                raise OSError("the downloaded file failed its checksum")
            return dest
        except (OSError, urllib.error.URLError) as error:
            print(f"\n  {label}: attempt {attempt} of 3 failed ({error}).")
            if attempt == 3:
                raise
            time.sleep(3 * attempt)


def extract_tar(archive, inner_dir, wanted, target):
    """Pulls only the `wanted` files out of the tar.bz2 `archive` into `target`."""
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=MODELS) as temp:
        with tarfile.open(archive, "r:bz2") as tar:
            try:
                tar.extractall(temp, filter="data")
            except TypeError:  # older Python without extraction filters
                tar.extractall(temp)
        for name in wanted:
            shutil.move(str(Path(temp) / inner_dir / name), str(target / name))


def write_config(with_whisper):
    config_path = HERE / "config.json"
    if config_path.exists():
        if not with_whisper:
            print("  config.json already exists: left as it is.")
            return
        config = json.loads(config_path.read_text(encoding="utf-8"))
    else:
        config = json.loads((HERE / "config.example.json").read_text(encoding="utf-8"))
    if with_whisper:
        config["fallback_whisper_dir"] = "models/whisper-small"
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print("  config.json written.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--with-whisper", action="store_true", help="also install the optional Whisper second opinion")
    parser.add_argument("--packs-from", default=PACKS_BASE_URL, help="folder or web address holding the pack zips")
    args = parser.parse_args()

    MODELS.mkdir(exist_ok=True)
    need_gb = 3.5 if args.with_whisper else 2.5
    free_gb = shutil.disk_usage(MODELS).free / 1e9
    if free_gb < need_gb:
        sys.exit(f"Not enough free disk space: {free_gb:.1f} GB free, about {need_gb} GB needed.")

    print("1/4  Voice detector")
    fetch(SHERPA_RELEASE, VAD["file"], VAD, MODELS, "silero_vad.onnx")

    print("2/4  Speech recogniser (Parakeet)")
    parakeet_dir = MODELS / "parakeet-tdt-0.6b-v3-int8"
    if all((parakeet_dir / f).exists() for f in PARAKEET_FILES):
        print("  Parakeet: already installed.")
    else:
        archive = fetch(SHERPA_RELEASE, PARAKEET["file"], PARAKEET, MODELS, "Parakeet")
        print("  Unpacking...")
        extract_tar(archive, "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8", PARAKEET_FILES, parakeet_dir)
        archive.unlink()

    print("3/4  Translation packs")
    for name, info in PACKS.items():
        pack_dir = MODELS / "packs" / name
        if (pack_dir / "model.bin").exists():
            print(f"  {name}: already installed.")
            continue
        archive = fetch(args.packs_from, f"{name}.zip", info, MODELS / "downloads", name)
        with zipfile.ZipFile(archive) as z:
            z.extractall(MODELS / "packs")
        archive.unlink()

    print("4/4  Second opinion (Whisper, optional)")
    if args.with_whisper:
        whisper_dir = MODELS / "whisper-small"
        if all((whisper_dir / f).exists() for f in WHISPER_FILES):
            print("  Whisper: already installed.")
        else:
            archive = fetch(SHERPA_RELEASE, WHISPER["file"], WHISPER, MODELS, "Whisper small")
            print("  Unpacking...")
            extract_tar(archive, "sherpa-onnx-whisper-small", WHISPER_FILES, whisper_dir)
            archive.unlink()
    else:
        print("  Skipped (add --with-whisper to install it).")

    shutil.rmtree(MODELS / "downloads", ignore_errors=True)
    write_config(args.with_whisper)
    print("\nAll done. Start the translator with start_server.bat.")


if __name__ == "__main__":
    main()
