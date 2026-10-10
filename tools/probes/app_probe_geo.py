
import sys, time, json, threading
sys.path.insert(0, r"C:\Users\amduc\lane-cove-weather")
import webview, app

weather = app.Store(); news = app.NewsStore(); gallery = app.GalleryStore()
api = app.API(weather, news, gallery)
win = webview.create_window("LC_PROBE_GEO", url=app.HTML_PATH,
                            width=1200, height=920, min_size=(900,760),
                            text_select=False, background_color="#06070c", js_api=api)
api._win = win
JS = r"""
(function(){
  var r={vw:innerWidth,vh:innerHeight};
  var sel=['.hero','.fore','.newsec','.foot','.gallerysec','#frame'];
  r.rects={};
  sel.forEach(function(s){
    var n=document.querySelector(s);
    if(n){var b=n.getBoundingClientRect(); r.rects[s]={x:Math.round(b.x),y:Math.round(b.y),w:Math.round(b.width),h:Math.round(b.height)};}
    else r.rects[s]='(absent)';
  });
  r.scroll={docH:document.documentElement.scrollHeight,clientH:innerHeight};
  var cs=getComputedStyle(document.getElementById('frame'));
  r.grid={cols:cs.gridTemplateColumns,rows:cs.gridTemplateRows};
  return JSON.stringify(r);
})()
"""
def worker():
    time.sleep(14)
    for i in range(14):
        try:
            d=json.loads(win.evaluate_js(JS))
            print("probe[%d]:"%i, json.dumps(d), flush=True)
            if d.get("rects",{}).get(".foot") not in (None,'(absent)'):
                open(r"C:\Users\amduc\lane-cove-weather\probe_geo.json","w",encoding="utf-8").write(json.dumps(d,indent=1))
                print("PASS",flush=True); return
        except Exception as e:
            print("exc:",repr(e),flush=True)
        time.sleep(5)
    print("TIMEOUT",flush=True)
threading.Thread(target=worker,daemon=True).start()
webview.start()
