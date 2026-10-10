import ctypes, json, os, re, subprocess, sys, threading, time
from pathlib import Path

APP_DIR = Path(r"C:\Users\amduc\lane-cove-weather")
PY      = APP_DIR / "venv" / "Scripts" / "python.exe"

class RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                ("r", ctypes.c_long), ("b", ctypes.c_long)]

import ctypes as C
u32 = C.windll.user32

def primary_work_area() -> tuple[int, int, int, int]:
    r = RECT(); SystemParametersInfoW = u32.SystemParametersInfoW
    SystemParametersInfoW(0x0030, 0, C.byref(r), 0)
    return (r.l, r.t, r.r - r.l, r.b - r.t)

def monitors() -> list[tuple[int, int, int, int]]:
    out = []
    CB  = C.WINFUNCTYPE(C.c_int, C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p)
    class MONITORINFOEXW(C.Structure):
        _fields_ = [("cbSize", C.c_uint), ("szDevice", C.c_wchar * 32),
                    ("rcMonitor", RECT), ("rcWork", RECT)]
    def cb(hmon, herr, lprec, _d):
        mi = MONITORINFOEXW(); mi.cbSize = C.sizeof(MONITORINFOEXW)
        MonitorInfoFromHmon = u32.GetMonitorInfoW
        MonitorInfoFromHmon(hmon, mi)
        w, h = mi.rcWork.right - mi.rcWork.left, mi.rcWork.bottom - mi.rcWork.top
        out.append((mi.rcWork.left, mi.rcWork.top, w, h))
        return 1
    u32.EnumDisplayMonitors(None, None, CB(cb), 0)
    return out

wa = primary_work_area()
print("work area:", wa)
print("monitors:", monitors())

# --- quick py_compile check of app.py ---
r = subprocess.run([str(PY), "-m", "py_compile", str(APP_DIR / "app.py")], capture_output=True, text=True)
print("py_compile rc:", r.returncode, (r.stderr or "")[:400])

# --- quick import check (catches syntax errors & import-time crashes) ---
sys.path.insert(0, str(APP_DIR))
# Stub out webview import so we can load app.py without launching
import types
webview = types.ModuleType("webview")
webview.create_window = lambda *a, **k: None
webview.start = lambda *a, **k: None
webview.windows = []
sys.modules["webview"] = webview
import app as lcapp
print("module loaded, main exists:", callable(lcapp.main))
print("settings path:", getattr(lcapp, "SETTINGS_PATH", None))
