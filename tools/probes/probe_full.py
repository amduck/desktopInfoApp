
import sys, os, json, time, threading
sys.path.insert(0, r"C:\Users\amduc\lane-cove-weather")
os.chdir(r"C:\Users\amduc\lane-cove-weather")
sys.argv = ["app.py"]
import app as A
import webview
def P(*a):
    print(*a, file=sys.stderr, flush=True)
    sys.stderr.flush()

threading.Timer(55, lambda: os._exit(3)).start()   # hard watchdog
api = A.API(A.Store(), A.NewsStore(), A.GalleryStore())
panel = A._panel_from_settings()
P("starting window")
window = webview.create_window("Lane Cove Weather + News", x=panel["x"], y=panel["y"],
    width=panel["w"], height=panel["h"], min_size=(A.PANEL_MIN_W, A.PANEL_MIN_H),
    resizable=True, easy_drag=True, url=A.HTML_PATH, text_select=False,
    background_color="#06070c", js_api=api)
api._win = window

def P2(expr, wait=1.6, retries=3):
    for attempt in range(retries):
        window.evaluate_js("window.__probeResult=null")
        js = f"(async()=>{{ try{{ window.__probeResult = await ({expr}); }}catch(e){{ window.__probeResult = 'ERR: '+e.message; }} }})();"
        try: window.evaluate_js(js)
        except Exception as e: P("  P2 throw:", e)
        time.sleep(wait)
        v = window.evaluate_js("window.__probeResult")
        if v is not None: return v
        P(f"  P2 attempt {attempt}: still None, expr={expr[:60]}")
    return "UNSET"

RES = r"C:\Users\amduc\lane-cove-weather\probe_full.json"
def steps():
    time.sleep(2.5)
    P("T0 ready check")
    out = {}
    out["T0"] = P2("document.readyState")
    out["T1_temp"] = P2("document.getElementById('temp').textContent")
    out["T2_bridge"] = P2("typeof window.pywebview.api.get_panel")

    # open modal, check it's populated
    out["T3_open"] = P2("(document.getElementById('gear').click(), document.getElementById('panelModal').classList.contains('open'))")
    P("  T3_open =", out["T3_open"])
    out["T3_filled"] = P2("JSON.stringify({x:+pX.value,y:+pY.value,w:+pW.value,h:+pH.value,mode:modeSel.value,note:mNote.textContent.slice(0,60)})")
    P("  T3_filled =", out["T3_filled"])

    # preset chips
    out["T4_left"]   = P2("(document.querySelector('.chip[data-preset=left]').click(), JSON.stringify({x:+pX.value,y:+pY.value,w:+pW.value,h:+pH.value}))")
    out["T4_right"]  = P2("(document.querySelector('.chip[data-preset=right]').click(), JSON.stringify({x:+pX.value,y:+pY.value,w:+pW.value,h:+pH.value}))")
    out["T4_center"] = P2("(document.querySelector('.chip[data-preset=center]').click(), JSON.stringify({x:+pX.value,y:+pY.value,w:+pW.value,h:+pH.value}))")
    out["T4_full"]   = P2("(document.querySelector('.chip[data-preset=full]').click(), JSON.stringify({x:+pX.value,y:+pY.value,w:+pW.value,h:+pH.value}))")
    P("  presets OK:", out["T4_left"][:50], "…")

    # resize slider
    out["T5_scale"] = P2("(pScale.value=640, pScale.dispatchEvent(new Event('input')), JSON.stringify({w:+pW.value,h:+pH.value}))")
    P("  T5_scale =", out["T5_scale"])

    # explicit size
    out["T6_entry"] = P2("(pW.value=900, pW.dispatchEvent(new Event('input')), pH.value=700, pH.dispatchEvent(new Event('input')), JSON.stringify({w:+pW.value,h:+pH.value}))")
    P("  T6_entry =", out["T6_entry"])

    # set exact coords, then Apply
    P2("(pX.value=432, pY.value=96, pW.value=880, pH.value=630, 'set')", wait=0.5)
    time.sleep(0.3)
    out["T7_apply"] = P2("(mApply.click(), 'clicked')", wait=0.5)
    time.sleep(1.6)
    P("  T7_apply =", out["T7_apply"], "| modal open after:", )
    out["T7_modal_after"] = P2("document.getElementById('panelModal').classList.contains('open')", wait=0.8)
    P("  T7_modal_after =", out["T7_modal_after"])
    out["T7_saved_bridge"] = P2("window.pywebview.api.get_panel().then(r=>JSON.stringify(r.panel))", wait=1.8)
    P("  T7_saved_bridge =", out["T7_saved_bridge"])
    try:
        out["T7_disk"] = json.load(open(r"C:\Users\amduc\lane-cove-weather\settings.json",encoding="utf-8"))
    except Exception as e:
        out["T7_disk"] = f"NOFILE: {e}"
    P("  T7_disk =", out["T7_disk"])

    # close modal
    out["T8_close"] = P2("(mClose.click(), 'ok')", wait=0.5)
    time.sleep(0.4)
    out["T8_closed"] = P2("!document.getElementById('panelModal').classList.contains('open')", wait=0.6)
    P("  T8_closed =", out["T8_closed"])

    # edge handles present
    out["T9_edges"] = P2("document.querySelectorAll('.resize-edge').length", wait=0.5)
    P("  T9_edges =", out["T9_edges"])

    # window rect (client area)
    out["T9_win"] = P2("JSON.stringify({iw:innerWidth,ih:innerHeight})", wait=0.5)
    P("  T9_win =", out["T9_win"])

    # bridge wall-state
    out["T10_wall"] = P2("window.pywebview.api.is_wall_mode().then(x=>String(x))", wait=0.8)
    P("  T10_wall =", out["T10_wall"])

    out["PASS"] = True
    P("ALL SET — writing results")
    with open(RES, "w", encoding="utf-8") as f: json.dump(out, f, indent=1)
    P("DONE — sleeping then exit")
    time.sleep(0.8)
    os._exit(0)

t = threading.Thread(target=steps, daemon=True); t.start()
time.sleep(1)
P("main thread: starting webview loop")
try: webview.start(debug=False)
except Exception as e: P("webview.start exited:", e)
P("webview.start returned — os._exit(0)")
os._exit(0)
