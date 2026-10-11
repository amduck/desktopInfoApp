#!/usr/bin/env python
"""
Lane Cove Weather + News — a desktop info panel built on pywebview (WebView2).

Data model
  * Each data source (weather / news / gallery) is a PolledStore: one daemon
    thread owns all network I/O for that source and publishes an immutable
    snapshot under a lock. The first fetch happens on that thread, so the
    window opens immediately even when the network is down.
  * A failed fetch never replaces good data: the previous snapshot is kept,
    `error` is set, and the loop retries with exponential back-off.
  * The JS bridge (`API`) is pure reads plus "please refresh" signals —
    nothing on the bridge thread touches the network.

Run:  venv\\Scripts\\python.exe app.py
"""
import base64
import concurrent.futures as cf
import ctypes
import datetime as dt
import hashlib
import io
import json
import logging
import logging.handlers
import os
import random
import re
import threading
import time
import urllib.parse
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import xml.sax.saxutils as sax
from email.utils import parsedate_to_datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(_HERE, "index.html")
LOG_PATH = os.path.join(_HERE, "app.log")
CACHE_DIR = os.path.join(_HERE, "cache", "gallery")
SETTINGS_PATH = os.path.join(_HERE, "settings.json")

WINDOW_TITLE = "Lane Cove Weather + News"

LAT, LON = -33.805, 151.19
TIMEZONE = "Australia/Sydney"

# Open-Meteo "current" values are built from 15-minutely model data, so
# polling faster than every few minutes only re-downloads the same numbers.
WEATHER_REFRESH_S = 600           # 10 minutes
NEWS_REFRESH_S = 1800             # 30 minutes
GALLERY_REFRESH_S = 1200          # new set of images every 20 minutes
GALLERY_SET_SIZE = 5
GALLERY_HISTORY = 300             # don't repeat any of the last N images shown
GALLERY_CACHE_MAX_AGE_S = 7 * 86400   # offline fallback images
RETRY_MIN_S = 30                  # first retry after a failure
NEWS_POOL_CAP = 40
NEWS_AGE_CAP_HRS = 48
HOURLY_WINDOW = 24
PRESSURE_TENDENCY_HRS = 3         # standard synoptic tendency period

WEATHER_URL = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
    "latitude": LAT, "longitude": LON,
    "current": ",".join([
        "temperature_2m", "apparent_temperature", "relative_humidity_2m",
        "precipitation", "weather_code", "wind_speed_10m", "wind_gusts_10m",
        "wind_direction_10m", "pressure_msl", "is_day"]),
    "hourly": "temperature_2m,precipitation_probability,weather_code,pressure_msl",
    "daily": ("weather_code,temperature_2m_max,temperature_2m_min,"
              "precipitation_probability_max"),
    "timezone": TIMEZONE,
    "past_days": 1,               # gives 3 h of pressure history just after midnight
    "forecast_days": 4,
})

# Reddit: unauthenticated .json has returned 403 since May 2026; the public
# RSS (Atom) feeds still work but Reddit has announced they will be switched
# off (reported date: 13 Nov 2026). Feeds are ordered by score already.
REDDIT_FEEDS = {
    "reddit": "https://www.reddit.com/r/popular/top/.rss?t=day&limit=50",
    "sydney": "https://www.reddit.com/r/sydney/top/.rss?t=day&limit=50",
}
REDDIT_REFRESH_S = 1800
REDDIT_SPACING_S = 65             # Reddit RSS allows roughly one request a minute per client
REDDIT_POOL_CAP = 50
REDDIT_UA = "windows:LaneCoveInfoPanel:1.2 (personal desktop dashboard)"

