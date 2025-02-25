#include <stdio.h>
#include <stdlib.h>
#include <windows.h>
#include <time.h>

// Define types for function pointers to dynamically load Windows API functions.
typedef HWND (*GetConsoleWindow_t)(void);
typedef BOOL (*ShowWindow_t)(HWND, int);
typedef BOOL (*SetForegroundWindow_t)(HWND);

// Load necessary functions from kernel32.dll and user32.dll to manage console window behavior.
// Returns TRUE if all functions are successfully loaded, otherwise FALSE.
BOOL loadConsoleFunctions(GetConsoleWindow_t *getConsoleWindow, ShowWindow_t *showWindow, SetForegroundWindow_t *setForegroundWindow)
{
    HMODULE kernel32 = GetModuleHandle("kernel32.dll");
    HMODULE user32 = LoadLibrary("user32.dll");

    // Check if the DLLs were successfully loaded
    if (!kernel32 || !user32)
        return FALSE;

    // Retrieve the function addresses and assign them to the function pointers.
    *getConsoleWindow = (GetConsoleWindow_t)GetProcAddress(kernel32, "GetConsoleWindow");
    *showWindow = (ShowWindow_t)GetProcAddress(user32, "ShowWindow");
    *setForegroundWindow = (SetForegroundWindow_t)GetProcAddress(user32, "SetForegroundWindow");

    // Return TRUE only if all functions were successfully loaded.
    return *getConsoleWindow && *showWindow && *setForegroundWindow;
}

// Print an error message and restore the console window if it was minimized.
void displayErrorAndRestoreConsole(const char *message, HWND hConsole, ShowWindow_t showWindow)
{
    printf("Error: %s Error code: %lu\n", message, GetLastError());
    if (hConsole)
        showWindow(hConsole, SW_RESTORE);
}

// Global handle for the shutdown pipe
HANDLE g_hCommandPipe = NULL;

// Console control handler to send a shutdown signal to the Python script.
BOOL WINAPI ConsoleHandler(DWORD dwCtrlType)
{
    if (dwCtrlType == CTRL_CLOSE_EVENT || dwCtrlType == CTRL_C_EVENT || dwCtrlType == CTRL_SHUTDOWN_EVENT)
    {
        if (g_hCommandPipe)
        {
            const char *shutdownMessage = "shutdown\n";
            DWORD bytesWritten;
            WriteFile(g_hCommandPipe, shutdownMessage, strlen(shutdownMessage), &bytesWritten, NULL);
            CloseHandle(g_hCommandPipe);
            g_hCommandPipe = NULL;
        }
        return TRUE; // Prevent further handling
    }
    return FALSE;
}

// Processes data from the inbound pipe, sends periodic heartbeats, and monitors the
// Python process.
void processPipeDataLoop(HANDLE hInboundPipe, HANDLE hCommandPipe, PROCESS_INFORMATION *pi)
{
    char buffer[4096];
    DWORD bytesRead;
    DWORD lastHeartbeatTime = GetTickCount(); // Track the last time a heartbeat was sent
    const DWORD heartbeatInterval = 1000;    // Send heartbeat every 1 second
    const char *heartbeatMessage = "HEARTBEAT\n";

    while (1)
    {
        // Check if data is available in the pipe
        DWORD bytesAvailable = 0;
        BOOL hasData = PeekNamedPipe(hInboundPipe, NULL, 0, NULL, &bytesAvailable, NULL);

        if (hasData && bytesAvailable > 0)
        {
            // Read the available data
            BOOL result = ReadFile(hInboundPipe, buffer, sizeof(buffer) - 1, &bytesRead, NULL);
            if (result && bytesRead > 0)
            {
                buffer[bytesRead] = '\0'; // Null-terminate the string
                printf("%s", buffer);    // Display the script's output
            }
        }

        // Send a heartbeat command periodically
        DWORD currentTime = GetTickCount();
        if (currentTime - lastHeartbeatTime >= heartbeatInterval)
        {
            DWORD bytesWritten;
            if (!WriteFile(g_hCommandPipe, heartbeatMessage, strlen(heartbeatMessage), &bytesWritten, NULL))
            {
                printf("[ERROR] Failed to send heartbeat. Error: %lu\n", GetLastError());
            }
            lastHeartbeatTime = currentTime;
        }

        // Check if the Python process has exited
        if (WaitForSingleObject(pi->hProcess, 0) == WAIT_OBJECT_0)
        {
            printf("[INFO] Python process has exited.\n");
            break;
        }

        Sleep(10);
    }
}

