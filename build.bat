@echo off
setlocal
cd /d "%~dp0"

set "VERSION=0.6.1"

echo Building GBrowser v%VERSION%...
echo.

echo Step 1: Installing dependencies...
pip install PyQt6 PyQt6-WebEngine pywin32 pyinstaller
if errorlevel 1 goto error

echo.
echo Step 2: Building executable with PyInstaller...
pyinstaller --noconfirm --onedir --windowed --name "GBrowser" --icon "GBrowser.ico" --add-data "blocklist.txt;." GBrowser.py
if errorlevel 1 goto error

echo.
echo Step 3: Copying assets to dist...
copy /Y blocklist.txt dist\GBrowser\
copy /Y GBrowser.ico dist\GBrowser\

echo.
echo Step 4: Building installer...
REM Inno Setup outputs to releases\%VERSION%\ (defined in GBrowser.iss OutputDir)
"C:\Program Files\Inno Setup 7\ISCC.exe" GBrowser.iss
if errorlevel 1 goto error

echo.
echo Build complete!
echo Output: releases\%VERSION%\GBrowser-%VERSION%-Setup.exe
goto end

:error
echo.
echo BUILD FAILED!
exit /b 1

:end
