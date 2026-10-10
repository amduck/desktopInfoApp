import os, sys, time, json, threading
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import webview
import app as appmod

OUT = os.path.join(HERE, "probe_wall.json")
open(OUT, "w").close()
_t0 = time.time()
def log(tag, val):
    line = f"[{time.time()-_t0:6.2f}s] {tag}: {val}"
    print(line, flush=True)
    w = open(OUT, "a", encoding="utf-8"); w.write(line + "\n"); w.flush()

def wait_until(fn, timeout=60.0, step=0.4):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            v = fn()
            if v: return v
        except Exception: pass
        time.sleep(step)
    return None

weather = appmod.Store()
news    = appmod.NewsStore()
gallery = appmod.GalleryStore()
api     = appmod.API(weather, news, gallery)
icon    = os.path.join(HERE, "app_icon.ico")
common  = dict(url=appmod.HTML_PATH, text_select=False,
               background_color="#06070c", js_api=api)
window  = webview.create_window(
    "Lane Cove Weather + News",
    width=1260, height=840, min_size=(360, 280),
    **common)

def run_probe():
    def bridge_live():
        try:
            v = window.evaluate_js("window.pywebview && window.pywebview.api && typeof window.pywebview.api.get_weather === 'function'")
            return bool(v)
        except Exception:
            return False
    if not wait_until(bridge_live, 60):
        log("FAIL", "bridge never came live"); os._exit(4)
    log("OK", "bridge live")

    r1 = window.evaluate_js("""(function(){
      var el = document.getElementById('panelModal');
      return { found: !!el,
               modeSel: (document.getElementById('modeSel')||{}).value || null,
               pX: (document.getElementById('pX')||{}).value || null,
               pW: (document.getElementById('pW')||{}).value || null,
               applyModeVisible: (document.getElementById('mApplyMode').style.display !== 'none'),
               selectColor: getComputedStyle(document.getElementById('modeSel')).color,
               selectBg: getComputedStyle(document.getElementById('modeSel')).backgroundColor,
               selectW: getComputedStyle(document.getElementById('modeSel')).width,
               rowW: getComputedStyle(document.querySelector('.mrow')).width };
    })()""")
    log("T1 pre-open", json.dumps(r1))

    r2 = window.evaluate_js("""(function(){
      var m = document.getElementById('panelModal');
      m.classList.add('open');
      document.getElementById('mScrim').style.display = 'block';
      var s = getComputedStyle(document.getElementById('modeSel'));
      return { opened: m.classList.contains('open'),
               selectVal: document.getElementById('modeSel').value,
               selectColor: s.color, selectBg: s.backgroundColor,
               option0Color: getComputedStyle(document.getElementById('modeSel').options[0]).color,
               option1Color: getComputedStyle(document.getElementById('modeSel').options[1]).color,
               selectW: s.width, maxWidth: s.maxWidth,
               inputsFullW: getComputedStyle(document.querySelector('.mrow .inputs.full')).width,
               rowW: getComputedStyle(document.querySelector('.mrow')).width };
    })()""")
    log("T2 open", json.dumps(r2))

    r3 = None
    for _ in range(20):
        try:
            r3 = api.get_panel(); break
        except Exception as e:
            r3 = {"err": str(e)}; time.sleep(0.4)
    log("T3 bridge.get_panel", json.dumps(r3))

    r4 = api.set_mode("wall")
    log("T4 set_mode wall", json.dumps(r4))
    r4b = api.get_panel()
    log("T4b after", json.dumps({k: r4b.get(k) for k in ("mode","stored_mode","wall")}))

    window.evaluate_js("""(async function(){ window.__probeR = null;
      try{ window.__probeR = JSON.stringify(await window.pywebview.api.get_panel()); }
      catch(e){ window.__probeR = "ERR:"+e; }
    })()""")
    wait_until(lambda: window.evaluate_js("typeof window.__probeR === 'string' && window.__probeR !== ''"), 12)
    log("T5 js get_panel", window.evaluate_js("window.__probeR"))

    r6 = api.set_mode("panel")
    log("T6 set_mode panel", json.dumps(r6))
    r6b = api.get_panel()
    log("T6b after", json.dumps({k: r6b.get(k) for k in ("mode","stored_mode","wall")}))

    r7 = window.evaluate_js("""(function(){
      var f = document.getElementById('frame');
      var edges = f ? Array.from(f.querySelectorAll('.resize-edge')).map(e => ({r: e.dataset.r, cls: e.className})) : null;
      return { edgeCount: edges ? edges.length : 0, edges: edges,
               framePos: f ? getComputedStyle(f).position : null,
               bodyWall: document.body.classList.contains('wall') };
    })()""")
    log("T7 edges", json.dumps(r7))

    r8 = window.evaluate_js("""(function(){
      var s = getComputedStyle(document.getElementById('modeSel'));
      var rgb = s.color.replace(/rgba?\(([^)]+)\)/, '$1');
      var parts = rgb.split(',').map(x=>+x);
      var luma = parts[0]*0.2126 + parts[1]*0.7152 + parts[2]*0.0722;
      var bgParts = (s.backgroundColor.match(/rgba?\(([^)]+)\)/)||[])[1];
      var b = bgParts ? bgParts.split(',').map(x=>+x) : [255,255,255];
      var lumaB = b[0]*0.2126 + b[1]*0.7152 + b[2]*0.0722;
      var contrastRatio = (Math.max(luma,lumaB)+0.05)/(Math.min(luma,lumaB)+0.05);
      return { color: s.color, bg: s.backgroundColor,
               contrast: +contrastRatio.toFixed(1),
               selectFitsRow: (parseFloat(s.width) <= parseFloat(getComputedStyle(document.querySelector('.mrow .inputs.full')).width) + 1),
               selectW: s.width, rowW: getComputedStyle(document.querySelector('.mrow .inputs.full')).width,
               optionBg0: getComputedStyle(document.getElementById('modeSel').options[0]).backgroundColor };
    })()""")
    log("T8 contrast+fit", json.dumps(r8))

    r9 = {"has_kill_self": hasattr(api, "kill_self"), "has_set_mode": hasattr(api, "set_mode"),
          "has_restart_in": hasattr(api, "restart_in"), "has_close": hasattr(api, "close")}
    log("T9 bridge methods", json.dumps(r9))

    os._exit(0)

threading.Thread(target=run_probe, daemon=True).start()
threading.Timer(75, lambda: os._exit(3)).start()
webview.start()
log("END", "start returned")
