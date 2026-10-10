#!/usr/bin/env python
"""
Lane Cove Weather + News — a striking, bold Windows app.

Weather
  * A background fetcher thread owns the Open-Meteo HTTP calls on a
    30-second cadence, updating a thread-safe snapshot.
  * The JS bridge (`pywebview.api.get_weather`) is pure read — it never
    blocks on the network, so the pywebview COM worker pool can't
    deadlock the UI.

News
  * An independent background refresher polls key-less RSS feeds
    (BBC World, BBC Tech, TechCrunch) every 30 minutes, building a
    deduped, recency-sorted pool of up to 40 headlines (World / Tech).
  * `pywebview.api.get_news` is the same pure-read pattern.
  * `pywebview.api.open_url(url)` opens a clicked headline in the
    default browser (Windows).

Run:  venv\\Scripts\\python.exe app.py
"""
import base64
import concurrent.futures as cf
import json
import os
import re
import sys
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
import xml.sax.saxutils as sax

_HERE = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(_HERE, "index.html")
DEBUG_LOG = os.path.join(_HERE, "push_debug.log")

LAT, LON = -33.805, 151.19
WEATHER_REFRESH_S = 30
NEWS_REFRESH_S    = 1800          # 30 minutes
NEWS_POOL_CAP     = 40            # UI rotates this many
NEWS_AGE_CAP_HRS  = 48            # discard older than this

WEATHER_URL = (
    "https://api.open-meteo.com/v1/forecast?"
    "latitude=-33.805&longitude=151.19"
    "&current=temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,"
    "weather_code,wind_speed_10m,wind_gusts_10m,wind_direction_10m,pressure_msl,is_day"
    "&hourly=temperature_2m,precipitation_probability,weather_code"
    "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
    "&timezone=Australia%2FSydney&forecast_days=4"
)

