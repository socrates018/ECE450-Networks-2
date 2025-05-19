@echo off
setlocal

:: ===== CONFIGURATION =====
set "REPO_URL=https://github.com/socrates018/networks-2.git"
set "LOCAL_SOURCE=C:\Users\socra\Documents\mininet-vm"
set "CLONE_DIR=%~dp0GitHubClone"
set "DOWNLOADS_CLONE=%USERPROFILE%\Downloads\networks-2"
set "COMMIT_MSG=Auto-mirror: updated local project files"
:: ==========================

echo.
echo [M] Mirror mininet-vm into GitHub
echo [C] Clone repo into Downloads, edit, then upload
choice /c MC /n /m "Choose: [M]irror or [C]lone and edit: "
set "MODE=%ERRORLEVEL%"

if "%MODE%"=="1" (
    :: MIRROR MODE
    if exist "%CLONE_DIR%" (
        rmdir /s /q "%CLONE_DIR%"
    )
    git clone "%REPO_URL%" "%CLONE_DIR%"
    if errorlevel 1 (
        echo Failed to clone repository. Check your REPO_URL.
        exit /b
    )
    cd /d "%CLONE_DIR%"
    :: Delete everything except .git
    for /f "delims=" %%f in ('dir /a /b') do (
        if /i not "%%f"==".git" (
            rmdir /s /q "%%f" 2>nul
            del /f /q "%%f" 2>nul
        )
    )
    :: Copy everything from mininet-vm into the clone (excluding .pio, build, binaries)
    robocopy "%LOCAL_SOURCE%" "%CLONE_DIR%" /E /XD .pio build __pycache__ /XF *.bin *.elf *.hex *.exe *.o *.obj *.pyc >nul
    (
        echo .pio/
        echo build/
        echo *.bin
        echo *.elf
        echo *.hex
        echo *.exe
        echo *.o
        echo *.obj
        echo *.pyc
        echo __pycache__/
    ) > .gitignore
    rmdir /s /q ".pio" 2>nul
    rmdir /s /q "build" 2>nul
    rmdir /s /q "__pycache__" 2>nul
    del /s /q *.bin *.elf *.hex *.exe *.o *.obj *.pyc 2>nul
    git add -A
    git commit -m "%COMMIT_MSG%"
    git -c http.postBuffer=1048576000 -c http.maxRequestBuffer=500M -c core.compression=0 push --no-verify
    cd /d "%~dp0"
    rmdir /s /q "%CLONE_DIR%" 2>nul
    echo.
    echo Mirror complete and pushed to GitHub.
    exit /b
)

if "%MODE%"=="2" (
    :: CLONE-AND-EDIT MODE
    if exist "%DOWNLOADS_CLONE%" (
        rmdir /s /q "%DOWNLOADS_CLONE%"
    )
    git clone "%REPO_URL%" "%DOWNLOADS_CLONE%"
    if errorlevel 1 (
        echo Failed to clone repository. Check your REPO_URL.
        exit /b
    )
    echo.
    echo ==========================================================
    echo You may now make changes in:
    echo   %DOWNLOADS_CLONE%
    echo When you are ready to upload your changes, press ENTER...
    echo ==========================================================
    pause
    cd /d "%DOWNLOADS_CLONE%"
    git add .
    git diff --cached --quiet
    if errorlevel 1 (
        git commit -m "%COMMIT_MSG%"
        git -c http.postBuffer=1048576000 -c http.maxRequestBuffer=500M -c core.compression=0 push --no-verify
    )
    echo.
    echo Changes from Downloads clone pushed to GitHub.
    exit /b
)

endlocal