NEWS_FEEDS = [
    ("World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("Tech", "https://feeds.bbci.co.uk/news/technology/rss.xml"),
    ("Tech", "https://techcrunch.com/feed/"),
]

# Live gallery source: Wikimedia Commons "Featured pictures" (~18,000
# community-vetted images; key-less API). Wikimedia asks API clients to send
# a descriptive User-Agent.
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
COMMONS_CATEGORY = "Category:Featured pictures on Wikimedia Commons"
WIKIMEDIA_UA = "LaneCoveInfoPanel/1.1 (personal desktop dashboard; Python urllib)"
GALLERY_THUMB_W = 960             # one of Wikimedia's standard thumbnail widths

# Offline fallback when Commons can't be reached: (article_url, image_url, caption)
GALLERY_FALLBACK = [
    ("https://en.wikipedia.org/wiki/Sydney",
     "https://commons.wikimedia.org/wiki/Special:FilePath/Sydney_Opera_House_and_Harbour_Bridge_Dusk_%282%29_2019-06-21.jpg?width=800",
     "Sydney at dusk — the Opera House sails with the Harbour Bridge behind."),
    ("https://en.wikipedia.org/wiki/Bondi_Beach",
     "https://commons.wikimedia.org/wiki/Special:FilePath/Bondi_from_above.jpg?width=800",
     "Bondi from above — a crescent of sand and surf on Sydney's eastern shore."),
    ("https://en.wikipedia.org/wiki/Great_Barrier_Reef",
     "https://commons.wikimedia.org/wiki/Special:FilePath/ISS-45_StoryOfWater%2C_Great_Barrier_Reef%2C_Australia.jpg?width=800",
     "The Great Barrier Reef from the ISS — about 2,300 km of reef off the Queensland coast."),
    ("https://en.wikipedia.org/wiki/Kakadu_National_Park",
     "https://commons.wikimedia.org/wiki/Special:FilePath/Kakadu_2431.jpg?width=800",
     "Kakadu — Bininj/Mungguy country, jointly managed with its traditional owners and rich in ancient rock art."),
    ("https://en.wikipedia.org/wiki/Hubble_Space_Telescope",
     "https://commons.wikimedia.org/wiki/Special:FilePath/Hubble_2009_close-up_2.jpg?width=800",
     "Hubble, in orbit since 1990 — photographed during its final servicing mission in 2009."),
]

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


# ---------------------------------------------------------------- logging
log = logging.getLogger("lanecove")


def setup_logging():
    """Size-capped log (3 x 512 KB). Routine successes are DEBUG and not
    written; failures, recoveries and user actions are."""
    if log.handlers:
        return
    log.setLevel(logging.INFO)
    try:
        h = logging.handlers.RotatingFileHandler(
            LOG_PATH, maxBytes=512 * 1024, backupCount=3, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s",
                                         "%Y-%m-%d %H:%M:%S"))
        log.addHandler(h)
    except OSError:
        log.addHandler(logging.NullHandler())


# ------------------------------------------------------------------- store
class PolledStore:
    """One background thread per data source.

    * fetch() returns a dict or raises. A raise keeps the previous data.
    * Retries use exponential back-off from RETRY_MIN_S up to `interval`.
    * refresh() wakes the loop early without blocking the caller.
    """

    def __init__(self, name, fetch, interval, initial_delay=0, retry_min=RETRY_MIN_S):
        self.name, self._fetch, self.interval = name, fetch, interval
        self._retry_min = retry_min
        self._initial_delay = initial_delay
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._data = None
        self._error = None
        self._ts = None
        self._failures = 0

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name=f"lc-{self.name}").start()
        return self

    def refresh(self):
        self._wake.set()

    def run_once(self):
        t0 = time.time()
        try:
            data = self._fetch()
        except Exception as e:
            with self._lock:
                self._error = f"{type(e).__name__}: {e}"
                self._failures += 1
            log.warning("%s fetch failed (%d in a row): %r", self.name, self._failures, e)
            return False
        with self._lock:
            recovered = self._failures > 0
            self._data, self._ts, self._error, self._failures = data, time.time(), None, 0
        if recovered:
            log.info("%s recovered", self.name)
        log.debug("%s ok in %.2fs", self.name, time.time() - t0)
        return True

    def _next_wait(self):
        if not self._failures:
            return self.interval
        return min(self.interval, self._retry_min * 2 ** (self._failures - 1))

    def _loop(self):
        if self._initial_delay:
            time.sleep(self._initial_delay)
        while True:
            self.run_once()
            self._wake.wait(self._next_wait())
            self._wake.clear()

    def snapshot(self):
        with self._lock:
            return {"ok": self._data is not None, "error": self._error,
                    "data": self._data, "success_ts": self._ts,
                    "refresh_seconds": self.interval}


# ----------------------------------------------------------------- weather
def _http_get(url, accept, to=15, limit=None, ua=USER_AGENT):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": accept})
    with urllib.request.urlopen(req, timeout=to) as r:
        return r.read(limit) if limit else r.read()


def _pressure_tendency(delta):
    """Words for a 3-hour MSL pressure change (hPa), following the usual
    marine-forecast bands."""
    a = abs(delta)
    if a < 0.5:
        return "steady"
    word = "rising" if delta > 0 else "falling"
    if a < 1.6:
        return f"{word} slowly"
    if a < 3.6:
        return word
    if a < 6.0:
        return f"{word} quickly"
    return f"{word} very rapidly"


