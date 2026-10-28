@echo off
rem ===== ClickLab launcher =====
rem Purana tareeqa galat tha: browser python ke UTHNE se pehle khul jata tha, isliye
rem page "Loading…" par atak jata tha (server abhi sun hi nahi raha tha). Ab browser
rem clicklab.py khud kholta hai — server BIND hone ke BAAD. Aur agar ClickLab pehle
rem se chal raha hai to doosri misal uthane ke bajaye wahi khul jata hai.
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python nahi mila. Pehle python.org se install karein, ya is folder ke setup
  echo instructions dekhein. Phir ye file dobara dabayein.
  pause
  exit /b 1
)
echo ClickLab — thahra hua server ho to wahi khul jayega, warna naya uthega...
python clicklab.py
if errorlevel 1 (
  echo.
  echo ClickLab band ho gaya (upar error likha hoga). Ye window tab tak khuli rahegi
  jab tak aap koi button na dabayein — taake error parh sakein.
  pause
)
