@echo off

REM Prompt the user to confirm they want to proceed
echo This script will zip the contents of the WinPython directory and delete the directory afterwards - intended only for preparing a release.
choice /m "Do you want to continue?" /n

REM Check the user's choice
if errorlevel 2 (
    echo Exiting without changes.
    exit /b 0
)

REM Check if 7za.exe exists directly up one directory in Lib\7z
if not exist "%~dp0..\Lib\7z\7za.exe" (
    echo 7za.exe not found at "%~dp0..\Lib\7z\7za.exe". Exiting.
    exit /b 1
) else (
    echo Found 7za.exe at "%~dp0..\Lib\7z\7za.exe".
)

REM Navigate to the root directory of MSFS-PyScriptManager by moving up three directories
cd /d "%~dp0..\..\..\"

REM Print the current directory to confirm
echo Current directory after navigation: %cd%

REM Verify that the WinPython directory exists in the root directory
if not exist "WinPython" (
    echo WinPython directory not found in %cd%. Exiting.
    exit /b 1
)

REM Navigate into the WinPython directory to archive its contents only
cd WinPython

REM Zip the contents into WinPython.7z at the parent level, without including the folder itself
echo Zipping contents of WinPython directory...
"%~dp0..\Lib\7z\7za.exe" a -t7z "..\WinPython.7z" *

REM Return to the root directory
cd ..

REM Check if zipping was successful
if %errorlevel% equ 0 (
    echo Zipping successful. Deleting WinPython directory...
    rd /s /q WinPython
) else (
    echo Zipping failed. WinPython directory will not be deleted.
)

echo Done.
pause
