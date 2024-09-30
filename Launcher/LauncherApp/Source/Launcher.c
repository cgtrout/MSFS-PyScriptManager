#include <stdio.h>
#include <stdlib.h>
#include <windows.h>  

// Function to run a Python script without showing the console window
int run_script(const char *pythonPath, const char *scriptPath) {
    char commandLine[512];
    
    // Preparing the command line
    printf("Preparing command line...\n");
    snprintf(commandLine, sizeof(commandLine), "\"%s\" \"%s\"", pythonPath, scriptPath);
    printf("Command line prepared: %s\n", commandLine);

    // Setup process and startup info
    STARTUPINFO si;
    PROCESS_INFORMATION pi;

    printf("Initializing STARTUPINFO and PROCESS_INFORMATION...\n");
    memset(&si, 0, sizeof(si));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;  // Hide the console window

    memset(&pi, 0, sizeof(pi));

    // Debug: check that fields are set correctly
    printf("STARTUPINFO.cb = %lu\n", si.cb);
    printf("STARTUPINFO.dwFlags = %lu\n", si.dwFlags);
    printf("STARTUPINFO.wShowWindow = %d\n", si.wShowWindow);

    // Create the process without showing the window
    printf("Creating process...\n");
    if (!CreateProcess(NULL, commandLine, NULL, NULL, 0, DETACHED_PROCESS, NULL, NULL, &si, &pi)) {
        printf("Error: CreateProcess failed. Error code: %lu\n", GetLastError());
        return -1;
    }

    printf("Process created successfully. Process ID: %lu\n", pi.dwProcessId);

    // Wait for the process to complete
    printf("Waiting for process to complete...\n");
    WaitForSingleObject(pi.hProcess, INFINITE);

    // Close process and thread handles
    printf("Closing process and thread handles...\n");
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);

    printf("Script executed successfully.\n");
    return 0;
}

int main() {
    // Detach console from parent
    FreeConsole();

    // Define paths for Python interpreter and script
    const char* pythonPath = ".\\WinPython\\python-3.13.0rc1.amd64\\pythonw.exe";
    const char* scriptPath = ".\\Launcher\\LauncherScript\\launcher.py";

    // Run the Python script without showing a window
    return run_script(pythonPath, scriptPath);
}
