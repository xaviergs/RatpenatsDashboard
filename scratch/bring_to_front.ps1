Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool IsIconic(IntPtr hWnd);
}
"@

$proc = Get-Process | Where-Object { $_.MainWindowTitle -like "*Antigravity IDE - Ratpenats*" } | Select-Object -First 1
if ($proc) {
    $hwnd = $proc.MainWindowHandle
    Write-Host "Found Antigravity IDE process with ID $($proc.Id) and handle $hwnd. Bringing to front..."
    if ([Win32]::IsIconic($hwnd)) {
        Write-Host "Window is minimized. Restoring..."
        [Win32]::ShowWindowAsync($hwnd, 9) | Out-Null # SW_RESTORE
    }
    [Win32]::ShowWindowAsync($hwnd, 5) | Out-Null # SW_SHOW
    $result = [Win32]::SetForegroundWindow($hwnd)
    Write-Host "SetForegroundWindow returned: $result"
} else {
    Write-Host "No process found matching '*Antigravity IDE - Ratpenats*'"
}
