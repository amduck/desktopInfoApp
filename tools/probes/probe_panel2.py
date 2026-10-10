
import sys, os, json, time, threading
sys.path.insert(0, r"C:\Users\amduc\lane-cove-weather")
os.chdir(r"C:\Users\amduc\lane-cove-weather")
sys.argv = ["app.py"]
import app as A
import webview

RESULTS = r"C:\Users\amduc\lane-cove-weather\probe_results.json"
def P(*a):
    print(*a, file=sys.stderr, flush=True)

api = A.API(A.Store(), A.NewsStore(), A.GalleryStore())
panel = A._panel_from_settings(); work = A._work_area()
P("work:", work, "panel:", panel)

window = webview.create_window(
    "Lane Cove Weather + News",
    x=panel["x"], y=panel["y"], width=panel["w"], height=panel["h"],
    min_size=(A.PANEL_MIN_W, A.PANEL_MIN_H), resizable=True, easy_drag=True,
    url=A.HTML_PATH, text_select=False, background_color="#06070c", js_api=api)
api._win = window; api._wall = False

def js(expr, timeout=30):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            v = window.evaluate_js(expr)
            if v is not None: return v
        except Exception as e: last = e
        time.sleep(0.4)
    raise RuntimeError(f"js timeout: {expr[:60]!r} last={last!r}")

def steps():
    out = {}
    try:
        # 1 — page alive?
        js("document.readyState", 30)
        out["1_ready"] = js("document.readyState")
        out["1_temp"] = None
        end = time.time() + 45
        while out["1_temp"] in (None, "") and time.time() < end:
            try: out["1_temp"] = js("document.getElementById('temp').textContent", 3)
            except Exception as e: out["1_temp"] = time.time() < end and None or "ERR"
        if not out["1_temp"]: raise RuntimeError("temp never rendered")

        # 2 — bridge
        out["2_bridge"] = js("typeof window.pywebview.api.get_panel")

        # 3 — modal plumbing
        out["3_modal"] = json.loads(js("""(function(){
          const m = document.getElementById('panelModal');
          document.getElementById('gear').click();
          return JSON.stringify({
            modal: !!m, open: m.classList.contains('open'),
            inputs: ['pX','pY','pW','pH','pScale','modeSel','mApply','mDefaults','mApplyMode','mQuit','mClose','mNote']
                     .every(id => !!document.getElementById(id)),
            filled: ['pX','pY','pW','pH'].every(id => +document.getElementById(id).value > 0),
            mode: document.getElementById('modeSel').value,
            chips: document.querySelectorAll('#presetRow .chip').length,
            note: document.getElementById('mNote').textContent.slice(0,60)
          });
        })()"""))

        # 4 — preset right
        out["4_preset_right"] = json.loads(js("""(function(){
          document.querySelector('#presetRow .chip[data-preset=right]').click();
          return JSON.stringify({x:+document.getElementById('pX').value,
                                w:+document.getElementById('pW').value,
                                h:+document.getElementById('pH').value});
        })()"""))

        # 5 — resize slider keeps aspect
        out["5_slider"] = json.loads(js("""(function(){
          const s = document.getElementById('pScale');
          s.value = 640; s.dispatchEvent(new Event('input'));
          return JSON.stringify({w:+document.getElementById('pW').value, h:+document.getElementById('pH').value});
        })()"""))

        # 6 — modal Apply (panel mode → save)
        out["6_apply"] = json.loads(js("""(async function(){
          document.getElementById('pX').value = 520; document.getElementById('pY').value = 100;
          document.getElementById('pW').value = 860; document.getElementById('pH').value = 640;
          document.getElementById('mApply').click();
          await new Promise(r => setTimeout(r, 900));
          const r = await window.pywebview.api.get_panel();
          return JSON.stringify(r.panel);
        })()"""))
        out["6_disk"] = json.load(open(r"C:\Users\amduc\lane-cove-weather\settings.json", encoding="utf-8"))["panel"]

        # 7 — wall-mode flags (off here)
        out["7_is_wall"] = js("window.pywebview.api.is_wall_mode().then(x=>String(x))")
        out["7_lc_wall"] = js("typeof window.__lc_wall")
        out["7_resize_edges"] = js("document.querySelectorAll('.resize-edge').length")

        # 8 — error contract
        out["8_bad_arg_ok_false"] = js("window.pywebview.api.save_panel('x',1,2,3).then(r=>String(r.ok))")

        # 9 — weather still live
        out["9_temp_final"] = js("document.getElementById('temp').textContent")
        out["9_news"] = js("document.querySelectorAll('#newsItems .news-item').length")

        out["PASS"] = True
    except Exception as e:
        import traceback; out["FAIL"] = traceback.format_exc()
    finally:
        with open(RESULTS, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
        time.sleep(0.5)
        try: window.destroy()
        except Exception: os._exit(0 if out.get("PASS") else 1)

prober = threading.Thread(target=steps, daemon=True)
prober.start()
time.sleep(2)
webview.start(debug=False)     # main-thread loop; exits when window destroyed
time.sleep(1)
r = json.load(open(RESULTS, encoding="utf-8"))
sys.exit(0 if r.get("PASS") else 2)