def parse_weather(raw):
    """Turn an Open-Meteo response into exactly what the UI renders:
    the hourly window starts at the current local hour, the daily list
    starts today, and pressure tendency is a real 3-hour change."""
    c, h, d = raw["current"], raw.get("hourly", {}), raw.get("daily", {})
    now_iso = c["time"]                       # 'YYYY-MM-DDTHH:MM', local time
    today = now_iso[:10]

    h_time = h.get("time", [])
    # Index of the hour containing "now" (full ISO strings sort correctly).
    i_now = 0
    for i, t in enumerate(h_time):
        if t <= now_iso:
            i_now = i
        else:
            break
    sl = slice(i_now, i_now + HOURLY_WINDOW)

    tendency, delta = None, None
    p = h.get("pressure_msl", [])
    j = i_now - PRESSURE_TENDENCY_HRS
    if j >= 0 and i_now < len(p) and p[i_now] is not None and p[j] is not None:
        delta = round(p[i_now] - p[j], 1)
        tendency = _pressure_tendency(delta)

    d_time = d.get("time", [])
    k0 = next((k for k, t in enumerate(d_time) if t >= today), len(d_time))

    def dl(key):
        return d.get(key, [])[k0:]

    return {
        "temp": c["temperature_2m"], "feels": c["apparent_temperature"],
        "humidity": c["relative_humidity_2m"], "precip": c["precipitation"],
        "wind": c["wind_speed_10m"], "gust": c["wind_gusts_10m"],
        "wind_dir": c["wind_direction_10m"], "pressure": c["pressure_msl"],
        "pressure_delta_3h": delta, "pressure_tendency": tendency,
        "code": c["weather_code"], "is_day": c.get("is_day", 1),
        "as_of": now_iso, "elev": raw.get("elevation"),
        "lat": raw.get("latitude"), "lon": raw.get("longitude"),
        "h_hour": [t[11:13] for t in h_time[sl]],
        "h_temp": h.get("temperature_2m", [])[sl],
        "h_rain": h.get("precipitation_probability", [])[sl],
        "h_code": h.get("weather_code", [])[sl],
        "d_time": d_time[k0:],
        "d_name": ["TODAY" if t == today else dt.date.fromisoformat(t).strftime("%a").upper()
                   for t in d_time[k0:]],
        "d_max": dl("temperature_2m_max"), "d_min": dl("temperature_2m_min"),
        "d_code": dl("weather_code"), "d_rain": dl("precipitation_probability_max"),
    }


def weather_fetch_once():
    return parse_weather(json.loads(_http_get(WEATHER_URL, "application/json")))


# -------------------------------------------------------------------- news
def _clean_url(u):
    s = sax.unescape(u or "").strip()
    s = re.sub(r"&+amp;$", "", s)     # trailing &amp; left in some feed links
    return re.sub(r"&+$", "", s)


def _parse_date(s):
    """RFC 822 (pubDate) or ISO 8601 (dc:date) -> epoch seconds, else None."""
    s = (s or "").strip()
    if not s:
        return None
    try:
        return parsedate_to_datetime(s).timestamp()
    except (TypeError, ValueError, IndexError):
        pass
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.timestamp()
    except ValueError:
        return None


DC = "{http://purl.org/dc/elements/1.1/}"


def _item_dict(it, cat):
    title = sax.unescape((it.findtext("title") or "").strip())
    link = _clean_url(it.findtext("link") or it.findtext(DC + "identifier"))
    ts = _parse_date(it.findtext("pubDate") or it.findtext(DC + "date"))
    return {"t": title, "u": link, "c": cat, "ts": ts}


def parse_feed(raw, cat):
    root = ET.fromstring(raw)
    out = []
    for it in root.findall(".//item"):
        d = _item_dict(it, cat)
        if d["t"] and d["u"].startswith(("http://", "https://")):
            out.append(d)
    return out


def merge_news(items, now=None):
    """Dedupe by URL, drop items older than the age cap, newest first.
    Undated items are kept but sorted after every dated one."""
    now = now or time.time()
    cut = now - NEWS_AGE_CAP_HRS * 3600
    seen, out = set(), []
    for d in items:
        if d["ts"] is not None and d["ts"] < cut:
            continue
        if d["u"] in seen:
            continue
        seen.add(d["u"])
        out.append(d)
    out.sort(key=lambda x: x["ts"] if x["ts"] is not None else float("-inf"), reverse=True)
    return [{"t": x["t"], "u": x["u"], "c": x["c"]} for x in out[:NEWS_POOL_CAP]]


