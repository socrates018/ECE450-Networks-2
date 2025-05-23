@echo off
setlocal EnableDelayedExpansion

:: Set Vagrant directory (universal for any user)
set "VAGRANT_DIR=%USERPROFILE%\Documents\mininet-vm"
if not exist "%VAGRANT_DIR%" (
    echo Vagrant directory "%VAGRANT_DIR%" does not exist.
    pause
    exit /b 1
)
cd /d "%VAGRANT_DIR%"

:: Set VAGRANTFILE variable before checking/updating
set "VAGRANTFILE=%VAGRANT_DIR%\Vagrantfile"

:: Set Vagrant bin path for new terminals
set "VAGRANT_INSTALL_DIR=%ProgramFiles%\Vagrant\bin"

set "STARTED_BY_SCRIPT=0"
set "SCRIPT_PATH=%~f0"
echo Starting Vagrant VM...
vagrant up
if errorlevel 1 (
    echo Vagrant up failed.
    goto ErrorHandler
)
set "STARTED_BY_SCRIPT=1"

:: Limit the number of times the script calls itself to 3
if "%1"=="" (
    set CALL_COUNT=1
) else (
    set CALL_COUNT=%1
)
if %CALL_COUNT% LSS 3 (
    set /a NEXT_CALL_COUNT=CALL_COUNT+1
    start "Vagrant SSH" cmd /c "%SCRIPT_PATH%" !NEXT_CALL_COUNT!
)

vagrant ssh -- -t "cd /vagrant; exec bash -l"
goto AfterSSH

:_ssh
vagrant ssh -- -t "cd /vagrant; exec bash -l"
goto :eof

:AfterSSH
:: Prompt to halt VM or SSH again after SSH (always prompt, no debug output)
echo.
echo [H]alt VM  [S]SH again  [E]xit
choice /c HSE /n /t 10 /d E /m "Press H to halt the VM, S to SSH again, or E to exit (auto close in 10s): "
if errorlevel 3 (
    exit
) else if errorlevel 2 (
    echo Reopening SSH session...
    vagrant ssh -- -t "cd /vagrant; exec bash -l"
    goto AfterSSH
) else if errorlevel 1 (
    echo Shutting down Vagrant VM...
    vagrant halt
    if errorlevel 1 (
        echo Failed to halt VM. Manually run 'vagrant halt'.
    ) else (
        echo VM halted successfully.
    )
    timeout /t 2 >nul
    exit
)

echo Done.
pause
goto :eof

:ErrorHandler
echo.
echo Error occurred during Vagrant operation.
:ErrorPrompt
echo.
echo [U]p debug  [R]eload  [S]SH again  [H]alt VM  [E]xit
choice /c URSHE /n /t 30 /d E /m "Press U for 'vagrant up --debug', R for 'vagrant reload', S for SSH again, H to halt VM, or E to exit (auto close in 30s): "
if errorlevel 5 (
    exit
)
if errorlevel 4 (
    echo Shutting down Vagrant VM...
    vagrant halt
    if errorlevel 1 (
        echo Failed to halt VM. Manually run 'vagrant halt'.
    ) else (
        echo VM halted successfully.
    )
    timeout /t 2 >nul
    exit /b
)
if errorlevel 3 (
    echo Reopening SSH session...
    vagrant ssh -- -t "cd /vagrant; exec bash -l"
    goto AfterSSH
)
if errorlevel 2 (
    echo Running 'vagrant reload'...
    echo Vagrant up failed.
    :: Kill all VirtualBox tasks before error handler
    taskkill /F /IM VBoxHeadless.exe >nul 2>&1
    taskkill /F /IM VirtualBoxVM.exe >nul 2>&1
    vagrant reload
    if errorlevel 1 (
        echo 'vagrant reload' failed.
        goto ErrorPrompt
    )
    goto :eof
)
if errorlevel 1 (
    echo Running 'vagrant up --debug'...
    echo Vagrant up failed.
    vagrant up --debug
    if errorlevel 1 (
        echo 'vagrant up --debug' failed.
        goto ErrorPrompt
    )
    goto :eof
)
:: If Enter is pressed (errorlevel 0), just close the terminal after 10s
exit
