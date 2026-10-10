
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
window.events.shown += lambda: setattr(api, "_shown", True)

def js(expr):
    end = time.time() + 20; last = None
    while time.time() < end:
        try: v = window.evaluate_js(expr)
        except Exception as e: last = e; time.sleep(0.4); continue
        return v
    return f"TIMEOUT last={last!r}"

def steps():
    time.sleep(2)
    res = {}
    res["temp"] = js("document.getElementById('temp').textContent")
    res["title"] = js("document.title")
    res["bodyClass"] = js("document.body.className")
    res["frameStyle"] = js("JSON.stringify({l:document.getElementById('frame').style.left, t:document.getElementById('frame').style.top, w:document.getElementById('frame').style.width, h:document.getElementById('frame').style.height})")
    res["debug"] = js("JSON.stringify(window.__lc_debug && window.__lc_debug() || null)")
    res["lc_wall"] = js("typeof window.__lc_wall")
    res["gearExists"] = js("!!document.getElementById('gear')")
    res["modalOpenClass"] = js("document.getElementById('panelModal') ? document.getElementById('panelModal').className : 'NO-MODAL'")
    # click gear
    res["click"] = js("var g=document.getElementById('gear'); g ? (g.click(), 'clicked') : 'no gear'")
    time.sleep(0.6)
    res["modalOpenAfter"] = js("document.getElementById('panelModal').classList.contains('open')")
    # form values
    res["form"] = js("JSON.stringify({x:document.getElementById('pX').value, y:document.getElementById('pY').value, w:document.getElementById('pW').value, h:document.getElementById('pH').value})")
    # get_panel from JS (bridge)
    res["bridge_get"] = "window.pywebview.api.get_panel().then(r=>JSON.stringify(r))"
    res["bridge_get_res"] = None
    end = time.time()+15
    while res["bridge_get_res"] is None and time.time()<end:
        try:
            r = window.evaluate_js('window.pywebview.api.get_panel()')
            if r is not None: res["bridge_get_res"] = r if isinstance(r,str) else json.dumps(r)
        except Exception as e: last=e
        time.sleep(0.5)
    res["bridge_get_res"] = res["bridge_get_res"] or f"TIMEOUT"
    res["bridge_panel"] = "window.pywebview.api.get_panel().then(function(r){return JSON.stringify(r.panel)})"
    end = time.time()+15
    while res["bridge_panel"] and not str(res["bridge_panel"]).startswith("{") and time.time()<end:
        try: r = window.evaluate_js(res["bridge_panel"])
        except Exception: r=None
        if r is not None: res["bridge_panel"] = r if isinstance(r,str) else json.dumps(r)
        time.sleep(0.5)
    with open(r"C:\Users\amduc\lane-cove-weather\probe_dbg.json","w",encoding="utf-8") as f:
        json.dump(res,f,indent=1,default=str)
    P("done")
    time.sleep(0.4)
    try: window.destroy()
    except Exception: os._exit(0)

t = threading.Thread(target=steps, daemon=True); t.start()
time.sleep(1)
webview.start(debug=False)
