@echo off
REM Set the path to the TinyCC compiler
set PATH=%CD%\tcc;%PATH%

REM Change directory to the Source folder where main.c is located
cd Source

@echo on
REM Compile the C program using TinyCC
tcc launcher.c -o ..\..\..\MSFS-PyScriptManager.exe
@echo off

REM Navigate back to the LauncherApp folder
cd ..

REM Notify the user that compilation is complete
echo Compilation complete. The launcher has been created in the main directory.