// Creates a named pipe with a unique name and specified access mode.
HANDLE createNamedPipe(
    const char *pipePrefix,         // Prefix for the pipe name
    DWORD pid,                      // Process ID to include in the pipe name for uniqueness
    int randomSuffix,               // Random number to further ensure uniqueness of the pipe name
    DWORD accessMode,               // Access mode (e.g., PIPE_ACCESS_INBOUND or PIPE_ACCESS_OUTBOUND)
    char *pipeNameBuffer,           // Buffer to store the generated pipe name
    size_t pipeNameBufferSize,      // Size of the pipeNameBuffer
    SECURITY_ATTRIBUTES *sa,        // Pointer to SECURITY_ATTRIBUTES for the pipe
    HWND hConsole,                  // Handle to the console window (for error handling and restoration)
    ShowWindow_t showWindow         // Function pointer to ShowWindow for console management
) {
    // Generate a unique pipe name
    snprintf(pipeNameBuffer, pipeNameBufferSize, "\\\\.\\pipe\\%s_%lu_%d", pipePrefix, pid, randomSuffix);

    HANDLE pipeHandle = CreateNamedPipe(
        pipeNameBuffer,           // Pipe name
        accessMode,               // Access mode (e.g., read-only or write-only)
        PIPE_TYPE_BYTE | PIPE_WAIT, // Byte stream pipe, blocking mode
        1,                        // Max instances
        4096,                     // Output buffer size
        4096,                     // Input buffer size
        0,                        // Default timeout
        sa                        // Security attributes
    );

    if (pipeHandle == INVALID_HANDLE_VALUE)
    {
        char errorMessage[256];
        snprintf(errorMessage, sizeof(errorMessage), "Failed to create named pipe: %s", pipeNameBuffer);
        displayErrorAndRestoreConsole(errorMessage, hConsole, showWindow);
    }

    return pipeHandle;
}