def news_fetch_once():
    def hit(kv):
        cat, url = kv
        try:
            return parse_feed(_http_get(url, "application/rss+xml, application/xml", to=10), cat), None
        except Exception as e:
            return None, f"{url}: {e!r}"

    with cf.ThreadPoolExecutor(max_workers=len(NEWS_FEEDS)) as pool:
        results = list(pool.map(hit, NEWS_FEEDS))
    errors = [e for _, e in results if e]
    for e in errors:
        log.warning("news feed failed: %s", e)
    if len(errors) == len(NEWS_FEEDS):
        raise RuntimeError("all news feeds failed")
    pool_top = merge_news([d for items, _ in results if items for d in items])
    if not pool_top:
        raise RuntimeError("feeds returned no usable stories")
    return {"pool": pool_top, "count": len(pool_top), "fetched_ts": time.time(),
            "feeds_ok": len(NEWS_FEEDS) - len(errors), "feed_count": len(NEWS_FEEDS)}


# ------------------------------------------------------------------ reddit
ATOM = "{http://www.w3.org/2005/Atom}"


def _age_label(ts, now=None):
    if ts is None:
        return ""
    s = max(0, (now or time.time()) - ts)
    if s < 3600:
        return f"{int(s // 60)}m"
    if s < 86400:
        return f"{int(s // 3600)}h"
    return f"{int(s // 86400)}d"


def parse_reddit_atom(raw, now=None):
    """Reddit RSS is Atom: <entry><title/><link href/><category term label/>
    <published/>…</entry>. Keeps feed order (already ranked by score)."""
    root = ET.fromstring(raw)
    out, seen = [], set()
    for e in root.findall(ATOM + "entry"):
        title = sax.unescape((e.findtext(ATOM + "title") or "").strip())
        link_el = e.find(ATOM + "link")
        link = (link_el.get("href") if link_el is not None else "") or ""
        if not title or not link.startswith("https://") or link in seen:
            continue
        seen.add(link)
        cat = e.find(ATOM + "category")
        sub = (cat.get("label") or ("r/" + cat.get("term", ""))) if cat is not None else ""
        ts = _parse_date(e.findtext(ATOM + "published") or e.findtext(ATOM + "updated"))
        out.append({"t": title, "u": link, "c": sub, "ts": ts, "age": _age_label(ts, now)})
    return out[:REDDIT_POOL_CAP]


def reddit_fetch(url):
    try:
        raw = _http_get(url, "application/atom+xml, application/xml", to=15, ua=REDDIT_UA)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404, 410):
            raise RuntimeError(f"Reddit refused the feed (HTTP {e.code}) — "
                               "its RSS access may have been switched off") from None
        if e.code == 429:
            raise RuntimeError("Reddit rate limit (HTTP 429) — will retry") from None
        raise
    pool = parse_reddit_atom(raw)
    if not pool:
        raise RuntimeError("Reddit feed returned no posts")
    return {"pool": pool, "count": len(pool), "fetched_ts": time.time()}


# ----------------------------------------------------------------- gallery
def _cache_path(url):
    return os.path.join(CACHE_DIR, hashlib.sha1(url.encode()).hexdigest() + ".jpg")


def _download_jpeg(url, to=25, max_px=GALLERY_THUMB_W):
    """Download, re-encode as <=max_px JPEG q82, return bytes."""
    from PIL import Image, ImageOps
    raw = _http_get(url, "image/*", to=to, limit=8 * 1024 * 1024, ua=WIKIMEDIA_UA)
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    im.thumbnail((max_px, max_px), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=82, optimize=True)
    return buf.getvalue()


