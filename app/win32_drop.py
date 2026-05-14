"""
Hermit Crab - Windows Shell Drag-and-Drop Support
Zero external dependencies, pure ctypes.
"""

import ctypes
from ctypes import wintypes

WM_DROPFILES = 0x0233

# On 64-bit Windows, WPARAM/LPARAM/LRESULT are pointer-sized (64-bit),
# but Python's wintypes defines them as 32-bit c_long/c_uint.
# That truncates pointers and causes access violations / overflows.
if ctypes.sizeof(ctypes.c_void_p) == 8:
    wintypes.WPARAM = ctypes.c_uint64
    wintypes.LPARAM = ctypes.c_int64
    wintypes.LRESULT = ctypes.c_int64

WNDPROC = ctypes.WINFUNCTYPE(
    wintypes.LRESULT,
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
)

# Set proper argtypes so ctypes passes 64-bit values, not truncated 32-bit
ctypes.windll.user32.CallWindowProcW.argtypes = [
    wintypes.WPARAM,  # lpPrevWndFunc (pointer)
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
]
ctypes.windll.user32.CallWindowProcW.restype = wintypes.LRESULT

ctypes.windll.user32.SetWindowLongPtrW.argtypes = [
    wintypes.HWND, ctypes.c_int, wintypes.LPARAM,
]
ctypes.windll.user32.SetWindowLongPtrW.restype = wintypes.LPARAM

ctypes.windll.user32.GetWindowLongPtrW.argtypes = [
    wintypes.HWND, ctypes.c_int,
]
ctypes.windll.user32.GetWindowLongPtrW.restype = wintypes.LPARAM

# shell32 drag-drop handles (HDROP = HANDLE = pointer-sized)
ctypes.windll.shell32.DragAcceptFiles.argtypes = [wintypes.HWND, ctypes.c_bool]
ctypes.windll.shell32.DragAcceptFiles.restype = None
ctypes.windll.shell32.DragQueryFileW.argtypes = [
    wintypes.WPARAM, ctypes.c_uint, wintypes.LPWSTR, ctypes.c_uint,
]
ctypes.windll.shell32.DragQueryFileW.restype = ctypes.c_uint
ctypes.windll.shell32.DragFinish.argtypes = [wintypes.WPARAM]
ctypes.windll.shell32.DragFinish.restype = None
