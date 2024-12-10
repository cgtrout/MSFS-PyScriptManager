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

// Execute a Python script using the specified interpreter path and script file path
// Returns the exit code from the Python process, or -1 if there was an error
int run_script(const char *pythonPath, const char *scriptPath) {
    char commandLine[512];
    snprintf(commandLine, sizeof(commandLine), "\"%s\" -u \"%s\"", pythonPath, scriptPath);

    printf("MSFS-PyScriptManager: Loader exe\n");
    printf("-------------------------------------------------------------------------------------------\n\n");

    // Load console window management functions
    GetConsoleWindow_t getConsoleWindow;
    ShowWindow_t showWindow;
    SetForegroundWindow_t setForegroundWindow;

    if (!loadConsoleFunctions(&getConsoleWindow, &showWindow, &setForegroundWindow)) {
        printf("Error: Could not load necessary functions for managing the console window.\n");
        return -1;
    }

    // Retrieve the console window handle
    HWND hConsole = getConsoleWindow();
    if (!hConsole) {
        displayErrorAndRestoreConsole("Could not get console window handle.", NULL, NULL);
        return -1;
    }

    // Minimize the console window
    Sleep(100); // Allow time for the operation to take effect

    // Set up a named pipe for redirecting the output from the Python process
    SECURITY_ATTRIBUTES sa = {0};
    sa.nLength = sizeof(sa);
    sa.bInheritHandle = TRUE;
    sa.lpSecurityDescriptor = NULL;

    const char *pipeName = "\\\\.\\pipe\\PythonOutputPipe";
    HANDLE hNamedPipe = CreateNamedPipe(
        pipeName,                 // Pipe name
        PIPE_ACCESS_INBOUND,      // Read-only pipe
        PIPE_TYPE_BYTE | PIPE_WAIT, // Byte stream pipe, blocking mode
        1,                        // Max instances
        4096,                     // Output buffer size
        4096,                     // Input buffer size
        0,                        // Default timeout
        &sa                       // Security attributes
    );

    if (hNamedPipe == INVALID_HANDLE_VALUE) {
        displayErrorAndRestoreConsole("Failed to create named pipe.", hConsole, showWindow);
        return -1;
    }

    STARTUPINFO si = { sizeof(si), 0 };
    si.dwFlags = STARTF_USESTDHANDLES;

    si.hStdOutput = CreateFile(
        pipeName,
        GENERIC_WRITE,
        0,
        &sa,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        NULL
    );
    si.hStdError = si.hStdOutput;

    if (si.hStdOutput == INVALID_HANDLE_VALUE) {
        displayErrorAndRestoreConsole("Failed to open named pipe for the Python process.", hConsole, showWindow);
        CloseHandle(hNamedPipe);
        return -1;
    }

    PROCESS_INFORMATION pi = { 0 };

    // Launch the Python process
    if (!CreateProcess(NULL, commandLine, NULL, NULL, TRUE, 0, NULL, NULL, &si, &pi)) {
        displayErrorAndRestoreConsole("CreateProcess failed.", hConsole, showWindow);
        CloseHandle(hNamedPipe);
        CloseHandle(si.hStdOutput);
        return -1;
    }

    // Close the write handle in the parent process
    CloseHandle(si.hStdOutput);

    // Read the Python process's output
    printf("Reading Python script output...\n\n");
    printf("Keep this window open to monitor launcher.py output, otherwise it is safe to close.\n");
    printf("-------------------------------------------------------------------------------------------\n\n");

    // Bring the console window to the foreground and minimize it
    setForegroundWindow(hConsole);
    Sleep(100);
    showWindow(hConsole, SW_MINIMIZE);

    char buffer[4096];
    DWORD bytesRead;

    while (1) {
        BOOL result = ReadFile(hNamedPipe, buffer, sizeof(buffer) - 1, &bytesRead, NULL);
        if (!result || bytesRead == 0) break;

        buffer[bytesRead] = '\0';
        printf("%s", buffer);
    }

    // Wait for the Python process to complete
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD exitCode;
    GetExitCodeProcess(pi.hProcess, &exitCode);

    if (exitCode != 0) {
        showWindow(hConsole, SW_RESTORE);
        printf("\nPython script exited with error code: %lu\n", exitCode);
    } else {
        printf("Python script completed successfully.\n");
    }

    // Clean up
    CloseHandle(hNamedPipe);
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);

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