def _gallery_image(url):
    """Disk cache first; download only when missing or older than a week.
    A failed download falls back to a stale cached copy."""
    path = _cache_path(url)
    fresh = os.path.exists(path) and time.time() - os.path.getmtime(path) < GALLERY_CACHE_MAX_AGE_S
    if not fresh:
        try:
            data = _download_jpeg(url)
            os.makedirs(CACHE_DIR, exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
        except Exception as e:
            if not os.path.exists(path):
                raise
            log.warning("gallery download failed, using cached copy %s: %r", url, e)
    with open(path, "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("ascii")


def _strip_html(h, limit=None):
    """Plain text from an extmetadata HTML fragment."""
    t = re.sub(r"<[^>]+>", " ", h or "")
    t = re.sub(r"\s+", " ", sax.unescape(t.replace("&nbsp;", " "))).strip()
    if limit and len(t) > limit:
        cut = t[:limit].rsplit(" ", 1)[0].rstrip(",;:-–— ")
        t = cut + "…"
    return t


def _caption_from(title, meta):
    """Prefer the first sentence of the English description, else the
    object name, else the file name."""
    desc = _strip_html((meta.get("ImageDescription") or {}).get("value"))
    if desc:
        m = re.match(r"(.{25,}?[.!?])\s", desc + " ")
        desc = m.group(1) if m else desc
    name = _strip_html((meta.get("ObjectName") or {}).get("value"))
    fallback = re.sub(r"\.[A-Za-z0-9]+$", "", title.split(":", 1)[-1]).replace("_", " ")
    text = desc or name or fallback
    return _strip_html(text, 170)


def parse_commons_batch(raw, exclude=()):
    """Candidate images from a Commons API response: raster photos, at least
    1200 px wide, landscape-ish (they fill a landscape card), not shown recently."""
    out = []
    for page in (raw.get("query") or {}).get("pages", []):
        title = page.get("title", "")
        info = (page.get("imageinfo") or [None])[0]
        if not title.startswith("File:") or not info or title in exclude:
            continue
        w, h = info.get("width") or 0, info.get("height") or 0
        if info.get("mime") not in ("image/jpeg", "image/png", "image/webp"):
            continue
        if w < 1200 or not h or not (1.15 <= w / h <= 2.6):
            continue
        if not info.get("thumburl") or not info.get("descriptionurl"):
            continue
        meta = info.get("extmetadata") or {}
        artist = _strip_html((meta.get("Artist") or {}).get("value"), 60)
        licence = _strip_html((meta.get("LicenseShortName") or {}).get("value"), 30)
        out.append({"title": title, "thumb": info["thumburl"], "u": info["descriptionurl"],
                    "t": _caption_from(title, meta),
                    "credit": " · ".join(x for x in (artist, licence) if x)})
    return out


def _commons_query(prefix):
    q = urllib.parse.urlencode({
        "action": "query", "format": "json", "formatversion": 2,
        "generator": "categorymembers", "gcmtitle": COMMONS_CATEGORY,
        "gcmnamespace": 6, "gcmtype": "file", "gcmlimit": 40,
        "gcmstartsortkeyprefix": prefix,
        "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": GALLERY_THUMB_W, "iiextmetadatalanguage": "en",
        "iiextmetadatafilter": "ObjectName|ImageDescription|Artist|LicenseShortName",
    })
    return json.loads(_http_get(f"{COMMONS_API}?{q}", "application/json", ua=WIKIMEDIA_UA))


_ALPHA = "ABCDEFGHIJKLMNOPRSTW"       # common initial letters, weighted towards real titles
_recent = []                          # titles shown recently (most recent last)


def commons_featured_set(n=GALLERY_SET_SIZE, rng=random):
    """A random set of n featured pictures. Jumps to a random point in the
    category's alphabetical order, takes the next 40 files, filters and
    samples; retries from another point if too few qualify."""
    picked = []
    for _ in range(4):
        prefix = rng.choice(_ALPHA) + rng.choice("abcdefghilmnoprstu")
        cands = parse_commons_batch(_commons_query(prefix),
                                    exclude=set(_recent) | {p["title"] for p in picked})
        rng.shuffle(cands)
        picked += cands[: n - len(picked)]
        if len(picked) >= n:
            break

    def fetch(c):
        try:
            data = _download_jpeg(c["thumb"])
            img = "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")
            return {"t": c["t"], "u": c["u"], "credit": c["credit"], "img": img, "title": c["title"]}
        except Exception as e:
            log.warning("commons image failed %s: %r", c["thumb"], e)
            return None

    with cf.ThreadPoolExecutor(max_workers=n) as pool:
        got = [r for r in pool.map(fetch, picked) if r]
    _recent.extend(r.pop("title") for r in got)
    del _recent[:-GALLERY_HISTORY]
    return got


def _fallback_set():
    def hit(entry):
        art, img, cap = entry
        try:
            return {"t": cap, "u": art, "credit": "Wikimedia Commons", "img": _gallery_image(img)}
        except Exception as e:
            log.warning("fallback image failed %s: %r", img, e)
            return None

    with cf.ThreadPoolExecutor(max_workers=5) as pool:
        return [r for r in pool.map(hit, GALLERY_FALLBACK) if r]


def gallery_fetch_once():
    """New random set of Commons featured pictures. If Commons is unreachable
    and there is no previous set, show the cached fallback images instead
    (the raise below keeps an existing live set on screen, marked stale)."""
    try:
        pool = commons_featured_set()
        if len(pool) >= 3:
            return {"pool": pool, "count": len(pool), "fetched_ts": time.time(), "source": "commons"}
        err = RuntimeError(f"only {len(pool)} usable images from Commons")
    except Exception as e:
        err = e
    log.warning("live gallery failed: %r", err)
    if gallery_has_data():
        raise err
    pool = _fallback_set()
    if not pool:
        raise RuntimeError("no gallery images available")
    return {"pool": pool, "count": len(pool), "fetched_ts": time.time(), "source": "fallback"}


def gallery_has_data():
    return _gallery_store is not None and _gallery_store.snapshot()["ok"]


_gallery_store = None

# ==========================================================================
# Win32 helpers (Windows only)
# ==========================================================================
class _RECT32(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("rcMonitor", _RECT32),
                ("rcWork", _RECT32), ("dwFlags", ctypes.c_uint)]


def _primary_work_area():
    if os.name != "nt":
        return (0, 0, 1920, 1080)
    r = _RECT32()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)  # SPI_GETWORKAREA
    return (r.left, r.top, r.right - r.left, r.bottom - r.top)