NEWS_FEEDS = [
    ("World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("Tech",  "https://feeds.bbci.co.uk/news/technology/rss.xml"),
    ("Tech",  "https://techcrunch.com/feed/"),
]

# gallery: captioned images -> Wikipedia article pages (originals from en.wikipedia.org)
GALLERY = [
    # (article_url, image_url, caption) — Special:FilePath?width=800, all verified 200 OK
    ("https://en.wikipedia.org/wiki/Sydney",
     "https://commons.wikimedia.org/wiki/Special:FilePath/Sydney_Opera_House_and_Harbour_Bridge_Dusk_%282%29_2019-06-21.jpg?width=800",
     "Sydney, at dusk — the sails of the Opera House set off the Harbour Bridge, a harbour kept for ships and sails alike."),
    ("https://en.wikipedia.org/wiki/Bondi_Beach",
     "https://commons.wikimedia.org/wiki/Special:FilePath/Bondi_from_above.jpg?width=800",
     "Bondi from above — a crescent of sand and sea on Sydney's east coast, the beach at its widest."),
    ("https://en.wikipedia.org/wiki/Great_Barrier_Reef",
     "https://commons.wikimedia.org/wiki/Special:FilePath/ISS-45_StoryOfWater%2C_Great_Barrier_Reef%2C_Australia.jpg?width=800",
     "The Great Barrier Reef — the largest living structure on Earth, 2,300 km of coral seen from the ISS."),
    ("https://en.wikipedia.org/wiki/Kakadu_National_Park",
     "https://commons.wikimedia.org/wiki/Special:FilePath/Kakadu_2431.jpg?width=800",
     "Kakadu — water country for 65,000 years, its rock art older than the pyramids on Anangu country."),
    ("https://en.wikipedia.org/wiki/Hubble_Space_Telescope",
     "https://commons.wikimedia.org/wiki/Special:FilePath/Hubble_2009_close-up_2.jpg?width=800",
     "Hubble, 30 years up — a deep-field snapshot; that whole field is a 1/40,000th of a full-moon sky."),
]
GALLERY_ROTATE_S = 30
GALLERY_REFRESH_S = 1800
GALLERY_VISIBLE  = 5

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


# ---------------------------------------------------------------- logging
def dbg(msg):
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
            f.flush()
    except Exception:
        pass


# ----------------------------------------------------------------- weather
def weather_fetch_once():
    req = urllib.request.Request(
        WEATHER_URL, headers={"User-Agent": "lane-cove-weather/1.0",
                              "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = json.loads(r.read())
    c, h, d = raw["current"], raw.get("hourly", {}), raw.get("daily", {})
    return {
        "temp": c["temperature_2m"], "feels": c["apparent_temperature"],
        "humidity": c["relative_humidity_2m"], "precip": c["precipitation"],
        "wind": c["wind_speed_10m"], "gust": c["wind_gusts_10m"],
        "wind_dir": c["wind_direction_10m"], "pressure": c["pressure_msl"],
        "code": c["weather_code"], "is_day": c.get("is_day", 1),
        "as_of": c["time"], "elev": raw.get("elevation"),
        "lat": raw.get("latitude"), "lon": raw.get("longitude"),
        "h_time": [t[:13] for t in h.get("time", [])],
        "h_temp": h.get("temperature_2m", []),
        "h_rain": h.get("precipitation_probability", []),
        "h_code": h.get("weather_code", []),
        "d_time": d.get("time", []), "d_max": d.get("temperature_2m_max", []),
        "d_min": d.get("temperature_2m_min", []), "d_code": d.get("weather_code", []),
        "d_rain": d.get("precipitation_probability_max", []),
    }


# -------------------------------------------------------------------- news
def _http_get(url, to=10):
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT,
                      "Accept": "application/rss+xml, application/xml"})
    with urllib.request.urlopen(req, timeout=to) as r:
        return r.read()


def _clean(u):
    if not u:
        return u
    s = sax.unescape(u).strip()    # &amp; -> &
    s = re.sub(r"&+amp;$", "", s)  # drop trailing &amp; from query strings
    s = re.sub(r"&+$", "", s)      # drop any dangling literal &
    return s


def _item_dict(it, cat):
    t = (it.findtext("title") or "").strip()
    # link: either <link> or dc:identifier
    u = (it.findtext("link") or
         it.findtext("{http://purl.org/dc/elements/1.1/}identifier") or "").strip()
    ts = None
    pd = (it.findtext("pubDate") or
          it.findtext("{http://purl.org/dc/elements/1.1/}date") or "").strip()
    if pd:
        try:
            from email.utils import parsedate_to_datetime
            ts = parsedate_to_datetime(pd).timestamp()
        except Exception:
            ts = None
    t = sax.unescape(t)
    return {"t": t, "u": u, "c": cat, "ts": ts}


def news_fetch_once():
    """Fetch all feeds in parallel; dedupe by URL; sort newest-first; cap 40."""
    all_items = []
    ok_counts = []

    def hit(kv):
        cat, url = kv
        try:
            raw  = _http_get(url)
            root = ET.fromstring(raw)
            out  = []
            for it in root.findall(".//item"):
                d = _item_dict(it, cat)
                if d["t"] and d["u"]:
                    out.append(d)
            return ("ok", len(out), out)
        except Exception as e:
            return ("err", 0, [])

    with cf.ThreadPoolExecutor(max_workers=len(NEWS_FEEDS)) as pool:
        for status, n, items in pool.map(hit, NEWS_FEEDS):
            if status == "ok":
                all_items.extend(items)
                ok_counts.append(n)
            else:
                ok_counts.append(0)

    now  = time.time()
    cut  = now - NEWS_AGE_CAP_HRS * 3600
    seen, out = set(), []
    for d in all_items:
        if (d["ts"] or now) < cut:
            continue
        if d["u"] in seen:
            continue
        seen.add(d["u"])
        out.append({"t": d["t"], "u": d["u"], "c": d["c"], "ts": d["ts"]})

    out.sort(key=lambda x: x.get("ts") or now, reverse=True)
    pool_top = out[:NEWS_POOL_CAP]
    top = [{"t": x["t"], "u": x["u"], "c": x["c"]} for x in pool_top]
    dbg(f"news fetched: feeds_ok={sum(1 for x in ok_counts if x)}/{len(NEWS_FEEDS)} "
        f"pool={len(top)} top0={top[0]['t'][:60] if top else '-'}")
    return {"pool": top, "count": len(top), "fetched_ts": now,
            "feed_count": len(NEWS_FEEDS)}



# ------------------------------------------------------------------ gallery
def _img_b64(url, to=25):
    """Download the original, re-encode as \u2264800px JPEG q82, return a base64 data-URI."""
    import io
    from PIL import Image, ImageOps
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=to) as r:
        raw = r.read(6 * 1024 * 1024)          # 6 MB cap
    im  = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
    im  = im.convert("RGB")
    im.thumbnail((800, 800), Image.LANCZOS)    # \u2264800 px per side
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=82, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def gallery_fetch_once():
    """Download each image in parallel, verify byte signature, base64-embed,
    keep only entries whose download succeeded (so the pool is all-live)."""

    def hit(entry):
        art, img, cap = entry
        try:
            b64 = _img_b64(img)
            return {"t": cap, "u": art, "img": b64, "ok": True}
        except Exception as e:
            dbg(f"gallery fetch FAIL {img}: {e!r}")
            return {"t": cap, "u": art, "img": None, "ok": False}

    with cf.ThreadPoolExecutor(max_workers=5) as pool:
        res = list(pool.map(hit, GALLERY))
    ok = [r for r in res if r.pop("ok")]
    dbg(f"gallery fetched: {len(ok)}/{len(GALLERY)}")
    return {"pool": ok, "count": len(ok), "fetched_ts": time.time()}

