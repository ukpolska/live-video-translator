"""Tells Chrome where the helper program (native_host.bat) is, so the extension can start the
translator by itself. Only for the current Windows user; no administrator rights needed.
setup.bat runs this. If you move the project folder, run setup.bat again.

  python register_native_host.py             register
  python register_native_host.py --remove    undo it
  python register_native_host.py --dry-run   show what would be written, change nothing"""
import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOST_NAME = "com.ukpolska.live_video_translator"
REGISTRY_KEY = rf"Software\Google\Chrome\NativeMessagingHosts\{HOST_NAME}"
MANIFEST_PATH = HERE / "native_host_manifest.json"


def extension_id():
    """The extension's ID comes from the public key written in its manifest.json."""
    manifest = json.loads((HERE.parent / "extension" / "manifest.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(base64.b64decode(manifest["key"])).hexdigest()[:32]
    return "".join(chr(ord("a") + int(c, 16)) for c in digest)


def build_manifest():
    return {
        "name": HOST_NAME,
        "description": "Starts the Live Video Translator program",
        "path": str(HERE / "native_host.bat"),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{extension_id()}/"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--remove", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        print("Would write", MANIFEST_PATH, "with:")
        print(json.dumps(build_manifest(), indent=2))
        print(rf"Would set HKEY_CURRENT_USER\{REGISTRY_KEY} to", MANIFEST_PATH)
        return
    if sys.platform != "win32":
        sys.exit("This registration is for Windows only.")
    import winreg

    if args.remove:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY)
            print("Removed the helper registration.")
        except FileNotFoundError:
            print("It was not registered.")
        MANIFEST_PATH.unlink(missing_ok=True)
        return

    MANIFEST_PATH.write_text(json.dumps(build_manifest(), indent=2) + "\n", encoding="utf-8")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(MANIFEST_PATH))
    print("Registered: Chrome can now start the translator from the extension's button.")


if __name__ == "__main__":
    main()
