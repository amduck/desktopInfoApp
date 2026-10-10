
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

# Pure-sync helper: evaluate JS expr (which may be a Promise), store result in window.__probeResult
PROBE_JS_INIT = r"""
window.__probeResult = null;
window.__probing = false;
async function __probe(expr){
  return await eval(expr);
}
"""
def PJS(expr):
    """Poll-probe: run an expr (can be a Promise) and get the resolved result.
    Uses the __probeResult pattern for async, synchronous for sync."""
    # wrap: if the expr is async and returns a Promise, we need to .then() it
    wrapped_js = f"__probe({expr}).then(r => {window_name}.__probeResult = r);"
    end = time.time() + 20
    while time.time() < end:
        try:
            window.evaluate_js(wrapped_js)
        except Exception:
            pass
        time.sleep(0.2)
        try:
            v = window.evaluate_js("window.__probeResult")
            if v is not None: return v
        except Exception:
            pass
    return "TIMEOUT"

window_name = "window"  # for reference in the JS string
PJS.__globals__["__probeResult"] = "window.__probeResult"  # hack to define in namespace

def steps():
    time.sleep(2.5)
    res = {}

    init_js = """
    window.__probeResult = null;
    async function __probe(expr){ return await eval(expr); }
    'ready';
    """
    try: window.evaluate_js(init_js)
    except Exception: pass

    def P2(expr, wait=1.5):
        expr_clean = expr.strip().rstrip(';')
        res_js = f"window.__probeResult = null; (async()=>{{ const r=await eval(`{expr_clean}`); window.__probeResult = r; }})();"
        res_js = res_js.replace('`{', '`(').replace('}`', ')`')
        try: window.evaluate_js(res_js)
        except Exception as e: return f"PROBE_ERR:{e}"
        time.sleep(wait)
        try: return window.evaluate_js("window.__probeResult")
        except Exception as e: return f"GET_ERR:{e}"

    res["0_ready"] = P2("document.readyState", 0.5)
    res["1_temp"] = P2("document.getElementById('temp').textContent", 0.5)
    res["1_body"] = P2("document.body.className", 0.5)
    res["2_bridge_sync"] = P2("typeof window.pywebview.api.get_panel", 0.5)
    res["3_get_panel"] = P2("window.pywebview.api.get_panel()", 0.5)
    # gear
    res["4_click_gear"] = P2("document.getElementById('gear').click(); 'ok'", 0.5)
    time.sleep(0.6)
    res["5_modal_open"] = P2("document.getElementById('panelModal').classList.contains('open')", 0.5)
    res["6_form"] = P2("JSON.stringify({x:pX.value,y:pY.value,w:pW.value,h:pH.value,mode:modeSel.value})"
                       " + ' chips:' + document.querySelectorAll('#presetRow .chip').length", 0.5)
    res["7_note"] = P2("mNote.textContent.slice(0,90)", 0.5)
    # preset right
    res["8_preset_right"] = P2("document.querySelector('.chip[data-preset=right]').click(); "
                               "JSON.stringify({x:+pX.value,w:+pW.value,h:+pH.value})", 0.5)
    # save_panel via bridge
    res["9_save"] = P2("window.pywebview.api.save_panel(520,100,860,640)", 0.5)
    res["10_get_after"] = P2("window.pywebview.api.get_panel()", 0.5)
    res["11_wall"] = P2("window.pywebview.api.is_wall_mode()", 0.5)
    res["12_lc_debug"] = P2("JSON.stringify(window.__lc_debug && __lc_debug() || null)", 0.5)

    with open(r"C:\Users\amduc\lane-cove-weather\probe_dbg3.json","w",encoding="utf-8") as f:
        json.dump(res,f,indent=1,default=str)
    P("PROBE DONE rc=0")
    time.sleep(0.5)
    try: window.destroy()
    except Exception: os._exit(0)

t = threading.Thread(target=steps, daemon=True); t.start()
time.sleep(1)
import os as _os
try: webview.start(debug=False)
except Exception as e: P("start exited:", e)
