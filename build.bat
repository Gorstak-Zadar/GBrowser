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
echo Locating VCRUNTIME140.dll (python313.dll depends on it; PyInstaller misses it on some setups)...
REM python313.dll links against BOTH VCRUNTIME140.dll and VCRUNTIME140_1.dll.
REM PyInstaller reliably bundles _1 but sometimes not the base DLL, which yields
REM "failed to load module python313.dll" (LoadLibrary can't resolve the dependency).
REM Resolve a real copy (PyQt6 ships one next to the Qt binaries) and bundle it explicitly.
set "VCR="
for /f "delims=" %%P in ('python -c "import PyQt6,os;print(os.path.join(os.path.dirname(PyQt6.__file__),'Qt6','bin','vcruntime140.dll'))"') do set "VCR=%%P"
if not exist "%VCR%" for /f "delims=" %%P in ('python -c "import os,sysconfig;print(os.path.join(sysconfig.get_paths()[\"data\"],\"vcruntime140.dll\"))"') do set "VCR=%%P"
if exist "%VCR%" ( echo Found VCRUNTIME140.dll: "%VCR%" ) else ( echo WARNING: VCRUNTIME140.dll not found - build may fail to launch. )

echo.
echo Step 2: Building executable with PyInstaller...
REM --collect-all PyQt6 is REQUIRED: the default hook does not bundle
REM QtWebEngineProcess.exe (the web-content render helper). Without it QtWebEngine
REM crashes with an access violation the moment a page tries to render. It also pulls
REM in the WebEngine resources/locales in the correct relative layout.
if exist "%VCR%" (
    pyinstaller --noconfirm --onedir --windowed --name "GBrowser" --icon "GBrowser.ico" --collect-all PyQt6 --add-data "blocklist.txt;." --add-binary "%VCR%;." GBrowser.py
) else (
    pyinstaller --noconfirm --onedir --windowed --name "GBrowser" --icon "GBrowser.ico" --collect-all PyQt6 --add-data "blocklist.txt;." GBrowser.py
)
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
