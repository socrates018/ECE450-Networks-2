@echo off
setlocal enabledelayedexpansion
set PREFIX=3581_
set DESTDIR=%USERPROFILE%\Downloads\temp
if not exist "%DESTDIR%" mkdir "%DESTDIR%"
for %%F in (*) do (
    if not "%%~xF"==".bat" (
        set "FILENAME=%%~nF"
        copy "%%F" "%DESTDIR%\!PREFIX!!FILENAME!.txt" >nul
    )
)
