
import sys, json, time
sys.path.insert(0, r"C:\Users\amduc\lane-cove-weather")
import app
news = app.NewsStore()
t0=time.time()
snap = news.snapshot()
print("news snapshot: ok=%s count=%s feeds=%s in %.1fs" % (snap["ok"], snap["data"]["count"], snap["data"]["feed_count"], time.time()-t0))
pool = snap["data"]["pool"]
w  = sum(1 for x in pool if x["c"]=="World")
tc = sum(1 for x in pool if x["c"]=="Tech")
print("mix: World=%d Tech=%d" % (w,tc))
N=5
seen=[]
for i in range(10):
    seen.append(pool[(i)%len(pool)]["t"][:40])
# 10 consecutive 20s rotations -> 10 distinct first-lines
print("10 rotations distinct:", len(set(seen))==10)
# API surface — make sure open_url is callable & pure
api = app.API(app.Store.__new__(app.Store), news)
# give it a real weather store without running its loop
ws = app.Store.__new__(app.Store)
import threading
ws._lock=threading.Lock(); ws._data={"t":1}; ws._ts=time.time(); ws._error=None
api = app.API(ws, news)
print("api.get_news() ->", "ok" if api.get_news()["ok"] else "FAIL")
print("api.open_url('http://x') ->", api.open_url("http://example.com"))
print("api.open_url('notaurl') ->", api.open_url("notaurl"))
