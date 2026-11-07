# Live Video Translator

Live English captions for any video playing in Google Chrome, even when the site has no
subtitles. It listens to the sound of the tab, works out what is being said, and shows an
English translation in a box over the page, a second or two behind the speaker.

- **Languages:** Russian, Ukrainian and Spanish into English. It works out the language by
  itself, so there is nothing to switch.
- **Private:** everything runs on your own computer. After setup, no audio, text or
  anything else is sent over the internet.
- **Free:** no accounts, no subscription, no limits.
- **Ordinary PC:** no graphics card needed. It was developed on a 2015 4-core Intel i7 with
  16 GB of RAM, where captions appear about 1-2 seconds after the speaker pauses.

It is a personal project, shared in case it is useful to someone else. It is not a product
and comes with no guarantees (see [Known limits](#known-limits)).

## Built for a basic computer

This was deliberately developed and tuned for a very ordinary computer: a 2015 desktop with
a 4-core processor, 16 GB of RAM and no graphics card. Every choice (small models, short
processing steps, no GPU) was made so that it is useful on that kind of machine, not only on
a powerful one.

On a stronger PC (say 32 GB of RAM and a suitable graphics card) it could be improved, mainly
by running larger and more accurate speech and translation models, and by being faster. This
version does **not** do that by itself: it runs on the processor only, and using a GPU or
bigger models would need changes to the code. The two settings `asr_threads` and
`mt_threads` (see [Settings](#settings-optional)) already let it use more processor cores.

## What you need

- Windows 10 or 11 (64-bit). It has only been tested on Windows.
- Google Chrome.
- About 3 GB of free disk space and 8 GB of RAM (16 GB is better). While it runs, the
  translator itself uses about 1.5 GB of memory.
- A normal internet connection for the one-time setup (about 1.1 GB of downloads).
- Python 3.12, free from [python.org](https://www.python.org/downloads/). On the first screen
  of the Python installer, **tick "Add python.exe to PATH"**.

## Install (once)

**1. Get the files.** On this page click the green **Code** button, then **Download ZIP**.
Right-click the downloaded file, choose **Extract All**, and put the folder somewhere you
will remember (for example your Documents folder).

**2. Run the setup.** Open the folder and double-click **setup.bat**. A black window opens,
installs what it needs, downloads the models and connects Chrome to the translator (this
only affects your own Windows account). This can take 10-30 minutes. When it says
"Setup finished", press any key. If Windows shows a "protected your PC" notice for the
file, click **More info**, then **Run anyway**. The file only runs the steps you can read
inside it.

**3. Add the extension to Chrome.**
1. In Chrome, type `chrome://extensions` in the address bar and press Enter.
2. Turn on **Developer mode** (switch at the top right).
3. Click **Load unpacked**.
4. In the window that opens, click the **Folder:** box at the bottom, paste the full path of
   the `extension` folder inside the folder you extracted (for example
   `C:\Users\You\Documents\LiveVideoTranslator\extension`), and click **Select Folder**.
5. "Live Video Translator" appears in the list. Click the puzzle-piece icon next to the
   address bar and the pin beside it, so its button is always visible.

## Use it

1. Open your video in Chrome.
2. Click the **Live Video Translator button** next to the address bar. A small badge shows
   **ON**. If the translator is not running yet, the box says "Starting the translator..."
   for about 20 seconds while it loads. Then press play.
3. Captions appear in a dark box at the top of the page. **Drag it** wherever you like and
   it remembers the place. Click the button again to turn it off.

There is nothing else to start. The translator starts by itself when you click the button,
and shuts itself down about 10 minutes after you stop using it, to free up memory.
(`start_server.bat` is only a backup: it starts the translator by hand in a visible window,
which also shows what it is doing.)

Things you may see in the box:

| Caption | Meaning |
|---|---|
| plain text | a translation |
| *[unclear] text* (italic) | the speech was hard to make out, so the translation may be wrong |
| *[inaudible]* | something was said but nothing could be made out |
| *♪ music ♪* or *♪ [no speech]* | music or sound without speech |

Tips:
- Switch the extension on **before** pressing play, and use one tab at a time.
- It is built for ordinary speech. Loud music over the voice, several people talking at
  once and very fast speech all reduce accuracy.
- If you reload the page, click the button off and on again.

## If something does not work

| Problem | What to try |
|---|---|
| Nothing appears on the page | Wait about 20 seconds after clicking: the first start loads the models. Then reload the video page and click the button off and on. |
| The box says "The translator is not running" | Double-click `connect_chrome.bat`: it reconnects Chrome to the translator. Do the same if you moved the folder. The file `server/server.log` shows why it stopped. |
| To see what the translator is doing | Double-click `start_server.bat` and leave its window open. |
| `start_server.bat` closes straight away or says the port is in use | The translator is already running in the background. Just use the extension's button. |
| `setup.bat` says Python was not found | Install Python 3.12 from python.org and tick "Add python.exe to PATH". |
| Setup stops part-way | Run `setup.bat` again. Anything already downloaded is kept. |
| "Cannot capture a tab with an active stream" | Close that tab and open the video again. |
| The captions are late or the PC is struggling | Close other heavy programs. The speed settings are in `server/config.json`. |

## Settings (optional)

`server/config.json` is created by the setup. The ones people change most:

| Setting | What it does |
|---|---|
| `markers.enabled` | `false` turns off all the `[unclear]`, `[inaudible]` and music notes |
| `markers.unclear_confidence` | closer to 0 flags more captions as unclear (default -0.35) |
| `markers.no_speech_seconds` | seconds of sound without speech before the music note shows (0 turns it off) |
| `vad.force_cut` | longest stretch of speech (seconds) before a caption is cut, shorter means sooner captions but choppier ones |
| `asr_threads`, `mt_threads` | how many processor cores are used |
| `idle_exit_minutes` | minutes without use before the translator shuts itself down (default 10) |

To use an optional second speech model that sometimes rescues unclear lines, run
`setup.bat --with-whisper` from a command window (adds a 640 MB download and uses more memory).

## Known limits

- Chrome on Windows only. It is not on the Chrome Web Store, so it is added by hand as above.
- Translations come from small models that run on a normal PC. Russian and Ukrainian are
  better than Spanish. Names, slang and idioms are often wrong, and very short fragments can
  be mistranslated. **Do not rely on it for anything where a mistake matters** (legal,
  medical, safety).
- One tab at a time. The caption box is designed to follow a video into fullscreen, but
  sites with unusual players may not show it.
- Some sites may not allow the sound of the tab to be captured.

## Privacy and the extension's permissions

The extension only talks to the program on your own computer (`localhost`, port 8765). The
only downloads are the one-time setup. The permissions it asks for, and why:

| Permission | Why |
|---|---|
| `tabCapture` | to hear the sound of the tab you switch it on for |
| `offscreen` | a hidden page where the sound is handled |
| `activeTab`, `scripting` | to put the caption box on the tab you clicked |
| `storage` | to remember which tab is switched on |
| `nativeMessaging` | so the button can start the translator program on your computer (set up by `setup.bat`) |
| Run on all sites | so the caption box can appear on whatever site you watch |

## How it works (short version)

Chrome gives the extension the tab's sound, which is sent to a small program on your PC
(`server/`). It cuts the sound into phrases at the pauses, turns each phrase into text with
NVIDIA's Parakeet speech recogniser, and translates it with a small translation model for
that language. The English text goes back to the extension, which draws it on the page.

## Removing it

Double-click **uninstall.bat** (it disconnects the translator from Chrome), remove the
extension on `chrome://extensions`, and delete the folder.

## Credits and licences

This project stands on other people's work. See [CREDITS.md](CREDITS.md) for every model and
library, their authors and licences. The translation models are by the
[quickmt](https://github.com/quickmt/quickmt) project, the speech recogniser is NVIDIA's
Parakeet, and the voice detector is Silero VAD.

The code in this repository is under the [MIT licence](LICENSE).
