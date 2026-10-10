
import sys, os, json, time, threading
sys.path.insert(0, r"C:\Users\amduc\lane-cove-weather")
os.chdir(r"C:\Users\amduc\lane-cove-weather")
sys.argv = ["app.py"]
import app as A
import webview
def P(*a): print(*a, file=sys.stderr, flush=True)

api = A.API(A.Store(), A.NewsStore(), A.GalleryStore())
panel = A._panel_from_settings()
window = webview.create_window("Lane Cove Weather + News", x=panel["x"], y=panel["y"],
    width=panel["w"], height=panel["h"], min_size=(A.PANEL_MIN_W, A.PANEL_MIN_H),
    resizable=True, easy_drag=True, url=A.HTML_PATH, text_select=False,
    background_color="#06070c", js_api=api)
api._win = window

def js(expr, timeout=15):
    got = {"v": None}
    def cb(v): got["v"] = v
    end = time.time()+timeout
    while time.time() < end:
        try: window.evaluate_js(expr, cb)
        except Exception as e:
            if isinstance(e, dict): return e   # pywebview rethrown JS error
            time.sleep(0.4); continue
        time.sleep(0.3)
        if got["v"] is not None: return got["v"]
    return "TIMEOUT"

def steps():
    time.sleep(2)
    res = {}
    res["temp"] = js("document.getElementById('temp').textContent")
    res["bodyClass"] = js("document.body.className")
    res["debug"] = js("__lc_debug && JSON.stringify(__lc_debug()) || 'null'")
    res["bridge_get_panel"] = js("window.pywebview.api.get_panel()")
    res["frameStyle_before"] = js("JSON.stringify({l:frame.style.left, t:frame.style.top, w:frame.style.width, h:frame.style.height})")
    # click gear and check modal
    res["click"] = js("document.getElementById('gear').click()")
    time.sleep(0.5)
    res["modalOpen"] = js("document.getElementById('panelModal').classList.contains('open')")
    res["form"] = js("JSON.stringify({x:pX.value, y:pY.value, w:pW.value, h:pH.value, mode:modeSel.value, note:mNote.textContent.slice(0,80)})")
    res["chips"] = js("document.querySelectorAll('#presetRow .chip').length")
    with open(r"C:\Users\amduc\lane-cove-weather\probe_dbg2.json","w",encoding="utf-8") as f:
        json.dump(res,f,indent=1,default=str)
    P("done")
    time.sleep(0.4)
    try: window.destroy()
    except Exception: os._exit(0)

t = threading.Thread(target=steps, daemon=True); t.start()
time.sleep(1)
webview.start(debug=False)
