@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title ClickLab setup

echo ============================================
echo   ClickLab A-to-Z setup
echo   Python + venv + FFmpeg + OCR + packages
echo ============================================
echo.

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if not defined PY (
  where py >nul 2>nul
  if not errorlevel 1 py -3 -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul && set "PY=py -3"
)
if not defined PY (
  where python >nul 2>nul
  if not errorlevel 1 python -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo [1/6] Python 3.12 install ho raha hai...
  where winget >nul 2>nul
  if errorlevel 1 goto :no_winget_python
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  if not defined PY (
    where py >nul 2>nul
    if not errorlevel 1 set "PY=py -3"
  )
)
if not defined PY (
  echo Python 3.10+ nahi mila. Winget install karo ya python.org se Python install karo.
  goto :fail
)
echo [1/6] Python OK: %PY%

echo [2/6] Is project ka isolated virtual environment ban raha hai...
if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv
  if errorlevel 1 goto :fail
)
set "PY=%~dp0.venv\Scripts\python.exe"
"%PY%" -m ensurepip --upgrade >nul 2>nul
"%PY%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :fail

echo [3/6] Python requirements install/verify ho rahi hain...
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 goto :fail
"%PY%" -c "import PIL,numpy,yt_dlp; print('Core Python packages OK')"
if errorlevel 1 goto :fail

echo [4/6] FFmpeg aur ffprobe check/install ho rahe hain...
where ffmpeg >nul 2>nul
set "FFOK=!errorlevel!"
where ffprobe >nul 2>nul
set "FPOK=!errorlevel!"
if not "!FFOK!"=="0" set "FPOK=1"
if not "!FPOK!"=="0" (
  where winget >nul 2>nul
  if errorlevel 1 (
    echo Winget nahi mila. FFmpeg manually install karke PATH mein add karo: https://ffmpeg.org/download.html
    goto :fail
  )
  winget install -e --id Gyan.FFmpeg.Shared --accept-package-agreements --accept-source-agreements
  set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"
  if exist "C:\Program Files\FFmpeg\bin" set "PATH=C:\Program Files\FFmpeg\bin;%PATH%"
)
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo FFmpeg install hua ho sakta hai, lekin current PATH refresh nahi hua. Terminal band karke setup dobara chalao.
  goto :fail
)
where ffprobe >nul 2>nul
if errorlevel 1 goto :fail
echo FFmpeg + ffprobe OK.

echo [5/6] Tesseract OCR check/install ho raha hai...
where tesseract >nul 2>nul
if errorlevel 1 if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" set "PATH=C:\Program Files\Tesseract-OCR;%PATH%"
where tesseract >nul 2>nul
if errorlevel 1 (
  where winget >nul 2>nul
  if not errorlevel 1 winget install -e --id UB-Mannheim.TesseractOCR --accept-package-agreements --accept-source-agreements
  if exist "C:\Program Files\Tesseract-OCR" set "PATH=C:\Program Files\Tesseract-OCR;%PATH%"
)
where tesseract >nul 2>nul
if errorlevel 1 echo Tesseract unavailable — RapidOCR fallback phir bhi chalega.
if not errorlevel 1 echo Tesseract OCR OK.

echo [6/6] Final health check...
"%PY%" -c "import sys; print('Python',sys.version.split()[0])"
ffprobe -version | findstr /b /c:"ffprobe version" >nul
if errorlevel 1 goto :fail
echo.
echo ============================================
echo Setup complete.
echo Ab ClickLab.bat double-click karo.
echo Virtual environment: .venv
echo.
echo Optional Modal cloud worker setup:
echo   ".venv\Scripts\modal.exe" token new
echo   ".venv\Scripts\modal.exe" profile current
echo   ".venv\Scripts\modal.exe" deploy modal_worker.py
echo Browser login ke baad deploy command isi ClickLab folder mein chalana hai.
echo API keys repo/setup mein nahi hain; apni keys local/tool ke andar do.
echo ============================================
pause
exit /b 0

:no_winget_python
echo Winget available nahi hai. Python 3.12 manually install karo:
echo https://www.python.org/downloads/windows/
echo Install ke waqt "Add python.exe to PATH" select karo.

:fail
echo.
echo SETUP FAILED. Upar wali error fix karke setup.bat dobara chalao.
pause
exit /b 1
