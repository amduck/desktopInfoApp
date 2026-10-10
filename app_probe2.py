
import sys, os, time, json, threading
sys.path.insert(0, r"C:\Users\amduc\lane-cove-weather")
import webview, app

def main():
    weather = app.Store()
    news    = app.NewsStore()
    api     = app.API(weather, news)
    win     = webview.create_window("LC_PROBE_NEWS", url=app.HTML_PATH,
                                    width=1200, height=1000,
                                    min_size=(980,860), easy_drag=True,
                                    text_select=False, background_color="#06070c", js_api=api)
    api._win = win
    result = {"err": None}
    events = threading.Event()

    def run():
        try:
            t_end = time.time() + 45
            got = False
            while time.time() < t_end and not got:
                time.sleep(3)
                try:
                    out = win.evaluate_js("""
                      (function(){
                        var r = {};
                        r.bootLog = window.__lc_bootLog ? window.__lc_bootLog.slice(-12) : '(none)';
                        r.temp = document.getElementById('t2m') ? document.getElementById('t2m').textContent : '(?)';
                        r.cond = document.getElementById('cond') ? document.getElementById('cond').textContent.trim() : '(?)';
                        var items = document.querySelectorAll('#newsItems .news-item');
                        r.newsVisible = items.length;
                        r.newsBadges = Array.prototype.map.call(document.querySelectorAll('#newsItems .news-badge'), function(b){return b.textContent;});
                        r.newsFirst = items.length ? items[0].querySelector('a').textContent.trim().slice(0,70) : '(none)';
                        r.newsHref  = items.length ? items[0].querySelector('a').getAttribute('href').slice(0,80) : '(none)';
                        r.meta = document.getElementById('newsMeta') ? document.getElementById('newsMeta').textContent : '(?)';
                        r.refreshLink = !!document.getElementById('newsRefresh');
                        return JSON.stringify(r);
                      })()
                    """)
                    if out:
                        d = json.loads(out)
                        if d.newsVisible > 0 and d.temp != '(?)':
                            win.destroy();
                            events.set();
                            got = True
                            with open(r"C:\Users\amduc\lane-cove-weather\probe_news.json","w",encoding="utf-8") as f:
                                json.dump(d, f, indent=1)
                            return "PASS"
                    time.sleep(2)
                except Exception as e:
                    pass
            return "TIMEOUT"
        finally:
            events.set()

    th = threading.Thread(target=run, daemon=True); th.start()
    webview.start()
    st = "PASS" if th and open(r"C:\Users\amduc\lane-cove-weather\probe_news.json").close() is None else "?"
    print(json.load(open(r"C:\Users\amduc\lane-cove-weather\probe_news.json")))
    print("PROBE DONE:", "PASS" if os.path.exists(r"C:\Users\amduc\lane-cove-weather\probe_news.json") else "TIMEOUT")

main()