def _monitors():
    """Work areas of every attached monitor as [(x, y, w, h)]."""
    if os.name != "nt":
        return []
    out = []
    u = ctypes.windll.user32
    u.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    u.GetMonitorInfoW.restype = ctypes.c_int
    u.EnumDisplayMonitors.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                      ctypes.c_void_p, ctypes.c_void_p]
    CB = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
                            ctypes.c_void_p, ctypes.c_void_p)

    def cb(hmon, _hdc, _rect, _lp):
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if u.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            w = mi.rcWork
            out.append((w.left, w.top, w.right - w.left, w.bottom - w.top))
        return 1

    try:
        proc = CB(cb)               # keep the C callback alive during the call
        u.EnumDisplayMonitors(None, None, proc, 0)
    except Exception as e:
        log.warning("EnumDisplayMonitors failed: %r", e)
    return out


def work_area_for(x, y, w, h, monitors=None):
    """Work area of the monitor that holds most of the rect; if the rect is
    entirely off-screen, the monitor nearest its centre (primary if none)."""
    mons = monitors if monitors is not None else _monitors()
    if not mons:
        return _primary_work_area()
    cx, cy = x + w / 2, y + h / 2

    def score(m):
        mx, my, mw, mh = m
        ix = max(0, min(x + w, mx + mw) - max(x, mx))
        iy = max(0, min(y + h, my + mh) - max(y, my))
        dx = max(mx - cx, 0, cx - (mx + mw))
        dy = max(my - cy, 0, cy - (my + mh))
        return (ix * iy, -(dx * dx + dy * dy))

    return tuple(max(mons, key=score))


def _set_window_pos(hwnd, x, y, w, h):
    u = ctypes.windll.user32
    u.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                               ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    SWP_NOZORDER, SWP_NOACTIVATE = 0x0004, 0x0010
    return u.SetWindowPos(hwnd, None, x, y, w, h, SWP_NOZORDER | SWP_NOACTIVATE)


def _hwnd_of(window):
    """Native handle of the pywebview window: the WinForms form handle when
    available, otherwise a lookup by window title."""
    try:
        return int(window.native.Handle.ToInt64())
    except Exception:
        pass
    if os.name != "nt":
        return 0
    u = ctypes.windll.user32
    u.FindWindowW.restype = ctypes.c_void_p
    u.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    return u.FindWindowW(None, WINDOW_TITLE) or 0


# ------------------------------------------------------------------ settings
PANEL_MIN_W, PANEL_MIN_H = 360, 280
PANEL_MAX_W, PANEL_MAX_H = 3840, 2400


def load_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_settings(d):
    tmp = SETTINGS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, SETTINGS_PATH)