# ------------------------------------------------------------------ stores
class Store:
    """Weather snapshot + background fetcher loop, exposed via the JS bridge."""

    def __init__(self):
        self._lock  = threading.Lock()
        self._data  = None
        self._error = None
        self._ts    = None
        try:
            self._data  = weather_fetch_once()
            self._ts    = time.time()
            self._error = None
            dbg(f"weather primed: temp={self._data['temp']} code={self._data['code']}")
        except Exception as e:
            self._error = str(e)
            dbg(f"weather prime FAIL: {e!r}")
        threading.Thread(target=self._loop, daemon=True, name="lc-fetch").start()
        dbg(f"weather fetcher started (pid={os.getpid()})")

    def _loop(self):
        while True:
            time.sleep(WEATHER_REFRESH_S)
            t0 = time.time()
            try:
                data = weather_fetch_once()
                with self._lock:
                    self._data, self._ts, self._error = data, time.time(), None
                dbg(f"weather ok in {time.time()-t0:.2f}s code={data['code']}")
            except Exception as e:
                with self._lock:
                    self._error = str(e)
                dbg(f"weather FAIL: {e!r}")

    def snapshot(self):
        with self._lock:
            return {"ok": self._ts is not None, "error": self._error,
                    "data": self._data, "success_ts": self._ts,
                    "refresh_seconds": WEATHER_REFRESH_S}


class NewsStore:
    """Key-less RSS pool; independent 30-min refresher; pure-read bridge."""

    def __init__(self):
        self._lock  = threading.Lock()
        self._data  = None
        self._error = None
        self._ts    = None
        try:
            self._data  = news_fetch_once()
            self._ts    = time.time()
            self._error = None
            dbg(f"news primed: count={self._data['count']}")
        except Exception as e:
            self._error = str(e)
            dbg(f"news prime FAIL: {e!r}")
        threading.Thread(target=self._loop, daemon=True, name="lc-news").start()
        dbg(f"news fetcher started (pid={os.getpid()})")

    def _loop(self):
        while True:
            time.sleep(NEWS_REFRESH_S)
            t0 = time.time()
            try:
                data = news_fetch_once()
                with self._lock:
                    self._data, self._ts, self._error = data, time.time(), None
                dbg(f"news ok in {time.time()-t0:.2f}s count={data['count']}")
            except Exception as e:
                with self._lock:
                    self._error = str(e)
                dbg(f"news FAIL: {e!r}")

    def snapshot(self):
        with self._lock:
            return {"ok": self._ts is not None, "error": self._error,
                    "data": self._data, "success_ts": self._ts,
                    "refresh_seconds": NEWS_REFRESH_S}



