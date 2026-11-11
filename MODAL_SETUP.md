# Better 2.0 remote processing

ClickLab can run Better 2.0 locally or on the deployed Modal T4 worker. The browser sends the owned/licensed media to the selected backend, shows progress, and keeps the completed output behind a short-lived local download token.

## One-time account setup

Install/run `setup.bat`, then authenticate the machine with the Modal account that owns the worker:

```powershell
modal token new
modal profile current
```

Do not put the token in GitHub, `.env` committed files, screenshots, or chat. If the profile is missing or misconfigured, Local mode continues to work and Modal mode reports the account error.

## Deploy/update the worker

```powershell
modal deploy modal_worker.py
```

The worker uses a T4 GPU, installs FFmpeg inside its image, falls back from NVENC to x264, and scales down after the job. The ClickLab UI exposes `This PC · local FFmpeg` and `Modal cloud · T4 GPU (fast)` under Analyze & Edit. The Stop button cancels the Modal function call when the provider accepts cancellation.

Only process media you own or are licensed to edit. Modal charges the account according to its current workspace billing and budget settings.
