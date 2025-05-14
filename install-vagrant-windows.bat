@echo off
:: Self-elevate to admin
:: Check for admin rights
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting administrative privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo Running as Administrator!

:: 1. Install Vagrant
echo Installing Vagrant...
winget install Vagrant --accept-package-agreements --accept-source-agreements

:: 2. Install VirtualBox
echo Installing VirtualBox...
winget install --id Oracle.VirtualBox --exact --accept-package-agreements --accept-source-agreements

:: 3. Verify installations
echo.
echo Verifying installations...

:: Check Vagrant version
for /f "delims=" %%A in ('vagrant --version 2^>nul') do set VAGRANT_VER=%%A

:: Check VirtualBox version
set "VBOX_PATH=C:\Program Files\Oracle\VirtualBox\vboxmanage.exe"
if exist "%VBOX_PATH%" (
    for /f "delims=" %%B in ('"%VBOX_PATH%" --version 2^>nul') do set VBOX_VER=%%B
)

if defined VAGRANT_VER (
    echo [✓] Vagrant installed: %VAGRANT_VER%
) else (
    echo [X] Vagrant installation failed!
)

if defined VBOX_VER (
    echo [✓] VirtualBox installed: %VBOX_VER%
) else (
    echo [X] VirtualBox installation failed!
)

echo.
echo Done with installations!

:: Create mininet-vm folder in user's Documents
set "MININET_VM_DIR=%USERPROFILE%\Documents\mininet-vm"
if not exist "%MININET_VM_DIR%" (
    mkdir "%MININET_VM_DIR%"
)

:: Download Vagrantfile from GitHub repo
echo Downloading Vagrantfile to %MININET_VM_DIR%...
powershell -Command "Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/socrates018/networks-2/main/Vagrantfile' -OutFile '%MININET_VM_DIR%\Vagrantfile'"

if exist "%MININET_VM_DIR%\Vagrantfile" (
    echo [✓] Vagrantfile downloaded successfully.
) else (
    echo [X] Failed to download Vagrantfile.
)

echo.
echo Done! Press any key to exit...
pause >nul