class GalleryStore:
    """Curated images with captions; 30-min refresher re-downloads each image
    so the pool is byte-live at every refresh."""

    def __init__(self):
        self._lock  = threading.Lock()
        self._data  = None
        self._error = None
        self._ts    = None
        try:
            self._data = gallery_fetch_once()
            self._ts   = time.time()
        except Exception as e:
            self._error = str(e)
            dbg(f"gallery prime FAIL: {e!r}")
        threading.Thread(target=self._loop, daemon=True, name="lc-gallery").start()
        dbg(f"gallery fetcher started (pid={os.getpid()})")

    def _loop(self):
        while True:
            time.sleep(GALLERY_REFRESH_S)
            t0 = time.time()
            try:
                self._data = gallery_fetch_once()
                self._ts   = time.time()
                with self._lock:
                    self._data, self._ts = self._data, time.time()
                    self._error = None
                dbg(f"gallery ok in {time.time()-t0:.2f}s count={self._data['count']}")
            except Exception as e:
                with self._lock:
                    self._error = str(e)
                dbg(f"gallery FAIL: {e!r}")

    def snapshot(self):
        with self._lock:
            return {"ok": self._ts is not None, "error": self._error,
                    "data": self._data, "success_ts": self._ts,
                    "refresh_seconds": GALLERY_REFRESH_S}

# --------------------------------------------------------------------- API
class API:
    def __init__(self, weather, news, gallery):
        self._weather  = weather
        self._news     = news
        self._gallery  = gallery
        self._win      = None

    # ---- weather ---------------------------------------------------------
    def get_weather(self):
        return self._weather.snapshot()

    def refresh_now(self):
        try:
            data = weather_fetch_once()
            with self._weather._lock:
                self._weather._data  = data
                self._weather._ts    = time.time()
                self._weather._error = None
        except Exception as e:
            with self._weather._lock:
                self._weather._error = str(e)
        return self._weather.snapshot()

    # ---- news ------------------------------------------------------------
    def get_news(self):
        return self._news.snapshot()

    def refresh_news(self):
        try:
            data = news_fetch_once()
            with self._news._lock:
                self._news._data  = data
                self._news._ts    = time.time()
                self._news._error = None
        except Exception as e:
            with self._news._lock:
                self._news._error = str(e)
        return self._news.snapshot()

    # ---- gallery ---------------------------------------------------------
    def get_gallery(self):
        return self._gallery.snapshot()

    def refresh_gallery(self):
        try:
            self._gallery._data  = gallery_fetch_once()
            self._gallery._ts    = time.time()
            with self._gallery._lock:
                self._gallery._error = None
        except Exception as e:
            with self._gallery._lock:
                self._gallery._error = str(e)
        return self._gallery.snapshot()

    # ---- browser --------------------------------------------------------
    def open_url(self, url):
        try:
            if not isinstance(url, str) or not url.startswith("http"):
                return {"ok": False, "error": "bad-url"}
            os.startfile(url)
            return {"ok": True}
        except Exception as e:
            dbg(f"open_url FAIL {url!r}: {e!r}")
            return {"ok": False, "error": str(e)}

    # ---- window ---------------------------------------------------------
    def minimise(self):
        try: self._win.minimise()
        except Exception: pass

    def close(self):
        try: self._win.destroy()
        except Exception: pass


# -------------------------------------------------------------------- main
def main():
    import webview
    weather = Store()
    news    = NewsStore()
    gallery = GalleryStore()
    api     = API(weather, news, gallery)
    window  = webview.create_window(
        "Lane Cove Weather + News",
        url=HTML_PATH,
        width=1200, height=1080,
        min_size=(980, 760),
        resizable=True,
        easy_drag=True,
        text_select=False,
        background_color="#06070c",
        js_api=api,
    )
    api._win = window
    webview.start(debug=False)


if __name__ == "__main__":
    main()
