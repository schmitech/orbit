# Install FFmpeg on AWS Linux (for Whisper Audio Transcription)

This guide installs a static FFmpeg build on Amazon Linux 2/2023 so Whisper-based audio transcription (e.g., in Orbit) can process audio files. Uses builds from [johnvansickle.com/ffmpeg](https://johnvansickle.com/ffmpeg/).

---

## 1. Check architecture

```bash
uname -m
```

- **x86_64** → Intel/AMD, use the **amd64** build in the next step  
- **aarch64** → ARM (Graviton), use the **arm64** build in the next step  

---

## 2. Download the static build

**For x86_64 (Intel/AMD):**

```bash
cd /tmp
wget https://johnvansickle.com/ffmpeg/builds/ffmpeg-git-amd64-static.tar.xz
```

**For ARM64 (Graviton):**

```bash
cd /tmp
wget https://johnvansickle.com/ffmpeg/builds/ffmpeg-git-arm64-static.tar.xz
```

---

## 3. Extract the tarball

**If you used amd64:**

```bash
tar -xf ffmpeg-git-amd64-static.tar.xz
```

**If you used arm64:**

```bash
tar -xf ffmpeg-git-arm64-static.tar.xz
```

---

## 4. Copy binaries to /usr/local/bin

```bash
cd ffmpeg-git-*-static/
sudo cp ffmpeg ffprobe /usr/local/bin/
```

*(The folder name varies by version, e.g. `ffmpeg-git-20240629-amd64-static`. The `ffmpeg-git-*-static` glob will match it.)*

---

## 5. Verify

```bash
ffmpeg -version
ffprobe -version
```

Both should print version and build info.

---

## 6. (Optional) Clean up /tmp

```bash
rm -rf /tmp/ffmpeg-git-*-static.tar.xz /tmp/ffmpeg-git-*-static
```

---

## Notes

- **PATH:** `/usr/local/bin` is usually on `PATH`, so `ffmpeg` and `ffprobe` are available to all users.
- **Restart the app:** If Orbit (or another service) was running during install, restart it so it can find `ffmpeg`.
- **Updates:** This uses a static build; to upgrade, re-run the steps and overwrite the files in `/usr/local/bin`.
