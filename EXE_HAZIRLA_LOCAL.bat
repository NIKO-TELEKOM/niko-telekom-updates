@echo off
chcp 65001 >nul
title NIKO TELEKOM V30 EXE Hazirlama
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python 3.11/3.12 tapilmadi. Python qurasdirin ve "Add Python to PATH" secin.
  pause
  exit /b 1
)
py -m pip install --upgrade pip
if errorlevel 1 goto fail
py -m pip install pyinstaller
if errorlevel 1 goto fail
py -m PyInstaller --noconfirm --clean --onefile --windowed --name NIKO_TELEKOM_V30 NIKO_TELEKOM_POS_V30.py
if errorlevel 1 goto fail
echo.
echo Hazir proqram: dist\NIKO_TELEKOM_V30.exe
pause
exit /b 0
:fail
echo EXE yigilmadi. Interneti ve Python qurasdirilmasini yoxlayin.
pause
exit /b 1
