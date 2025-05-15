@echo off
setlocal

:: ===== CONFIGURATION =====
set "REPO_URL=https://github.com/socrates018/networks-2.git"
set "LOCAL_SOURCE=C:\Users\socra\Documents\mininet-vm"
set "CLONE_DIR=%~dp0GitHubClone"
set "COMMIT_MSG=Added local project files"
:: ==========================

:: Clean previous clone (if exists)
if exist "%CLONE_DIR%" (
    echo Removing old clone...
    rmdir /s /q "%CLONE_DIR%"
)

:: Clone GitHub repo
echo Cloning %REPO_URL% into %CLONE_DIR% ...
git clone "%REPO_URL%" "%CLONE_DIR%"
if errorlevel 1 (
    echo Failed to clone repository. Check your REPO_URL.
    pause
    exit /b
)

:: Copy files from local folder into clone, EXCLUDING build/binary folders
echo Copying files from %LOCAL_SOURCE% (excluding .pio, build, binaries) ...
robocopy "%LOCAL_SOURCE%" "%CLONE_DIR%" /E /XD .pio build __pycache__ /XF *.bin *.elf *.hex *.exe *.o *.obj *.pyc

:: Note:
:: This script does NOT push the .git folder from your local source.
:: Only the files copied into the fresh clone (%CLONE_DIR%) are staged and pushed.
:: The .git folder in %CLONE_DIR% is the one created by 'git clone' and is used for all git operations.
:: Your local project's .git (if any) is ignored and never pushed.

:: Change to clone directory
cd /d "%CLONE_DIR%"

:: Configure Git for large files and timeouts
git config http.postBuffer 1048576000
git config http.maxRequestBuffer 500M
git config http.lowSpeedLimit 0
git config http.lowSpeedTime 999999
git config http.sslVerify false
git config core.compression 0
git config --global credential.helper wincred

:: Setup .gitignore to avoid pushing build files and binaries
echo Creating/updating .gitignore ...
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

:: Remove ignored/build files from clone directory before commit
:: (Optional, as robocopy should already exclude them)
rmdir /s /q ".pio" 2>nul
rmdir /s /q "build" 2>nul
rmdir /s /q "__pycache__" 2>nul
del /s /q *.bin *.elf *.hex *.exe *.o *.obj *.pyc 2>nul

:: Initialize git lfs if available
where git-lfs >nul 2>nul
if %errorlevel%==0 (
    git lfs install
    git lfs track "*.bin" "*.elf" "*.hex"
) else (
    echo WARNING: git-lfs not found. Large binaries may fail to push.
)

:: === USER EDIT PHASE ===
echo.
echo ==========================================================
echo You may now make changes in:
echo   %CLONE_DIR%
echo When you are ready to upload your changes, press ENTER...
echo ==========================================================
pause

:: Stage, commit and push only changed files
git add .
git commit -m "%COMMIT_MSG%"

:: Push with increased buffer size, retry if fails
set "PUSH_SUCCESS=0"
for /l %%i in (1,1,3) do (
    echo Attempt %%i to push...
    git -c http.postBuffer=1048576000 -c http.maxRequestBuffer=500M -c core.compression=0 push --no-verify
    if not errorlevel 1 (
        set "PUSH_SUCCESS=1"
        goto :push_done
    )
    echo Push failed, retrying in 10 seconds...
    timeout /t 10 >nul
)
:push_done

if "%PUSH_SUCCESS%"=="0" (
    echo.
    echo ERROR: git push failed after 3 attempts.
    echo Try:
    echo   - Checking your internet connection.
    echo   - Using SSH instead of HTTPS for remote URL.
    echo   - Running 'git lfs install' and 'git lfs track' if pushing large files.
    echo   - Increasing http.postBuffer even more.
    echo   - Pushing smaller commits.
    pause
    exit /b 1
)

echo.
echo Done! Files from %CLONE_DIR% have been pushed to GitHub.
pause

:: Clean up temporary clone directory
echo Cleaning up temporary folder: %CLONE_DIR% ...
cd /d "%~dp0"
rmdir /s /q "%CLONE_DIR%" 2>nul

endlocal
