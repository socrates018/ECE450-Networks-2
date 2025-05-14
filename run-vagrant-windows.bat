@echo off
setlocal EnableDelayedExpansion

:: Check for admin rights, relaunch as admin if not
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
if '%errorlevel%' NEQ '0' (
    echo Requesting administrative privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:: Ensure Vagrant is in PATH for this session
set "VAGRANT_INSTALL_DIR=%ProgramFiles%\Vagrant\bin"
echo %PATH% | find /I "%VAGRANT_INSTALL_DIR%" >nul
if errorlevel 1 (
    set "PATH=%VAGRANT_INSTALL_DIR%;%PATH%"
)

:: Ensure %LOCALAPPDATA%\Temp exists
if not exist "%LOCALAPPDATA%\Temp" (
    mkdir "%LOCALAPPDATA%\Temp"
)

:: Ensure C:\tmp exists
if not exist "C:\tmp" (
    mkdir "C:\tmp"
)

:: Set Vagrant directory (universal for any user)
set "VAGRANT_DIR=%USERPROFILE%\Documents\mininet-vm"
if not exist "%VAGRANT_DIR%" (
    echo Vagrant directory "%VAGRANT_DIR%" does not exist.
    pause
    exit /b 1
)
cd /d "%VAGRANT_DIR%"

:: Check VM status
for /f "tokens=4 delims=," %%A in ('vagrant status --machine-readable ^| findstr /c:",state,"') do (
    set "VM_STATUS=%%A"
)
if not defined VM_STATUS (
    set "VM_STATUS=not_created"
)

set "STARTED_BY_SCRIPT=0"
if /I not "%VM_STATUS%"=="running" (
    echo Starting Vagrant VM...
    vagrant up
    if errorlevel 1 (
        echo Vagrant up failed.
        goto ErrorHandler
    )
    set "STARTED_BY_SCRIPT=1"
) else (
    echo Vagrant VM already running.
)

:: Connect via SSH
echo Connecting to VM...
vagrant ssh -- -t "cd /vagrant; if [ -n \"$BASH_VERSION\" ]; then exec bash -l; else exec sh; fi"
set SSH_EXITCODE=%ERRORLEVEL%

:: Prompt to halt VM after SSH (always prompt, no debug output)
echo.
choice /c YN /n /m "Do you want to halt the VM? [Y]es  [N]o (default Yes): "
if errorlevel 2 (
    echo VM left running.
) else (
    echo Shutting down Vagrant VM...
    vagrant halt
    if errorlevel 1 (
        echo Failed to halt VM. Manually run 'vagrant halt'.
    ) else (
        echo VM halted successfully.
    )
    timeout /t 2 >nul
)

echo Done.
goto :eof

:ErrorHandler
echo.
echo Error occurred during Vagrant operation.
:ErrorPrompt
echo.
echo [U]p debug  [R]eload  [Enter] Exit
choice /c UR /n /m "Press U for 'vagrant up --debug', R for 'vagrant reload', or Enter to exit: "
if errorlevel 2 (
    echo Running 'vagrant reload'...
    vagrant reload
    goto :eof
)
if errorlevel 1 (
    echo Running 'vagrant up --debug'...
    vagrant up --debug
    goto :eof
)
:: If Enter is pressed (errorlevel 0), just exit
goto :eof
