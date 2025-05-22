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
    set /p num="How many Windows Terminal windows to open with vagrant ssh? (default 2): "
    if "%num%"=="" set num=2
    vagrant ssh
    :ssh_prompt
    set /a others=num-1
    if %others% gtr 0 (
        for /l %%i in (1,1,%others%) do (
            start wt vagrant ssh
        )
    )
    set /p action="Type 'e' to exit, 'h' to halt the VM, or 's' to ssh again: "
    if /i "%action%"=="e" (
        exit /b
    ) else if /i "%action%"=="h" (
        vagrant halt
        exit /b
    ) else if /i "%action%"=="s" (
        vagrant ssh
        goto ssh_prompt
    ) else (
        goto ssh_prompt
    )
)
pause

