## Voice Studio

A text-to-speech app powered by Microsoft Edge's TTS service.

### Requirements

- Internet connection required (voices are synthesized in the cloud)

### Windows

Download `VoiceStudio.exe` from the [latest release](https://github.com/justinyob/edge-tts-utils/releases/latest) and run it. No installation needed.

### Linux

Install dependencies first:

```
sudo apt install ffmpeg python3-tk     # Debian/Ubuntu
sudo pacman -S ffmpeg tk               # Arch
```

Then run:

```
chmod +x VoiceStudio
./VoiceStudio
```

### For developers building from source

1. Python 3.11+ required
2. `pip install -r requirements.txt`
3. **Windows only:** download a static `ffmpeg.exe` build (e.g. from https://www.gyan.dev/ffmpeg/builds/) and place it in the project root
4. `python build.py`

The built binary lands in `dist/VoiceStudio` (Linux) or `dist\VoiceStudio.exe` (Windows).

### Publishing an update

1. Bump `APP_VERSION` in `config.py`
2. Run `python build.py`
3. Create a GitHub Release tagged `v{version}` (e.g. `v1.1.0`)
4. Upload `VoiceStudio.exe` / `VoiceStudio` as a release asset with exactly that filename

The auto-updater in shipped builds polls GitHub Releases on launch and offers an in-app update when a newer tag is found.
