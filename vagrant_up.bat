@echo off
cd "%USERPROFILE%\Documents\mininet-vm"
vagrant up
if errorlevel 1 (
    echo vagrant up failed.
    set /p choice="Type 'r' to run 'vagrant reload', or any other key to exit: "
    if /i "%choice%"=="r" (
        vagrant reload
    ) else (
        exit /b
    )
) else (
    vagrant ssh
)
