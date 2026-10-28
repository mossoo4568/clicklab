@echo off
setlocal
cd /d "%~dp0"
echo ============================================
echo   ClickLab setup - A to Z (sab khud karega)
echo ============================================
echo.

echo [1/4] Checking Python...
where python >nul 2>nul
if errorlevel 1 (
    echo    Python nahi mila - winget se install kar raha hoon...
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
)
where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo    Auto-install nahi ho saka. Khud install karein:
    echo    https://www.python.org/downloads/
    echo    INSTALL KE WAQT "Add python.exe to PATH" TICK KARNA ZAROORI.
    echo    Phir setup.bat dobara chalayein.
    pause
    exit /b 1
)
echo    Python OK.
echo.

echo [2/4] Installing packages from requirements.txt (pillow, numpy, yt-dlp, opencv, rapidocr, scikit-learn)...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo    Purii list install nahi ho payi. Kam se kam ye zaroori hai:
    echo    python -m pip install pillow numpy yt-dlp
    echo    (Baaki packages optional hain - un ke bina tool chalta hai, bas
    echo     chehre / text-padhai / calibration wale numbers khali aaenge.)
)
echo.

echo [3/4] Checking Tesseract OCR (thumbnail par likha text padhne ke liye)...
if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
    echo    Tesseract pehle se installed hai - skip.
) else (
    echo    Tesseract download + install ho raha hai, thora wait karein...
    powershell -NoProfile -Command "$ErrorActionPreference='Stop'; $r=Invoke-RestMethod 'https://api.github.com/repos/UB-Mannheim/tesseract/releases/latest'; $u=$r.assets[0].browser_download_url; Invoke-WebRequest $u -OutFile \"$env:TEMP\tesseract-setup.exe\"; Start-Process -FilePath \"$env:TEMP\tesseract-setup.exe\" -ArgumentList '/S' -Wait; Remove-Item \"$env:TEMP\tesseract-setup.exe\""
    if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
        echo    Tesseract installed OK.
    ) else (
        echo    Install nahi ho paya. Khud karein:
        echo    https://github.com/UB-Mannheim/tesseract/wiki
        echo    (Tesseract ke bina bhi tool chalega - sirf text wale numbers khali aayenge.)
    )
)
echo.
echo ============================================
echo   Setup complete! Ab "ClickLab.bat" double-click karein.
echo   (AI thumbnail tab ke liye Runware ki key chahiye - wo tool ke andar
echo    "AI Thumbnail" me daal di jaati hai. Baaki poora tool key ke bina chalta hai.)
echo ============================================
pause
