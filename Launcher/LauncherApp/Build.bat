@echo off
REM Save the current directory
set "original_dir=%CD%"

REM Initialize the status variable
set "status="

REM Construct the full path to the TinyCC executable relative to the batch file
set "tcc_path=%~dp0tcc\tcc.exe"

REM Verify if tcc.exe exists
if not exist "%tcc_path%" (
    echo Error: Could not find tcc.exe at "%tcc_path%".
    pause
    exit /b 1
)

REM Change directory to the Source folder where main.c is located
cd Source

REM Compile the C program using TinyCC
"%tcc_path%" launcher.c -o ..\..\..\MSFS-PyScriptManager.exe 2>&1 | findstr /i "error"
if %errorlevel% equ 0 (
    set "status=failed"
    goto :cleanup
)

REM Set success status if no errors occurred
set "status=success"

:cleanup
REM Navigate back to the original directory
cd "%original_dir%"

REM Handle status-specific messages
if "%status%"=="failed" (
    echo Compilation failed. See the error above.
    pause
    exit /b 1
) else (
    echo Compilation complete. The launcher has been created in the main directory.
)
