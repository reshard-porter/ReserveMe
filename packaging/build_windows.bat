@echo off
REM Build ReserveMe for Windows: creates dist\ReserveMe\ and dist\installer\ReserveMe-Setup-<version>.exe
REM Needs: Python 3.12 (64-bit) on PATH, and Inno Setup 6 (iscc.exe) for the installer step.
setlocal
cd /d "%~dp0\.."

if not exist .venv (
  py -3.12 -m venv .venv || python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt || goto :error

python -m pytest -q tests || goto :error
pyinstaller packaging\reserveme.spec --noconfirm --clean || goto :error

REM Optional code signing: set SIGN_CMD to your signtool command, e.g.
REM   set SIGN_CMD=signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a
if defined SIGN_CMD %SIGN_CMD% dist\ReserveMe\ReserveMe.exe

where iscc >nul 2>nul
if %errorlevel%==0 (
  iscc packaging\installer.iss || goto :error
) else if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
  "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" packaging\installer.iss || goto :error
) else (
  echo Inno Setup not found - skipping installer. The app is in dist\ReserveMe\
)
if defined SIGN_CMD if exist dist\installer\*.exe %SIGN_CMD% dist\installer\*.exe
echo.
echo Done. App folder: dist\ReserveMe   Installer: dist\installer
exit /b 0

:error
echo Build failed.
exit /b 1
