# Lane Cove desktop info panel

A local desktop dashboard built on **pywebview** (WebView2) for Windows.

**Panels**
- **Weather** — Lane Cove (−33.805, 151.19): current conditions, 3-hour pressure tendency, 24-hour strip starting at the current hour, 4-day outlook. Source: [Open-Meteo](https://open-meteo.com) (no API key), refreshed every 10 minutes.
- **News** — 5 headlines at a time from a pool of up to 40 (BBC World, BBC Technology, TechCrunch RSS), rotating every 20 s, pool refreshed every 30 min. ‹ › to page; click a headline to open it in your browser.
- **In focus** — 5 curated Wikimedia Commons images with captions, rotating every 30 s. Images are cached in `cache/gallery/` and re-checked weekly.

**Run**
```
cd lane-cove-weather
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python app.py        (or pythonw.exe for no console)
```

**Window**
- Move or resize the window normally; its position and size are saved to `settings.json` automatically.
- ⚙ opens layout presets (left/right dock, centre, full work area) and exact X/Y/W/H. Positions are clamped per monitor, so a window on a second screen stays there.
- Windows narrower than 760 px switch to a single-column layout.
- The background animation runs at 30 fps, pauses while the window is minimised or hidden, and is a still image when Windows "Animation effects" is off (reduced motion).

**Architecture**
- `PolledStore` (one per source) runs a background thread that owns all network I/O and publishes a lock-guarded snapshot. The first fetch happens on that thread, so the window opens immediately even offline.
- A failed fetch never replaces good data: the last snapshot is kept, the UI shows **Stale**, and the thread retries with exponential back-off (30 s → refresh interval).
- The JS bridge (`API`) only reads snapshots or signals a refresh — no bridge call waits on the network.
- Logging goes to `app.log` (rotating, 3 × 512 KB); only failures, recoveries and user actions are written.

Sources: [Open-Meteo](https://open-meteo.com) · BBC · TechCrunch · [Wikimedia Commons](https://commons.wikimedia.org)