// Execute a Python script using the specified interpreter path and script file path
// Returns the exit code from the Python process, or -1 if there was an error
int run_script(const char *pythonPath, const char *scriptPath)
{
    char commandLine[512];
    snprintf(commandLine, sizeof(commandLine), "\"%s\" -u \"%s\"", pythonPath, scriptPath);

    printf("MSFS-PyScriptManager: Loader exe\n");
    printf("-------------------------------------------------------------------------------------------\n\n");

    // Load console window management functions
    GetConsoleWindow_t getConsoleWindow;
    ShowWindow_t showWindow;
    SetForegroundWindow_t setForegroundWindow;

    if (!loadConsoleFunctions(&getConsoleWindow, &showWindow, &setForegroundWindow))
    {
        printf("Error: Could not load necessary functions for managing the console window.\n");
        return -1;
    }

    // Retrieve the console window handle
    HWND hConsole = getConsoleWindow();
    if (!hConsole)
    {
        displayErrorAndRestoreConsole("Could not get console window handle.", NULL, NULL);
        return -1;
    }

    // Minimize the console window
    Sleep(100); // Allow time for the operation to take effect

    // Declare and initialize SECURITY_ATTRIBUTES
    SECURITY_ATTRIBUTES sa = {0};
    sa.nLength = sizeof(sa);
    sa.bInheritHandle = TRUE;
    sa.lpSecurityDescriptor = NULL;

    // Generate a unique pipe name using process ID and timestamp
    DWORD pid = GetCurrentProcessId();
    srand((unsigned int)time(NULL)); // Seed the random number generator
    int randomSuffix = rand();       // Generate a random number

    // Buffers to store pipe names
    char scriptOutputPipeName[256];
    char scriptCommandPipeName[256];

    // Create the stdout inbound pipe
    HANDLE hInboundPipe = createNamedPipe(
        "PythonOutputPipe",        // Pipe prefix
        pid,                       // Process ID
        randomSuffix,              // Random suffix
        PIPE_ACCESS_INBOUND,       // Read-only access
        scriptOutputPipeName,      // Output: pipe name
        sizeof(scriptOutputPipeName),
        &sa,                       // Pass SECURITY_ATTRIBUTES
        hConsole,                  // Console handle
        showWindow                 // ShowWindow function pointer
    );

    if (hInboundPipe == INVALID_HANDLE_VALUE)
    {
        return -1; // Exit if the pipe couldn't be created
    }

    // Create shutdown pipe
    g_hCommandPipe = createNamedPipe(
        "PythonShutdownPipe",      // Pipe prefix
        pid,                       // Process ID
        randomSuffix,              // Random suffix
        PIPE_ACCESS_OUTBOUND,      // Write-only access
        scriptCommandPipeName,     // Output: pipe name
        sizeof(scriptCommandPipeName),
        &sa,                       // Pass SECURITY_ATTRIBUTES
        hConsole,                  // Console handle
        showWindow                 // ShowWindow function pointer
    );

    if (g_hCommandPipe == INVALID_HANDLE_VALUE)
    {
        CloseHandle(hInboundPipe);
        return -1; // Exit if the pipe couldn't be created
    }

    // Pass the pipe names as arguments to the Python script
    snprintf(commandLine, sizeof(commandLine),
             "\"%s\" -u \"%s\" --output-pipe \"%s\" --shutdown-pipe \"%s\"",
             pythonPath, scriptPath, scriptOutputPipeName, scriptCommandPipeName);

    STARTUPINFO si = {sizeof(si), 0};
    si.dwFlags = STARTF_USESTDHANDLES;

    si.hStdOutput = CreateFile(
        scriptOutputPipeName,
        GENERIC_WRITE,
        0,
        &sa,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        NULL);
    si.hStdError = si.hStdOutput;

    if (si.hStdOutput == INVALID_HANDLE_VALUE)
    {
        displayErrorAndRestoreConsole("Failed to open named pipe for the Python process.", hConsole, showWindow);
        CloseHandle(hInboundPipe);
        CloseHandle(g_hCommandPipe);
        return -1;
    }

    PROCESS_INFORMATION pi = {0};

    // Launch the Python process
    if (!CreateProcess(NULL, commandLine, NULL, NULL, TRUE, 0, NULL, NULL, &si, &pi))
    {
        displayErrorAndRestoreConsole("CreateProcess failed.", hConsole, showWindow);
        CloseHandle(hInboundPipe);
        CloseHandle(g_hCommandPipe);
        CloseHandle(si.hStdOutput);
        return -1;
    }

    // Close the write handle in the parent process
    CloseHandle(si.hStdOutput);

    printf("Reading Python script output...\n\n");
    printf("NOTE: Closing this window will close MSFS-PyScriptManager\n");
    printf("-------------------------------------------------------------------------------------------\n\n");

    // Wait for the client to connect
    printf("Waiting for Launcher...\n");
    BOOL connected = ConnectNamedPipe(g_hCommandPipe, NULL) || GetLastError() == ERROR_PIPE_CONNECTED;
    if (!connected)
    {
        displayErrorAndRestoreConsole("Failed to connect to shutdown named pipe.", hConsole, showWindow);
        CloseHandle(hInboundPipe);
        return -1;
    }

    // Now, explicitly connect the output pipe after launching the process:
    BOOL connectedOutput = ConnectNamedPipe(hInboundPipe, NULL) ||
                           (GetLastError() == ERROR_PIPE_CONNECTED);
    if (!connectedOutput)
    {
        displayErrorAndRestoreConsole("Failed to connect to output named pipe.", hConsole, showWindow);
        CloseHandle(hInboundPipe);
        // Clean up shutdown pipe if needed...
        return -1;
    }

    printf("Launcher connected\n");

    // Bring the console window to the foreground and minimize it
    setForegroundWindow(hConsole);
    Sleep(100);
    showWindow(hConsole, SW_MINIMIZE);

    // MAIN LOOP - Process data from inbound and outbound pipes
    processPipeDataLoop(hInboundPipe, g_hCommandPipe, &pi);

    // Wait for the Python process to complete
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD exitCode;
    GetExitCodeProcess(pi.hProcess, &exitCode);

    if (exitCode != 0)
    {
        showWindow(hConsole, SW_RESTORE);
        printf("\nPython script exited with error code: %lu\n", exitCode);
    }
    else
    {
        printf("Python script completed successfully.\n");
    }

    // Clean up
    CloseHandle(hInboundPipe);
    if (g_hCommandPipe)
    {
        CloseHandle(g_hCommandPipe);
    }
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);

    return exitCode;
}

int main()
{
    // Specify the path to the Python interpreter and the script to be executed.
    const char *pythonPath = ".\\WinPython\\python-3.13.0rc1.amd64\\pythonw.exe";
    const char *scriptPath = ".\\Launcher\\LauncherScript\\launcher.py";

    // Register the console control handler
    SetConsoleCtrlHandler(ConsoleHandler, TRUE);

    // Run the Python script and retrieve the exit code.
    int result = run_script(pythonPath, scriptPath);

    // If there was an error, prompt the user to press a key before exiting.
    if (result != 0)
    {
        printf("Press any key to exit...\n");
        getchar();
    }

    return result;
}
