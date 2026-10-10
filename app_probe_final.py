
import sys, time, json, threading
sys.path.insert(0, r"C:\Users\amduc\lane-cove-weather")
import webview, app

weather = app.Store(); news = app.NewsStore(); gallery = app.GalleryStore()
api = app.API(weather, news, gallery)
win = webview.create_window("LC_PROBE_FINAL", url=app.HTML_PATH,
                            width=1200, height=920, min_size=(900,760),
                            text_select=False, background_color="#06070c", js_api=api)
api._win = win
JS = r"""
(function(){
  var r={vw:innerWidth,vh:innerHeight,checks:{}};
  function g(s){var n=document.querySelector(s);return n?n.getBoundingClientRect():null;}
  // 1) 4-day outlook rounded bottom
  var f=document.querySelector('.fore');
  r.checks.fore={overflow:getComputedStyle(f).overflow, borderRadius:getComputedStyle(f).borderRadius,
                 rect:(function(){var b=f.getBoundingClientRect();return {y:Math.round(b.y),h:Math.round(b.height)};})()};
  // 2) news nav buttons present + clickable
  r.checks.newsNav={prev:!!document.getElementById('newsPrev'), next:!!document.getElementById('newsNext'),
                    items:(document.querySelectorAll('.news-item')||[]).length};
  // 3) gallery panel
  var gs=document.querySelector('.gallerysec');
  r.checks.gallery={
    present:!!gs,
    rect:(function(){var b=gs.getBoundingClientRect();return {x:Math.round(b.x),y:Math.round(b.y),w:Math.round(b.width),h:Math.round(b.height)};})(),
    prev:!!document.getElementById('galPrev'), next:!!document.getElementById('galNext'),
    imgHasSrc:(function(){var im=document.getElementById('galImg');return im && im.src && im.src.indexOf('data:image')===0;})(),
    cap:(function(){var c=document.getElementById('galCap');return c?c.textContent.slice(0,40):'';})(),
    meta:(function(){var m=document.getElementById('galMeta');return m?m.textContent.slice(0,60):'';})(),
    clickTarget:(function(){var a=document.getElementById('galLink');return a?a.getAttribute('href'):'?';})()
  };
  return JSON.stringify(r);
})()
"""
def worker():
    time.sleep(14)
    JS2 = r"""
    (function(){
      var gs=document.querySelector('.gallerysec');
      var card=gs?gs.querySelector('.card'):null;
      var fore=document.querySelector('.fore');
      var frame=document.getElementById('frame');
      var r={};
      if(gs) r.galCard = Math.round(gs.getBoundingClientRect().height);
      if(card) r.cardH = Math.round(card.getBoundingClientRect().height);
      if(fore) r.foreH = Math.round(fore.getBoundingClientRect().height);
      if(frame) r.bodyH = Math.round(document.body.getBoundingClientRect().height);
      r.imgLoaded = (function(){var im=document.getElementById('galImg'); return im && im.complete && im.naturalWidth>0 ? im.naturalWidth+'x'+im.naturalHeight : 'notloaded';})();
      r.cap = (function(){var c=document.getElementById('galCap');return c?c.textContent.slice(0,34):'';})();
      return JSON.stringify(r);
    })()
    """
    def sample():
        return json.loads(win.evaluate_js(JS2))
    seq=[]
    for i in range(4):
        seq.append(sample())
        if i<3:
            win.evaluate_js("document.getElementById('galNext').click(); true")
            time.sleep(2.5)
    heights=[(d.get('galCard'),d.get('cardH'),d.get('foreH')) for d in seq]
    stable = len(set(heights))==1
    print("HEIGHTS_SEQ:", heights, flush=True)
    print("STABLE:" , stable, flush=True)
    detail=[ (d['cap'], d['imgLoaded'], d.get('galCard')) for d in seq ]
    open(r"C:\Users\amduc\lane-cove-weather\probe_stability.json","w",encoding="utf-8").write(json.dumps({"seq":detail,"heights":heights,"stable":stable},indent=1))
    print("PASS" if stable else "FAIL", flush=True)

threading.Thread(target=worker,daemon=True).start()
webview.start()
