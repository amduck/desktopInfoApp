
import sys, time, json, threading
sys.path.insert(0, r"C:\Users\amduc\lane-cove-weather")
import webview, app

weather = app.Store()
news    = app.NewsStore()
api     = app.API(weather, news)
win     = webview.create_window("LC_PROBE_NEWS", url=app.HTML_PATH,
                                width=1100, height=940, min_size=(900, 760),
                                text_select=False, background_color="#06070c", js_api=api)
api._win = win
JS="""
(function(){
  var r={};
  r.boot=window.__lc_bootLog?window.__lc_bootLog.join(' ~ ').slice(-400):'(none)';
  r.temp=document.getElementById('temp')?document.getElementById('temp').textContent:'(?)';
  r.cond=document.getElementById('cond')?document.getElementById('cond').textContent.trim():'(?)';
  var it=document.querySelectorAll('#newsItems .news-item');
  r.n=it.length;
  r.badges=Array.prototype.map.call(document.querySelectorAll('#newsItems .news-badge'),function(b){return b.textContent;});
  r.first= it.length? it[0].querySelector('a').textContent.trim().slice(0,80):'(none)';
  r.href= it.length? it[0].querySelector('a').getAttribute('href').slice(0,90):'(none)';
  r.meta=document.getElementById('newsMeta')?document.getElementById('newsMeta').textContent:'(?)';
  r.pyReady=!!(window.pywebview && window.pywebview.api && typeof window.pywebview.api.get_news==='function');
  return JSON.stringify(r);
})()
"""
def worker():
    time.sleep(15)
    for i in range(14):
        try:
            d=json.loads(win.evaluate_js(JS))
            print("probe[%d]:" % i, json.dumps(d)[:500], flush=True)
            if d.get("n",0)>=1 and d.get("temp") not in (None,"(?)",""):
                with open(r"C:\Users\amduc\lane-cove-weather\probe_news.json","w",encoding="utf-8") as f:
                    json.dump(d,f,indent=1)
                print("PASS",flush=True)
                return
        except Exception as e:
            print("exc:",repr(e),flush=True)
        time.sleep(5)
    print("TIMEOUT",flush=True)
t=threading.Thread(target=worker,daemon=True); t.start()
webview.start(); print("returned",flush=True)
