
import sys, os, json, time, threading, ctypes
sys.path.insert(0, r"C:\Users\amduc\lane-cove-weather")
os.chdir(r"C:\Users\amduc\lane-cove-weather")
sys.argv = ["app.py"]                      # panel mode
import importlib
if "app" in sys.modules: del sys.modules["app"]
import app as A

results = {}
import webview
store_n = A.NewsStore(); gallery_n = A.GalleryStore()
api = A.API(A.Store(), store_n, gallery_n)

work  = A._work_area()
panel = A._panel_from_settings()
window = webview.create_window(
    "Lane Cove Weather + News",
    x=panel["x"], y=panel["y"], width=panel["w"], height=panel["h"],
    min_size=(A.PANEL_MIN_W, A.PANEL_MIN_H), resizable=True, easy_drag=True,
    url=A.HTML_PATH, text_select=False, background_color="#06070c", js_api=api)
api._win = window; api._wall = False

t = threading.Thread(target=webview.start, kwargs={"debug": False}, daemon=True)
t.start()

def js(expr, tries=40):
    for i in range(tries):
        try:
            v = window.evaluate_js(expr)
            if v is not None:
                return v
        except Exception as e:
            last = e
        time.sleep(0.5)
    raise RuntimeError(f"js timeout: {expr!r} last={last!r}")

# 1) bridge visible to JS
v = js("window.pywebview && typeof window.pywebview.api.get_panel === 'function'")
print("bridge.get_panel visible:", v); assert v is True

# 2) panel data round-trips from JS side
v = js("window.pywebview.api.get_panel().then(r => JSON.stringify(r))")
print("JS get_panel:", v)

# 3) modal plumbing: open + fill + preset + save
v = js("""
(function(){
  const out = {};
  const M = document.getElementById('panelModal');
  const open = document.getElementById('mOpenProbe'); // none
  out.modal = !!M;
  out.chips = document.querySelectorAll('#presetRow .chip').length;
  out.inputs = ['pX','pY','pW','pH','pScale','modeSel','mApply'].every(id => !!document.getElementById(id));
  // simulate opening
  document.getElementById('gear').click();
  out.opened = M.classList.contains('open');
  // form populated?
  out.formFilled = ['pX','pY','pW','pH'].every(id => +document.getElementById(id).value > 0);
  out.modeSel = document.getElementById('modeSel').value;
  return JSON.stringify(out);
})()
""")
print("modal probe:", v)

# 4) preset click updates form then reverts (no save yet)
v = js("""
(function(){
  document.querySelector('#presetRow .chip[data-preset=right]').click();
  const w = +document.getElementById('pW').value;
  const h = +document.getElementById('pH').value;
  const x = +document.getElementById('pX').value;
  return JSON.stringify({w, h, x});
})()
""")
print("preset 'right' =>", v)

# 5) end-to-end save through the modal Apply (stays in panel mode -> doSave path)
v = js("""
window.pywebview.api.get_panel().then(()=>window.pywebview.api.save_panel(400, 200, 940, 700))
.then(r => JSON.stringify(r))
""")
print("save_panel(400,200,940,700):", v)
disk = json.load(open(r"C:\Users\amduc\lane-cove-weather\settings.json", encoding="utf-8"))
print("on disk:", disk)
assert disk["panel"] == {"x":400,"y":200,"w":940,"h":700}

# 6) is_wall_mode from JS
v = js("window.pywebview.api.is_wall_mode().then(x => String(x))")
print("is_wall_mode JS:", v); assert v == "False"

# 7) live resize effect on the actual window (save_panel moves it)
time.sleep(1.2)
user32 = ctypes.windll.user32
hwnd = user32.FindWindowW(None, "Lane Cove Weather + News")
print("hwnd:", hex(hwnd or 0)); assert hwnd
class RECT(ctypes.Structure):
    _fields_ = [("l",ctypes.c_long),("t",ctypes.c_long),("r",ctypes.c_long),("b",ctypes.c_long)]
r = RECT(); user32.GetWindowRect(hwnd, ctypes.byref(r))
print("window rect:", r.l, r.t, r.r-r.l, r.b-r.t)

# 8) __lc_wall hook exists
v = js("typeof window.__lc_wall")
print("__lc_wall:", v); assert v == "function"

# 9) weather still loads while settings system is active
v = js("document.getElementById('temp').textContent")
print("temp rendered:", v)

# 10) quit
v = js("window.pywebview.api.quit_app().then(r=>JSON.stringify(r))")
print("quit_app:", v)
time.sleep(1.2)
print("PANEL-MODE GUI PROBE DONE")
