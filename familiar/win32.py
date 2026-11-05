"""Win32 plumbing: per-pixel-alpha layered window, never takes focus. Windows only for now."""
import ctypes, ctypes.wintypes as W

# ---------------------------------------------------------------- Win32 plumbing
user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)

class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", W.UINT), ("style", W.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", W.HINSTANCE), ("hIcon", W.HICON), ("hCursor", W.HANDLE),
                ("hbrBackground", W.HBRUSH), ("lpszMenuName", W.LPCWSTR), ("lpszClassName", W.LPCWSTR), ("hIconSm", W.HICON)]

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", W.DWORD), ("biWidth", W.LONG), ("biHeight", W.LONG), ("biPlanes", W.WORD), ("biBitCount", W.WORD),
                ("biCompression", W.DWORD), ("biSizeImage", W.DWORD), ("biXPelsPerMeter", W.LONG), ("biYPelsPerMeter", W.LONG),
                ("biClrUsed", W.DWORD), ("biClrImportant", W.DWORD)]

class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", W.DWORD * 3)]

class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte), ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]

class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", W.DWORD), ("rcMonitor", W.RECT), ("rcWork", W.RECT), ("dwFlags", W.DWORD)]

class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", W.UINT), ("dwTime", W.DWORD)]

class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", W.DWORD), ("dwMemoryLoad", W.DWORD), ("ullTotalPhys", ctypes.c_uint64), ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64), ("ullAvailPageFile", ctypes.c_uint64), ("ullTotalVirtual", ctypes.c_uint64),
                ("ullAvailVirtual", ctypes.c_uint64), ("ullAvailExtendedVirtual", ctypes.c_uint64)]

def ram_gb():
    m = MEMORYSTATUSEX(); m.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys / 2**30, m.ullTotalPhys / 2**30

def sig(fn, args, res=None):
    fn.argtypes = args
    if res is not None:
        fn.restype = res

sig(user32.DefWindowProcW, [W.HWND, W.UINT, W.WPARAM, W.LPARAM], LRESULT)
sig(user32.RegisterClassExW, [ctypes.POINTER(WNDCLASSEXW)], W.ATOM)
sig(user32.CreateWindowExW, [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                             W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID], W.HWND)
sig(user32.UpdateLayeredWindow, [W.HWND, W.HDC, ctypes.POINTER(W.POINT), ctypes.POINTER(W.SIZE), W.HDC, ctypes.POINTER(W.POINT),
                                 W.DWORD, ctypes.POINTER(BLENDFUNCTION), W.DWORD], W.BOOL)
sig(user32.GetDC, [W.HWND], W.HDC)
sig(user32.ReleaseDC, [W.HWND, W.HDC], ctypes.c_int)
sig(user32.SetTimer, [W.HWND, ctypes.c_size_t, W.UINT, ctypes.c_void_p], ctypes.c_size_t)
sig(user32.GetMessageW, [ctypes.POINTER(W.MSG), W.HWND, W.UINT, W.UINT], W.BOOL)
sig(user32.TranslateMessage, [ctypes.POINTER(W.MSG)], W.BOOL)
sig(user32.DispatchMessageW, [ctypes.POINTER(W.MSG)], LRESULT)
sig(user32.CreatePopupMenu, [], W.HMENU)
sig(user32.AppendMenuW, [W.HMENU, W.UINT, ctypes.c_size_t, W.LPCWSTR], W.BOOL)
sig(user32.TrackPopupMenu, [W.HMENU, W.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.HWND, ctypes.c_void_p], ctypes.c_int)
sig(user32.DestroyMenu, [W.HMENU], W.BOOL)
sig(user32.GetCursorPos, [ctypes.POINTER(W.POINT)], W.BOOL)
sig(user32.SetCapture, [W.HWND], W.HWND)
sig(user32.ReleaseCapture, [], W.BOOL)
sig(user32.ShowWindow, [W.HWND, ctypes.c_int], W.BOOL)
sig(user32.SetWindowPos, [W.HWND, W.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.UINT], W.BOOL)
sig(user32.SetForegroundWindow, [W.HWND], W.BOOL)
sig(user32.GetForegroundWindow, [], W.HWND)
sig(user32.GetWindowRect, [W.HWND, ctypes.POINTER(W.RECT)], W.BOOL)
sig(user32.GetClassNameW, [W.HWND, W.LPWSTR, ctypes.c_int], ctypes.c_int)
sig(user32.MonitorFromWindow, [W.HWND, W.DWORD], W.HMONITOR)
sig(user32.MonitorFromPoint, [W.POINT, W.DWORD], W.HMONITOR)
sig(user32.GetMonitorInfoW, [W.HMONITOR, ctypes.POINTER(MONITORINFO)], W.BOOL)
sig(user32.GetLastInputInfo, [ctypes.POINTER(LASTINPUTINFO)], W.BOOL)
sig(user32.PostQuitMessage, [ctypes.c_int], None)
sig(user32.PostMessageW, [W.HWND, W.UINT, W.WPARAM, W.LPARAM], W.BOOL)
sig(user32.DestroyWindow, [W.HWND], W.BOOL)
sig(user32.LoadCursorW, [W.HINSTANCE, ctypes.c_void_p], W.HANDLE)
sig(gdi32.CreateCompatibleDC, [W.HDC], W.HDC)
sig(gdi32.CreateDIBSection, [W.HDC, ctypes.POINTER(BITMAPINFO), W.UINT, ctypes.POINTER(ctypes.c_void_p), W.HANDLE, W.DWORD], W.HBITMAP)
sig(gdi32.SelectObject, [W.HDC, W.HGDIOBJ], W.HGDIOBJ)
sig(gdi32.DeleteObject, [W.HGDIOBJ], W.BOOL)
sig(gdi32.DeleteDC, [W.HDC], W.BOOL)
sig(kernel32.GetModuleHandleW, [W.LPCWSTR], W.HMODULE)
sig(kernel32.CreateMutexW, [ctypes.c_void_p, W.BOOL, W.LPCWSTR], W.HANDLE)
sig(kernel32.GetTickCount, [], W.DWORD)

WM_DESTROY, WM_CLOSE, WM_TIMER, WM_MOUSEACTIVATE = 0x0002, 0x0010, 0x0113, 0x0021
WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_RBUTTONUP = 0x0200, 0x0201, 0x0202, 0x0205
EX = 0x00080000 | 0x00000008 | 0x00000080 | 0x08000000  # LAYERED | TOPMOST | TOOLWINDOW | NOACTIVATE
WS_POPUP = 0x80000000
SWP = 0x0001 | 0x0002 | 0x0010  # NOSIZE | NOMOVE | NOACTIVATE
HWND_TOPMOST = W.HWND(-1)

def idle_s():
    li = LASTINPUTINFO(); li.cbSize = ctypes.sizeof(LASTINPUTINFO)
    user32.GetLastInputInfo(ctypes.byref(li))
    return ((kernel32.GetTickCount() - li.dwTime) & 0xFFFFFFFF) / 1000.0

def monitor_info(hmon):
    mi = MONITORINFO(); mi.cbSize = ctypes.sizeof(MONITORINFO)
    user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
    return mi

