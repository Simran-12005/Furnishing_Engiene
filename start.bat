@echo off
title Furnishing Estimator
cd /d "C:\Python\Content_Gallery_Generator\marketing-service\furnishing-engine"

rem --- One-time: allow phones on the Wi-Fi to connect (firewall). ---
rem --- Checks if the rule exists; if not, asks for permission once. ---
netsh advfirewall firewall show rule name="Furnishing8300" >nul 2>&1
if errorlevel 1 (
  echo.
  echo  First-time setup: allowing your phone to connect.
  echo  Click YES on the Windows permission prompt that appears...
  powershell -NoProfile -Command "Start-Process netsh -Verb RunAs -ArgumentList 'advfirewall','firewall','add','rule','name=Furnishing8300','dir=in','action=allow','protocol=TCP','localport=8300','profile=any'"
  timeout /t 3 >nul
)

echo ============================================================
echo  Furnishing Estimator is starting...
echo  The phone link is shown below by the server.
echo  Keep THIS window open. Close it to stop the app.
echo ============================================================
"C:\Python\Content_Gallery_Generator\marketing-service\.venv\Scripts\python.exe" -u server.py
echo.
echo App stopped. Press any key to close.
pause >nul