def default_panel(work):
    wx, wy, ww, wh = work
    w, h = min(1024, ww), min(760, wh)
    return {"x": wx + (ww - w) // 2, "y": wy + int(wh * 0.14), "w": w, "h": h}


def clamp_panel(x, y, w, h, monitors=None):
    """Clamp size, then keep at least a grabbable strip on the monitor the
    rect is (mostly) on — not just the primary monitor."""
    w = int(max(PANEL_MIN_W, min(PANEL_MAX_W, w)))
    h = int(max(PANEL_MIN_H, min(PANEL_MAX_H, h)))
    wx, wy, ww, wh = work_area_for(int(x), int(y), w, h, monitors)
    x = int(max(wx - w + 120, min(wx + ww - 120, x)))
    y = int(max(wy, min(wy + wh - 60, y)))           # title bar never above the top
    return {"x": x, "y": y, "w": w, "h": h}


def panel_from_settings(monitors=None):
    st = load_settings().get("panel")
    if isinstance(st, dict):
        try:
            return clamp_panel(st["x"], st["y"], st["w"], st["h"], monitors)
        except (KeyError, TypeError, ValueError):
            pass
    return default_panel(_primary_work_area())


# --------------------------------------------------------------------- API
class API:
    """JS bridge. Reads return snapshots; refresh_* only signal the
    background threads, so no bridge call ever waits on the network."""

    def __init__(self, weather, news, gallery, feeds=None):
        self._weather, self._news, self._gallery = weather, news, gallery
        self._feeds = feeds or {}           # extra list panels by name, e.g. Reddit
        self._win = None
        self._save_timer = None

    # ---- data ------------------------------------------------------------
    def get_weather(self):
        return self._weather.snapshot()

    def get_news(self):
        return self._news.snapshot()

    def get_gallery(self):
        return self._gallery.snapshot()

    def refresh_now(self):
        self._weather.refresh()
        return {"ok": True}

    def refresh_news(self):
        self._news.refresh()
        return {"ok": True}

    def refresh_gallery(self):
        self._gallery.refresh()
        return {"ok": True}

    def get_feed(self, name):
        st = self._feeds.get(name)
        return st.snapshot() if st else {"ok": False, "error": f"unknown feed {name!r}", "data": None}

    def refresh_feed(self, name):
        st = self._feeds.get(name)
        if st:
            st.refresh()
        return {"ok": bool(st)}

    # ---- browser ---------------------------------------------------------
    def open_url(self, url):
        try:
            p = urllib.parse.urlparse(url if isinstance(url, str) else "")
            if p.scheme not in ("http", "https") or not p.netloc:
                return {"ok": False, "error": "bad-url"}
            os.startfile(url)
            return {"ok": True}
        except Exception as e:
            log.warning("open_url failed %r: %r", url, e)
            return {"ok": False, "error": str(e)}

    # ---- window ----------------------------------------------------------
    def minimise(self):
        try:
            self._win.minimize()
        except Exception as e:
            log.warning("minimise failed: %r", e)

    def close(self):
        self.quit_app()

    def quit_app(self):
        log.info("quit requested")
        try:
            self._win.destroy()
        except Exception as e:
            log.warning("destroy failed: %r", e)
        return {"ok": True}

    # ---- panel settings ---------------------------------------------------
    def get_panel(self):
        mons = _monitors()
        panel = panel_from_settings(mons)
        return {"ok": True, "panel": panel,
                "work": list(work_area_for(panel["x"], panel["y"], panel["w"], panel["h"], mons)),
                "monitors": [list(m) for m in mons] or [list(_primary_work_area())],
                "min": {"w": PANEL_MIN_W, "h": PANEL_MIN_H}}

    def _persist_panel(self, panel):
        st = load_settings()
        st["panel"] = panel
        st.pop("mode", None)                 # wall mode no longer exists
        save_settings(st)

    def save_panel(self, x, y, w, h):
        try:
            panel = clamp_panel(int(x), int(y), int(w), int(h))
        except (TypeError, ValueError) as e:
            return {"ok": False, "error": f"bad-value: {e!r}"}
        try:
            self._persist_panel(panel)
        except OSError as e:
            log.warning("save_panel persist failed: %r", e)
            return {"ok": False, "error": str(e)}
        if self._win is not None:
            try:
                hwnd = _hwnd_of(self._win)
                if hwnd and os.name == "nt":
                    _set_window_pos(hwnd, panel["x"], panel["y"], panel["w"], panel["h"])
                else:
                    self._win.move(panel["x"], panel["y"])
                    self._win.resize(panel["w"], panel["h"])
            except Exception as e:
                log.warning("save_panel live move failed: %r", e)
        log.info("panel saved %s", panel)
        return {"ok": True, "panel": panel}

    # ---- native move / resize -> settings (debounced) ---------------------
    def _on_geometry_changed(self, *_):
        if self._save_timer:
            self._save_timer.cancel()
        self._save_timer = threading.Timer(0.6, self._save_native_geometry)
        self._save_timer.daemon = True
        self._save_timer.start()

    def _save_native_geometry(self):
        try:
            hwnd = _hwnd_of(self._win)
            if not hwnd or os.name != "nt":
                return
            r = _RECT32()
            u = ctypes.windll.user32
            u.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            if not u.GetWindowRect(hwnd, ctypes.byref(r)):
                return
            if u.IsIconic(ctypes.c_void_p(hwnd)) or u.IsZoomed(ctypes.c_void_p(hwnd)):
                return                       # don't persist minimised/maximised rects
            panel = clamp_panel(r.left, r.top, r.right - r.left, r.bottom - r.top)
            if load_settings().get("panel") != panel:
                self._persist_panel(panel)
                log.info("window geometry saved %s", panel)
        except Exception as e:
            log.warning("saving window geometry failed: %r", e)

    def _apply_saved_geometry(self, *_):
        """pywebview's create_window() takes logical (DPI-scaled) pixels while
        settings are stored in physical pixels (GetWindowRect/SetWindowPos), so
        once the window exists, place it exactly from the saved rect."""
        if os.name != "nt":
            return
        try:
            hwnd = _hwnd_of(self._win)
            if hwnd:
                p = panel_from_settings()
                _set_window_pos(hwnd, p["x"], p["y"], p["w"], p["h"])
        except Exception as e:
            log.warning("applying saved geometry failed: %r", e)

    # ---- frameless window: custom resize edges ----------------------------
    def get_bounds(self):
        """Current window rect in physical pixels (for the JS resize edges)."""
        if os.name != "nt":
            return {"ok": False}
        hwnd = _hwnd_of(self._win)
        r = _RECT32()
        u = ctypes.windll.user32
        u.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        if not hwnd or not u.GetWindowRect(hwnd, ctypes.byref(r)):
            return {"ok": False}
        return {"ok": True, "x": r.left, "y": r.top, "w": r.right - r.left, "h": r.bottom - r.top}

    def set_bounds(self, x, y, w, h):
        """Live move/resize while an edge is dragged. Persisting happens via
        the debounced moved/resized handlers, so this stays cheap."""
        try:
            w = int(max(PANEL_MIN_W, min(PANEL_MAX_W, w)))
            h = int(max(PANEL_MIN_H, min(PANEL_MAX_H, h)))
            hwnd = _hwnd_of(self._win)
            if hwnd and os.name == "nt":
                _set_window_pos(hwnd, int(x), int(y), w, h)
            return {"ok": True}
        except Exception as e:
            log.warning("set_bounds failed: %r", e)
            return {"ok": False, "error": str(e)}

    def _style_frameless(self, *_):
        """Windows 11: ask DWM for rounded corners on the frameless window
        (no-op on Windows 10)."""
        if os.name != "nt":
            return
        try:
            hwnd = _hwnd_of(self._win)
            pref = ctypes.c_int(2)                          # DWMWCP_ROUND
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd), 33, ctypes.byref(pref), ctypes.sizeof(pref))  # DWMWA_WINDOW_CORNER_PREFERENCE
        except Exception:
            pass

    def _set_animation_paused(self, paused):
        try:
            self._win.evaluate_js(f"window.__lc_pause && window.__lc_pause({'true' if paused else 'false'})")
        except Exception:
            pass


