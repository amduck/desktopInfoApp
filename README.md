# Lane Cove desktop info panel

A local desktop dashboard built on **pywebview** (WebView2) for Windows.

**Panels**
- **Weather** — Lane Cove (−33.805, 151.19): current conditions, 3-hour pressure tendency, 24-hour strip starting at the current hour, 4-day outlook. Source: [Open-Meteo](https://open-meteo.com) (no API key), refreshed every 10 minutes.
- **News** — 5 headlines at a time from a pool of up to 40 (BBC World, BBC Technology, TechCrunch RSS), rotating every 20 s, pool refreshed every 30 min. ‹ › to page; click a headline to open it in your browser.
- **In focus** — a new random set of 5 [Wikimedia Commons featured pictures](https://commons.wikimedia.org/wiki/Commons:Featured_pictures) every 20 minutes (from ~18,000 community-vetted images; no repeats within the last 300), rotating every 30 s with caption and photographer/licence credit. Click an image to open its Commons page. If Commons can't be reached at start-up, 5 saved images from `cache/gallery/` are shown instead.
- **Reddit — popular** and **r/sydney** — the top 50 posts of the day from r/popular and r/sydney, shown 5 at a time exactly like the news panel (rotate every 20 s, ‹ › to step, click to open, refreshed every 30 min). Source: Reddit's public RSS feeds. Reddit has blocked key-free `.json` access since May 2026 and has announced it will switch off RSS feeds (reported for 13 Nov 2026); if that happens the panels show *"Reddit refused the feed"* until a different source is wired in.

**Run**
```
cd lane-cove-weather
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python app.py        (or pythonw.exe for no console)
```

**Window**
- The window is frameless (no Windows title bar). Drag the top bar to move it; drag any edge or corner to resize. Position and size are saved to `settings.json` automatically. Use the – and ✕ buttons to minimise or quit.
- ⚙ opens layout presets (left/right dock, centre, full work area) and exact X/Y/W/H. Positions are clamped per monitor, so a window on a second screen stays there.
- Windows narrower than 760 px switch to a single-column layout.
- The background animation runs at 30 fps, pauses while the window is minimised or hidden, and is a still image when Windows "Animation effects" is off (reduced motion).

**Architecture**
- `PolledStore` (one per source) runs a background thread that owns all network I/O and publishes a lock-guarded snapshot. The first fetch happens on that thread, so the window opens immediately even offline.
- A failed fetch never replaces good data: the last snapshot is kept, the UI shows **Stale**, and the thread retries with exponential back-off (30 s → refresh interval).
- The JS bridge (`API`) only reads snapshots or signals a refresh — no bridge call waits on the network.
- Logging goes to `app.log` (rotating, 3 × 512 KB); only failures, recoveries and user actions are written.

Sources: [Open-Meteo](https://open-meteo.com) · BBC · TechCrunch · Reddit · [Wikimedia Commons](https://commons.wikimedia.org) (images under their individual free licences, credited in the panel)
