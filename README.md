# desktopInfoApp

Lane Cove desktop info app — a local dashboard built on **pywebview** (WebView2).

**Panels**
- **Weather** — Lane Cove (−33.805, 151.19), current conditions, 24-hour strip, 4-day outlook. Source: [Open-Meteo](https://open-meteo.com) (no API key).
- **News feed** — 5 headlines shown from a 40-story pool (BBC World, BBC Tech, TechCrunch RSS), auto-rotating every 20 s, pool refresh every 30 min, manual ‹ › page buttons, headlines open in the browser.
- **In focus gallery** — 5 curated images with captions, rotating every 30 s, refreshed every 30 min, ‹ › buttons, image clicks through to the source page.
- **System stats** — CPU / RAM history.

**Run**
```
cd lane-cove-weather
uv venv .venv        # or: python -m venv venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python app.py
```

**Architecture**
- Pull model: background fetcher threads (weather / news / gallery) own all network I/O; the pywebview JS bridge (`API`) is pure reads — no network on the UI thread, `RLock`-guarded shared state.
- Gallery images are base64'd (Pillow) in-thread and pushed as data-URLs so the WebView needs no CORS.
- `app_probe*.py` are headless verification probes (`evaluate_js` DOM readbacks) used to confirm rendering before shipping a change.

Sources: [Open-Meteo](https://open-meteo.com) · BBC · TechCrunch · [Wikimedia Commons](https://commons.wikimedia.org)
