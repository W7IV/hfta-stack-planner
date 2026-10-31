/*
 * HFTA Stack Planner standalone launcher (Windows, no installation).
 * MIT License, copyright (c) 2026 W7IV.
 *
 * Starts only the bundled Python runtime. No shell, downloaded scripts,
 * installation, elevation or network listener beyond local Flask.
 *
 * Unsigned native EXEs can still be blocked by Smart App Control.
 * This launcher is not a substitute for trusted Authenticode signing.
 */
#define UNICODE
#define _UNICODE
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <shellapi.h>
#include <stdio.h>
#include <wchar.h>

#define PATH_CAP 32768

static wchar_t root[PATH_CAP];
static wchar_t python_exe[PATH_CAP];
static wchar_t script_path[PATH_CAP];
static wchar_t command_line[PATH_CAP];
static wchar_t data_dir[PATH_CAP];
static wchar_t project_dir[PATH_CAP];
static wchar_t temp_path[PATH_CAP];

static int join(wchar_t *out, const wchar_t *base, const wchar_t *suffix) {
    int n = swprintf(out, PATH_CAP, L"%ls\\%ls", base, suffix);
    return n >= 0 && n < PATH_CAP;
}

static int exists_file(const wchar_t *path) {
    DWORD a = GetFileAttributesW(path);
    return a != INVALID_FILE_ATTRIBUTES && !(a & FILE_ATTRIBUTE_DIRECTORY);
}

static int make_dir(const wchar_t *path) {
    return CreateDirectoryW(path, NULL) || GetLastError() == ERROR_ALREADY_EXISTS;
}

static int env_path(const wchar_t *key, const wchar_t *suffix) {
    if (!join(temp_path, root, suffix)) return 0;
    return SetEnvironmentVariableW(key, temp_path);
}

static int server_listening(void) {
    SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    struct sockaddr_in addr;
    int ok;
    if (s == INVALID_SOCKET) return 0;
    addr.sin_family = AF_INET;
    addr.sin_port = htons(5055);
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    ok = connect(s, (const struct sockaddr *)&addr, sizeof(addr)) == 0;
    closesocket(s);
    return ok;
}

static void open_when_ready(HANDLE child) {
    WSADATA ws;
    DWORD status;
    wchar_t no_browser[8];
    unsigned i;

    if (GetEnvironmentVariableW(L"HFTA_NO_BROWSER", no_browser, 8) > 0 &&
        wcscmp(no_browser, L"1") == 0) return;
    if (WSAStartup(MAKEWORD(2,2), &ws) != 0) return;

    for (i = 0; i < 120; ++i) {
        if (!GetExitCodeProcess(child, &status) || status != STILL_ACTIVE) break;
        if (server_listening()) {
            ShellExecuteW(NULL, L"open", L"http://127.0.0.1:5055/",
                          NULL, NULL, SW_SHOWNORMAL);
            WSACleanup();
            return;
        }
        Sleep(250);
    }
    WSACleanup();
    wprintf(L"Open http://127.0.0.1:5055/ in your browser if the server starts.\n");
}

int wmain(void) {
    DWORD n = GetModuleFileNameW(NULL, root, PATH_CAP);
    wchar_t *slash;
    STARTUPINFOW startup = {0};
    PROCESS_INFORMATION child = {0};
    DWORD exit_code = 1;

    if (n == 0 || n >= PATH_CAP) {
        fwprintf(stderr, L"Cannot determine the launcher location.\n");
        return 1;
    }
    slash = wcsrchr(root, L'\\');
    if (!slash) {
        fwprintf(stderr, L"Launcher must reside in the application folder.\n");
        return 1;
    }
    *slash = L'\0';

    if (!join(python_exe, root, L"runtime\\python.exe") ||
        !join(script_path, root, L"app\\app.py") ||
        !join(data_dir, root, L"data") ||
        !join(project_dir, root, L"data\\projects")) {
        fwprintf(stderr, L"Application path is too long.\n");
        return 1;
    }
    if (!exists_file(python_exe) || !exists_file(script_path)) {
        fwprintf(stderr, L"Missing bundled runtime or application. Extract the complete ZIP before starting.\n");
        return 1;
    }
    if (!make_dir(data_dir) || !make_dir(project_dir) ||
        !env_path(L"OPENHFTA_DIR", L"openhfta") ||
        !env_path(L"OPENHFTA_LIB", L"openhfta\\OpenYTWCore.dll") ||
        !env_path(L"PROJECTS_DIR", L"data\\projects") ||
        !env_path(L"VOACAPL", L"voacap\\bin\\voacapl.exe") ||
        !env_path(L"ITSHFBC", L"voacap\\itshfbc") ||
        !SetEnvironmentVariableW(L"PORT", L"5055") ||
        !SetEnvironmentVariableW(L"HOST", L"127.0.0.1") ||
        !SetEnvironmentVariableW(L"PYTHONDONTWRITEBYTECODE", L"1")) {
        fwprintf(stderr, L"Cannot initialize the local application folder or settings. Windows error %lu.\n",
                 GetLastError());
        return 1;
    }

    /* Explicit executable path avoids PATH searches and command interpreters. */
    if (swprintf(command_line, PATH_CAP, L"\"%ls\" \"%ls\"", python_exe, script_path) < 0) {
        fwprintf(stderr, L"Command path is too long.\n");
        return 1;
    }
    startup.cb = sizeof(startup);
    wprintf(L"HFTA Stack Planner starting on this computer only.\n");
    wprintf(L"Keep this window open while the planner is running.\n");
    wprintf(L"Local URL: http://127.0.0.1:5055/\n");
    fflush(stdout);

    if (!CreateProcessW(python_exe, command_line, NULL, NULL, FALSE, 0,
                        NULL, root, &startup, &child)) {
        fwprintf(stderr, L"Could not start bundled Python. Windows error %lu.\n", GetLastError());
        wprintf(L"Press Enter to close.\n");
        (void)getchar();
        return 1;
    }

    open_when_ready(child.hProcess);
    WaitForSingleObject(child.hProcess, INFINITE);
    GetExitCodeProcess(child.hProcess, &exit_code);
    CloseHandle(child.hThread);
    CloseHandle(child.hProcess);
    if (exit_code != 0) {
        wprintf(L"The planner exited with code %lu. Review the messages above.\n", exit_code);
        wprintf(L"Press Enter to close.\n");
        (void)getchar();
    }
    return (int)exit_code;
}