def main():
    import webview
    setup_logging()
    log.info("starting (pid=%d)", os.getpid())

    weather = PolledStore("weather", weather_fetch_once, WEATHER_REFRESH_S).start()
    news = PolledStore("news", news_fetch_once, NEWS_REFRESH_S).start()
    global _gallery_store
    _gallery_store = gallery = PolledStore("gallery", gallery_fetch_once, GALLERY_REFRESH_S).start()
    feeds = {name: PolledStore(name, (lambda u=url: reddit_fetch(u)), REDDIT_REFRESH_S,
                               initial_delay=5 + REDDIT_SPACING_S * i,
                               retry_min=REDDIT_SPACING_S).start()
             for i, (name, url) in enumerate(REDDIT_FEEDS.items())}
    api = API(weather, news, gallery, feeds)

    panel = panel_from_settings()
    window = webview.create_window(
        WINDOW_TITLE, url=HTML_PATH, js_api=api,
        x=panel["x"], y=panel["y"], width=panel["w"], height=panel["h"],
        min_size=(PANEL_MIN_W, PANEL_MIN_H), resizable=True,
        frameless=True, easy_drag=False,     # no Windows title bar; page moves/resizes via get_bounds/set_bounds
        text_select=False, background_color="#06070c")
    api._win = window

    # Persist native moves/resizes; pause the background animation while minimised.
    for ev, handler in (("shown", api._apply_saved_geometry),
                        ("shown", api._style_frameless),
                        ("moved", api._on_geometry_changed),
                        ("resized", api._on_geometry_changed),
                        ("minimized", lambda *_: api._set_animation_paused(True)),
                        ("restored", lambda *_: api._set_animation_paused(False))):
        try:
            getattr(window.events, ev).__iadd__(handler)
        except AttributeError:
            log.info("pywebview has no '%s' event; skipping", ev)

    webview.start(debug=False)


if __name__ == "__main__":
    main()
