# ClickLab

ClickLab is a local-first YouTube research and creator workspace. It combines public YouTube data, channel tracking, competitor analysis, thumbnail measurement, transcript/OCR tools, and optional AI-assisted drafting in a responsive desktop and mobile interface.

## Features

- **Creator tools:** 67 research, video, image, writing, and calculator tools.
- **Channel workspaces:** organize your channels and add up to 10 competitors per channel.
- **Public statistics:** track observed channel counters and their actual collection timestamps.
- **Video Intelligence Pack:** inspect complete public descriptions, creator-applied tags, subtitles, and screen OCR from one video link.
- **Thumbnail workflows:** measure local images, compare packaging, prepare A/B variants, and optionally generate images.
- **Grounded drafting:** attach real YouTube evidence to supported AI drafting tools.
- **Responsive interface:** adapts to mobile, laptop, desktop, and wide-screen layouts.

## Requirements

- **Windows 10 or 11** for the included batch installers.
- **Python 3.x**; `setup.bat` can install Python 3.12 through `winget` when available.
- Python packages listed in [requirements.txt](requirements.txt): Pillow, NumPy, yt-dlp, OpenCV, RapidOCR, scikit-learn, and pytrends.
- **FFmpeg** available on `PATH` for video-frame screen OCR.
- A **YouTube Data API v3 key** for tools that use the YouTube Data API. Public-page extraction does not cover every API-backed feature.
- Optional provider keys for specific features:
  - **Gemini:** AI drafting and explicitly selected API screen OCR.
  - **Runware:** optional AI thumbnail generation.

Node.js is not required to run ClickLab. No API key is included in this repository.

## Quick Start on Windows

1. Download or clone the repository:

   ```bash
   git clone https://github.com/mossoo4568/clicklab.git
   cd clicklab
   ```

2. Run **`setup.bat`** by double-clicking it. It checks Python, installs `requirements.txt`, and attempts to install Tesseract OCR for thumbnail text analysis. Review and approve any installer prompts.

3. Run **`ClickLab.bat`**. The server starts and opens ClickLab in your browser, normally at:

   ```text
   http://127.0.0.1:8028/
   ```

4. Open **Settings** in ClickLab to configure the provider keys you want to use. Keep the launcher window open while using the app; closing it stops the local server.

### Manual Start

If you already have Python and the dependencies installed:

```bash
python -m pip install -r requirements.txt
python clicklab.py
```

Install FFmpeg separately before using screen OCR. Local OCR does not send video frames to a cloud OCR provider.

## Project Files

| File | Purpose |
|---|---|
| `ClickLab.bat` | Windows application launcher |
| `setup.bat` | Windows dependency setup |
| `requirements.txt` | Python package requirements |
| `clicklab.py` | Local HTTP server, interface, and core analysis engine |
| `studio.css` | Responsive workspace styling |
| `studio.js`, `studio_pro.js`, `studio_features.js` | Workspace and creator-tool frontend |
| `studio_backend.py`, `studio_features.py` | Public-data services and tool workflows |
| `test_studio.py`, `test_studio_features.py` | Regression and browser-layout tests |
| `STUDIO_GUIDE.md` | Workspace behavior and data-source details |
| `FEATURE_COVERAGE.md` | Implemented tool scope and remaining limitations |

## Privacy and Local Data

API keys, cookies, `.env` files, generated images, reports, cached metadata, transcripts, OCR output, channel workspaces, and tracking databases are excluded from Git through `.gitignore`.

Local runtime data is stored primarily in `thumb_output/`. Back up that folder separately if you want to preserve your workspaces and history. Never commit your private key files or runtime data.

## Important Limitations

- Real Time means **observations of public YouTube counters**, not another channel's private YouTube Studio traffic.
- Public subscriber counts may be rounded or delayed. Historical changes exist only after ClickLab has collected readings.
- Search samples are not global search-volume figures or a complete YouTube index.
- Tags are the creator's applied public tags; ClickLab does not invent a separate keyword field.
- Subtitles depend on availability. Screen OCR reads visible frame text; it is not spoken-audio transcription.
- AI features may consume provider quota or credits. API screen OCR requires explicit selection and confirmation.
- Earnings, RPM, valuation, and sponsorship calculations are scenarios based on supplied assumptions, not verified channel income.

## Tests

```bash
python -m unittest test_studio test_studio_features
```

The current suite contains 45 tests. Responsive browser tests require Python Playwright and an installed Chrome browser; they are skipped when Playwright is unavailable.

For optional public-data tool verification:

```bash
python verify_tools.py http://127.0.0.1:8028 --skip-ocr
```

This uses YouTube API quota. AI-generation calls are not executed by the verification script.

## License

See [LICENSE.txt](LICENSE.txt).
