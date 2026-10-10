
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

def P2(expr, wait=1.5):
    res_js = f"window.__probeResult = null; (async()=>{{ try {{ const r=await eval('{expr}'); window.__probeResult = r; }} catch(e) {{ window.__probeResult = 'PROBE_ERR:'+e; }} }})();"
    res_js = res_js.replace("'eval('","\"eval(\"")
    res_js = res_js.replace("eval(\"","eval(`").replace("`);",";` )")
    # Actually simpler: don't use backticks. The expression has no single-quotes
    res_js = f"window.__probeResult=null;(async()=>{{ try{{ const r=await (function(){{ return {expr}; }})(); window.__probeResult=r; }}catch(e){{ window.__probeResult='ERR:'+e; }} }})();"
    try: window.evaluate_js(res_js)
    except Exception as e: return f"JS_THROW:{e}"
    time.sleep(wait)
    try: return window.evaluate_js("window.__probeResult")
    except: return "GET_ERR"

def steps():
    time.sleep(2.5)
    window.evaluate_js("window.__probeResult=null")
    res = {}
    # check for early JS errors (capture window.onerror)
    window.evaluate_js("window.__jserr=null; window.addEventListener('error', function(e){ window.__jserr = e.message + ' @' + e.lineno; });")
    res["jserr_early"] = P2("window.__jserr", 0.3)
    # does openPanelModal exist globally?
    res["openFn_global"] = P2("typeof window.openPanelModal", 0.3)
    res["closeFn_global"] = P2("typeof window.closePanelModal", 0.3)
    res["saveFn_global"] = P2("typeof window.savePanel", 0.3)
    # gear element
    res["gear"] = P2("!!document.getElementById('gear')", 0.3)
    res["modal"] = P2("!!document.getElementById('panelModal')", 0.3)
    # click gear
    res["click"] = P2("document.getElementById('gear').click(); 'clicked'", 0.8)
    res["modal_class"] = P2("document.getElementById('panelModal').className", 0.5)
    res["jserr_after_click"] = P2("window.__jserr", 0.3)
    res["pX_val"] = P2("document.getElementById('pX').value", 0.3)
    res["pW_val"] = P2("document.getElementById('pW').value", 0.3)
    res["presets"] = P2("Array.from(document.querySelectorAll('#presetRow .chip')).map(c=>c.dataset.preset).join(',')", 0.3)
    res["note"] = P2("document.getElementById('mNote').textContent.slice(0,80)", 0.3)
    res["mApply"] = P2("document.getElementById('mApply').textContent", 0.3)
    # try calling openPanelModal directly (if it's not global, we need different approach)
    res["call_open_fn"] = P2("typeof openPanelModal!=='undefined' ? (openPanelModal(),'called') : 'not global'", 0.8)
    res["modal_class2"] = P2("document.getElementById('panelModal').className", 0.5)
    res["pX_val2"] = P2("document.getElementById('pX').value", 0.3)

    # Try to expose functions to global scope for testing
    res["expose_test"] = P2("(function(){ if(typeof openPanelModal!=='undefined'){ window.__openPanelModal=openPanelModal; window.__closePanelModal=closePanelModal; return 'exposed'; } return 'cannot-expose'; })()", 0.5)

    with open(r"C:\Users\amduc\lane-cove-weather\probe_dbg4.json","w",encoding="utf-8") as f:
        json.dump(res, f, indent=1, default=str)
    P("done")
    time.sleep(0.5)
    try: window.destroy()
    except: os._exit(0)

t = threading.Thread(target=steps, daemon=True); t.start()
time.sleep(1)
webview.start(debug=False)
