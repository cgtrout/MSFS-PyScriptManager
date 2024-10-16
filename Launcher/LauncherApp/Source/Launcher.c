#include <stdio.h>
#include <stdlib.h>
#include <windows.h>

// Define types for function pointers to dynamically load Windows API functions.
typedef HWND (*GetConsoleWindow_t)(void);
typedef BOOL (*ShowWindow_t)(HWND, int);
typedef BOOL (*SetForegroundWindow_t)(HWND);

// Load necessary functions from kernel32.dll and user32.dll to manage console window behavior.
// Returns TRUE if all functions are successfully loaded, otherwise FALSE.
BOOL loadConsoleFunctions(GetConsoleWindow_t* getConsoleWindow, ShowWindow_t* showWindow, SetForegroundWindow_t* setForegroundWindow) {
    HMODULE kernel32 = GetModuleHandle("kernel32.dll");
    HMODULE user32 = LoadLibrary("user32.dll");

    // Check if the DLLs were successfully loaded
    if (!kernel32 || !user32) return FALSE;

    // Retrieve the function addresses and assign them to the function pointers.
    *getConsoleWindow = (GetConsoleWindow_t)GetProcAddress(kernel32, "GetConsoleWindow");
    *showWindow = (ShowWindow_t)GetProcAddress(user32, "ShowWindow");
    *setForegroundWindow = (SetForegroundWindow_t)GetProcAddress(user32, "SetForegroundWindow");

    // Return TRUE only if all functions were successfully loaded.
    return *getConsoleWindow && *showWindow && *setForegroundWindow;
}

// Print an error message and restore the console window if it was minimized.
void displayErrorAndRestoreConsole(const char* message, HWND hConsole, ShowWindow_t showWindow) {
    printf("Error: %s Error code: %lu\n", message, GetLastError());
    if (hConsole) showWindow(hConsole, SW_RESTORE);
}

// Execute a Python script using the specified interpreter path and script file path.
// Returns the exit code from the Python process, or -1 if there was an error.
int run_script(const char *pythonPath, const char *scriptPath) {
    char commandLine[512];
    // Prepare the command line for launching the Python script.
    snprintf(commandLine, sizeof(commandLine), "\"%s\" -u \"%s\"", pythonPath, scriptPath);

    printf("MSFS-PyScriptManager: Loader exe\n");
    printf("-------------------------------------------------------------------------------------------\n\n");

    GetConsoleWindow_t getConsoleWindow;
    ShowWindow_t showWindow;
    SetForegroundWindow_t setForegroundWindow;

    // Load console window management functions.
    if (!loadConsoleFunctions(&getConsoleWindow, &showWindow, &setForegroundWindow)) {
        printf("Error: Could not load necessary functions for managing the console window.\n");
        return -1;
    }

    HWND hConsole = getConsoleWindow();
    if (!hConsole) {
        displayErrorAndRestoreConsole("Could not get console window handle.", NULL, NULL);
        return -1;
    }

    // Set up pipes for redirecting the output from the Python process back to the console.
    HANDLE hReadPipe, hWritePipe;
    SECURITY_ATTRIBUTES sa = { sizeof(SECURITY_ATTRIBUTES), NULL, TRUE };
    if (!CreatePipe(&hReadPipe, &hWritePipe, &sa, 0) || !SetHandleInformation(hReadPipe, HANDLE_FLAG_INHERIT, 0)) {
        displayErrorAndRestoreConsole("Failed to create or configure pipe.", hConsole, showWindow);
        return -1;
    }

    STARTUPINFO si = { sizeof(si), 0 };
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdOutput = si.hStdError = hWritePipe;
    PROCESS_INFORMATION pi = { 0 };

    printf("Launching Python script: %s\n", scriptPath);
    // Launch the Python process and check if it was successful.
    if (!CreateProcess(NULL, commandLine, NULL, NULL, TRUE, 0, NULL, NULL, &si, &pi)) {
        displayErrorAndRestoreConsole("CreateProcess failed.", hConsole, showWindow);
        CloseHandle(hReadPipe); 
        CloseHandle(hWritePipe);
        return -1;
    }

    // Bring the console window to the foreground and minimize it.
    setForegroundWindow(hConsole);
    Sleep(100);
    showWindow(hConsole, SW_MINIMIZE);

    // Close the write end of the pipe as it's no longer needed.
    CloseHandle(hWritePipe);
    printf("Reading Python script output...\n\n");
    printf("Keep this window open to monitor launcher.py output, otherwise it is safe to close.\n");
    printf("-------------------------------------------------------------------------------------------\n\n");
    
    // Buffer to hold the output from the Python script.
    char buffer[4096];
    DWORD bytesRead;
    DWORD availableBytes;

    // Continuously read from the pipe until the Python process completes.
    while (1) {
        // Peek to check if there is any data available.
        if (!PeekNamedPipe(hReadPipe, NULL, 0, NULL, &availableBytes, NULL)) {
            // Exit loop if there's an error or if the pipe is closed.
            break;
        }

        // If data is available, read it.
        if (availableBytes > 0) {
            if (ReadFile(hReadPipe, buffer, min(sizeof(buffer) - 1, availableBytes), &bytesRead, NULL) && bytesRead > 0) {
                buffer[bytesRead] = '\0'; // Null-terminate the output.
                printf("%s", buffer);     // Print the output to the console.
            }
        } else {
            // Sleep briefly to avoid excessive CPU usage in case of slow output.
            Sleep(50);
        }
    }

    // Wait for the Python process to finish and retrieve its exit code.
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD exitCode;
    GetExitCodeProcess(pi.hProcess, &exitCode);
    if (exitCode != 0) {
        // If the Python script failed, restore the console window and display the error code.
        showWindow(hConsole, SW_RESTORE);
        printf("\nPython script exited with error code: %lu\n", exitCode);
    } else {
        printf("Python script completed successfully.\n");
    }

    // Clean up and release resources.
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    CloseHandle(hReadPipe);
    FreeLibrary(GetModuleHandle("user32.dll"));

    return exitCode;
}

int main() {
    // Specify the path to the Python interpreter and the script to be executed.
    const char* pythonPath = ".\\WinPython\\python-3.13.0rc1.amd64\\pythonw.exe";
    const char* scriptPath = ".\\Launcher\\LauncherScript\\launcher.py";

    // Run the Python script and retrieve the exit code.
    int result = run_script(pythonPath, scriptPath);

    // If there was an error, prompt the user to press a key before exiting.
    if (result != 0) {
        printf("Press any key to exit...\n");
        getchar();
    }

    return result;
}