"""
Desktop Live Feed — Transparent Overlay Ticker
================================================
A see-through horizontal news ticker that sits on top of your desktop.
Headlines are clickable (open in browser). Stocks & crypto float alongside.

OS:  Windows (uses -transparentcolor and -topmost)
Run: python desktop_feed.py

Requirements:
  pip install requests beautifulsoup4
  tkinter — bundled with standard Python on Windows
"""

import tkinter as tk
import threading
import json
import urllib.request
import urllib.parse
import webbrowser
import time
import re
from datetime import datetime

try:
    from bs4 import BeautifulSoup
    BS4 = True
except ImportError:
    BS4 = False

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
CITY              = "San Diego"
PANEL_W           = 800       # panel width
PANEL_H           = 400       # panel height
PANEL_X           = -1        # -1 = right edge of screen
PANEL_Y           = -1        # -1 = bottom edge of screen
SCROLL_PX         = 1         # pixels per tick (vertical)
SCROLL_MS         = 30        # ms per tick (~33 fps)
ROW_H             = 38        # px height per headline row
FONT_SIZE         = 10
HEADER_H          = 28        # top bar (clock + stats)
FOOTER_H          = 22        # bottom bar (stocks/crypto strip)

# Refresh intervals (seconds)
REFRESH_NEWS      = 90
REFRESH_STOCKS    = 20
REFRESH_CRYPTO    = 35

STOCKS  = ["AAPL","MSFT","GOOGL","TSLA","AMZN","NVDA","META","SPY","QQQ","AMD"]
CRYPTOS = ["bitcoin","ethereum","solana","dogecoin","ripple","cardano"]

# ── Windows transparency ──
# The window bg is set to TRANSPARENT_KEY; Windows makes that color see-through.
# The canvas background is a real (opaque) dark color for the panel body.
TRANSPARENT_KEY = "#010101"

# ── Palette ──
BG_PANEL  = "#0e1016"         # main panel background
BG_HEADER = "#0a0c11"         # header/footer strip
BG_ROW_A  = "#0e1016"         # alternating row colours
BG_ROW_B  = "#111520"
TEXT_COL  = "#dde3ee"
ACCENT    = "#00e5a0"
ACCENT2   = "#00b4d8"
RED       = "#ff4d6d"
GREEN     = "#00e5a0"
YELLOW    = "#ffd166"
SUBTEXT   = "#4a5568"
FONT      = ("Courier New", FONT_SIZE, "bold")
FONT_BODY = ("Helvetica", FONT_SIZE)
FONT_SM   = ("Helvetica", 8)

# ─────────────────────────────────────────────
# SOURCE COLOR MAP  (6-digit hex only — no alpha)
# ─────────────────────────────────────────────
SOURCE_COLORS = {
    "reuters":      "#e8a838",
    "bbc":          "#ee3030",
    "ap":           "#c0392b",
    "cnn":          "#cc0000",
    "npr":          "#4a9eda",
    "guardian":     "#0084c6",
    "al jazeera":   "#00703c",
    "sky":          "#e63946",
    "dw":           "#c8a020",
    "france":       "#003f8a",
    "politico":     "#d4af37",
    "hill":         "#8e44ad",
    "axios":        "#ff6b35",
    "nasa":         "#0b3d91",
    "science":      "#27ae60",
    "new scientist":"#16a085",
    "nature":       "#2e86ab",
    "ars":          "#e67e22",
    "verge":        "#7c6af7",
    "wired":        "#c0392b",
    "techcrunch":   "#0a84ff",
    "hacker":       "#ff6600",
    "mit":          "#a31f34",
    "zdnet":        "#e74c3c",
    "engadget":     "#00adef",
    "marketwatch":  "#00bc8c",
    "coindesk":     "#1652f0",
    "cointelegraph":"#d4a800",
    "decrypt":      "#7b2fff",
    "espn":         "#d50a0a",
    "reddit":       "#ff4500",
    "hn":           "#ff6600",
    "github":       "#58a6ff",
    "hckr":         "#ff6600",
}

def src_color(source):
    s = source.lower()
    for key, col in SOURCE_COLORS.items():
        if key in s:
            return col
    return ACCENT2


# ─────────────────────────────────────────────
# FETCHERS
# ─────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

def fetch_url(url, timeout=10):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:
        return None


# ── RSS parser (stdlib only) ──────────────────
def parse_rss(raw, source, max_items=8):
    import xml.etree.ElementTree as ET
    items = []
    if not raw:
        return items
    try:
        root = ET.fromstring(raw)
        ns   = {"atom": "http://www.w3.org/2005/Atom"}
        for el in list(root.iter("item")) + list(root.findall("atom:entry", ns)):
            if len(items) >= max_items:
                break
            title = (
                el.findtext("title") or
                el.findtext("atom:title", namespaces=ns) or ""
            ).strip().replace("\n", " ")
            link = (
                el.findtext("link") or
                el.findtext("atom:link", namespaces=ns) or ""
            ).strip()
            if title:
                items.append({"source": source, "title": title, "url": link})
    except Exception:
        pass
    return items


# ── Scrapers ──────────────────────────────────

def scrape_hn():
    """Hacker News top stories via their free JSON API."""
    items = []
    try:
        raw = fetch_url("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=6)
        if not raw:
            return items
        ids = json.loads(raw)[:20]
        for story_id in ids[:15]:
            r = fetch_url(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json", timeout=5)
            if not r:
                continue
            d = json.loads(r)
            title = d.get("title", "")
            url   = d.get("url", f"https://news.ycombinator.com/item?id={story_id}")
            score = d.get("score", 0)
            if title and score > 50:
                items.append({"source": "HN", "title": f"[{score}▲] {title}", "url": url})
    except Exception:
        pass
    return items


def scrape_reddit_news():
    """Reddit r/worldnews and r/technology via JSON API (no auth needed)."""
    items = []
    subs = [("r/worldnews", "WorldNews"), ("r/technology", "r/tech"),
            ("r/science", "r/science"), ("r/stocks", "r/stocks")]
    for sub, label in subs:
        raw = fetch_url(f"https://www.reddit.com/{sub}.json?limit=10&t=day", timeout=8)
        if not raw:
            continue
        try:
            posts = json.loads(raw)["data"]["children"]
            for p in posts[:6]:
                d     = p["data"]
                title = d.get("title", "").strip()
                url   = d.get("url", "")
                score = d.get("score", 0)
                nsfw  = d.get("over_18", False)
                if title and not nsfw and score > 100:
                    items.append({"source": label, "title": title, "url": url})
        except Exception:
            continue
    return items


def scrape_github_trending():
    """GitHub trending repos — scrape the HTML."""
    items = []
    if not BS4:
        return items
    raw = fetch_url("https://github.com/trending", timeout=10)
    if not raw:
        return items
    try:
        soup = BeautifulSoup(raw, "html.parser")
        for repo in soup.select("article.Box-row")[:10]:
            name_el = repo.select_one("h2 a")
            desc_el = repo.select_one("p")
            stars_el = repo.select_one("span.d-inline-block.float-sm-right")
            if not name_el:
                continue
            name = name_el.get_text(strip=True).replace("\n","").replace(" ","")
            desc = desc_el.get_text(strip=True) if desc_el else ""
            stars = stars_el.get_text(strip=True) if stars_el else ""
            title = f"{name}"
            if desc:
                title += f" — {desc[:80]}"
            if stars:
                title += f"  ★{stars.strip()}"
            url = "https://github.com" + name_el.get("href","")
            items.append({"source": "GitHub↑", "title": title, "url": url})
    except Exception:
        pass
    return items


def scrape_producthunt():
    """Product Hunt top posts via their RSS."""
    raw = fetch_url("https://www.producthunt.com/feed", timeout=8)
    return parse_rss(raw, "ProductHunt", max_items=6)


def scrape_arxiv():
    """arXiv CS + AI recent papers via RSS."""
    items = []
    feeds = [
        ("arXiv·AI",  "https://rss.arxiv.org/rss/cs.AI"),
        ("arXiv·ML",  "https://rss.arxiv.org/rss/cs.LG"),
    ]
    for label, url in feeds:
        raw = fetch_url(url, timeout=8)
        items += parse_rss(raw, label, max_items=5)
    return items


# ── RSS sources ───────────────────────────────
RSS_FEEDS = [
    ("Reuters World",    "https://feeds.reuters.com/reuters/topNews"),
    ("Reuters Biz",      "https://feeds.reuters.com/reuters/businessNews"),
    ("Reuters Tech",     "https://feeds.reuters.com/reuters/technologyNews"),
    ("BBC World",        "http://feeds.bbci.co.uk/news/world/rss.xml"),
    ("BBC Tech",         "http://feeds.bbci.co.uk/news/technology/rss.xml"),
    ("BBC Business",     "http://feeds.bbci.co.uk/news/business/rss.xml"),
    ("AP Top",           "https://rsshub.app/apnews/topics/apf-topnews"),
    ("AP World",         "https://rsshub.app/apnews/topics/apf-intlnews"),
    ("CNN Top",          "http://rss.cnn.com/rss/edition.rss"),
    ("CNN World",        "http://rss.cnn.com/rss/edition_world.rss"),
    ("CNN Money",        "http://rss.cnn.com/rss/money_latest.rss"),
    ("NPR News",         "https://feeds.npr.org/1001/rss.xml"),
    ("NPR World",        "https://feeds.npr.org/1004/rss.xml"),
    ("Guardian World",   "https://www.theguardian.com/world/rss"),
    ("Guardian US",      "https://www.theguardian.com/us-news/rss"),
    ("Guardian Tech",    "https://www.theguardian.com/technology/rss"),
    ("Al Jazeera",       "https://www.aljazeera.com/xml/rss/all.xml"),
    ("Sky News",         "https://feeds.skynews.com/feeds/rss/world.xml"),
    ("DW News",          "https://rss.dw.com/rdf/rss-en-all"),
    ("France 24",        "https://www.france24.com/en/rss"),
    ("Politico",         "https://rss.politico.com/politics-news.xml"),
    ("The Hill",         "https://thehill.com/news/feed/"),
    ("Axios",            "https://api.axios.com/feed/"),
    ("NASA",             "https://www.nasa.gov/rss/dyn/breaking_news.rss"),
    ("Science Daily",    "https://www.sciencedaily.com/rss/all.xml"),
    ("New Scientist",    "https://www.newscientist.com/feed/home/"),
    ("Nature",           "https://www.nature.com/nature.rss"),
    ("Ars Technica",     "https://feeds.arstechnica.com/arstechnica/index"),
    ("The Verge",        "https://www.theverge.com/rss/index.xml"),
    ("Wired",            "https://www.wired.com/feed/rss"),
    ("TechCrunch",       "https://techcrunch.com/feed/"),
    ("MIT Tech Review",  "https://www.technologyreview.com/topnews.rss"),
    ("ZDNet",            "https://www.zdnet.com/news/rss.xml"),
    ("Engadget",         "https://www.engadget.com/rss.xml"),
    ("MarketWatch",      "http://feeds.marketwatch.com/marketwatch/topstories/"),
    ("CoinDesk",         "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("CoinTelegraph",    "https://cointelegraph.com/rss"),
    ("Decrypt",          "https://decrypt.co/feed"),
    ("ESPN",             "https://www.espn.com/espn/rss/news"),
    ("BBC Sport",        "http://feeds.bbci.co.uk/sport/rss.xml"),
    ("Product Hunt",     "https://www.producthunt.com/feed"),
]

def fetch_all_news():
    items = []
    threads = []
    lock = threading.Lock()

    def rss_worker(source, url):
        r = fetch_url(url)
        with lock:
            items.extend(parse_rss(r, source, max_items=8))

    def scraper_worker(fn):
        result = fn()
        with lock:
            items.extend(result)

    for source, url in RSS_FEEDS:
        t = threading.Thread(target=rss_worker, args=(source, url), daemon=True)
        threads.append(t)

    for fn in [scrape_hn, scrape_reddit_news, scrape_github_trending, scrape_arxiv]:
        t = threading.Thread(target=scraper_worker, args=(fn,), daemon=True)
        threads.append(t)

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=12)

    # dedupe by title
    seen = set()
    deduped = []
    for item in items:
        key = item["title"][:60].lower()
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def fetch_stocks(symbols):
    results = {}
    url = (
        "https://query1.finance.yahoo.com/v7/finance/quote"
        f"?symbols={urllib.parse.quote(','.join(symbols))}"
        "&fields=regularMarketPrice,regularMarketChangePercent"
    )
    raw = fetch_url(url)
    if not raw:
        return results
    try:
        for q in json.loads(raw)["quoteResponse"]["result"] or []:
            sym = q.get("symbol","")
            results[sym] = {
                "price":  q.get("regularMarketPrice", 0),
                "chg":    q.get("regularMarketChangePercent", 0),
            }
    except Exception:
        pass
    return results


def fetch_crypto(ids):
    results = {}
    url = (
        "https://api.coingecko.com/api/v3/simple/price"
        f"?ids={urllib.parse.quote(','.join(ids))}"
        "&vs_currencies=usd&include_24hr_change=true"
    )
    raw = fetch_url(url)
    if not raw:
        return results
    try:
        for cid, v in json.loads(raw).items():
            results[cid] = {"price": v.get("usd",0), "chg": v.get("usd_24h_change",0)}
    except Exception:
        pass
    return results


def fetch_weather(city):
    geo = fetch_url(
        f"https://geocoding-api.open-meteo.com/v1/search"
        f"?name={urllib.parse.quote(city)}&count=1&language=en&format=json")
    if not geo:
        return None
    try:
        loc = json.loads(geo)["results"][0]
        lat, lon = loc["latitude"], loc["longitude"]
    except Exception:
        return None
    wx = fetch_url(
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,weathercode,windspeed_10m"
        f"&temperature_unit=fahrenheit&windspeed_unit=mph&timezone=auto")
    if not wx:
        return None
    try:
        cur = json.loads(wx)["current"]
        icons = {0:"☀",1:"🌤",2:"⛅",3:"☁",45:"🌫",61:"🌧",71:"❄",80:"🌦",95:"⛈"}
        code  = cur.get("weathercode",0)
        icon  = next((v for k,v in icons.items() if code==k), "🌡")
        return f"{icon} {city}  {cur.get('temperature_2m','--')}°F"
    except Exception:
        return None


# ─────────────────────────────────────────────
# VERTICAL PANEL APP
# ─────────────────────────────────────────────

class TickerApp(tk.Tk):
    def __init__(self):
        super().__init__()

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        px = sw - PANEL_W - 12  if PANEL_X == -1 else PANEL_X
        py = sh - PANEL_H - 12  if PANEL_Y == -1 else PANEL_Y

        self.geometry(f"{PANEL_W}x{PANEL_H}+{px}+{py}")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-transparentcolor", TRANSPARENT_KEY)
        self.configure(bg=TRANSPARENT_KEY)
        self.wm_attributes("-alpha", 0.82)   # more transparent than before

        # ── State ──
        self._headlines  = []
        self._stocks     = {}
        self._crypto     = {}
        self._weather    = ""
        self._lock       = threading.Lock()

        # Scroll state — vertical
        self._rows       = []    # list of {"source","title","url","color"}
        self._y_offset   = 0.0   # fractional pixel offset from top
        self._total_rows_h = 0   # total height of all rows (px)
        self._speed      = SCROLL_PX
        self._paused     = False
        self._hover_row  = None  # row index under mouse

        # Drag to move
        self._drag_x = 0
        self._drag_y = 0

        self._build_ui()
        self._schedule_all()
        self._scroll_tick()

    # ─── UI ──────────────────────────────────

    def _build_ui(self):
        feed_h = PANEL_H - HEADER_H - FOOTER_H

        # ── Header canvas ──
        self._hdr = tk.Canvas(
            self, width=PANEL_W, height=HEADER_H,
            bg=BG_HEADER, bd=0, highlightthickness=0)
        self._hdr.pack(side="top", fill="x")

        # accent line bottom of header
        self._hdr.create_line(0, HEADER_H-1, PANEL_W, HEADER_H-1,
                              fill=ACCENT, width=1)

        self._clock_id = self._hdr.create_text(
            8, HEADER_H//2, text="", fill=ACCENT,
            font=("Courier New", 9, "bold"), anchor="w")

        self._count_id = self._hdr.create_text(
            PANEL_W - 8, HEADER_H//2, text="loading…",
            fill=SUBTEXT, font=("Helvetica", 8), anchor="e")

        self._weather_id = self._hdr.create_text(
            PANEL_W//2, HEADER_H//2, text="",
            fill=ACCENT2, font=("Helvetica", 9), anchor="center")

        # drag header to move window
        self._hdr.bind("<ButtonPress-1>",   self._drag_start)
        self._hdr.bind("<B1-Motion>",       self._drag_motion)
        self._hdr.bind("<Button-3>",        self._on_right_click)

        # ── Feed canvas ──
        self._canvas = tk.Canvas(
            self, width=PANEL_W, height=feed_h,
            bg=BG_PANEL, bd=0, highlightthickness=0)
        self._canvas.pack(side="top", fill="x")

        self._canvas.bind("<Motion>",    self._on_motion)
        self._canvas.bind("<Leave>",     self._on_leave)
        self._canvas.bind("<Button-1>",  self._on_click)
        self._canvas.bind("<Button-3>",  self._on_right_click)

        # ── Footer canvas (stocks + crypto ticker) ──
        self._ftr = tk.Canvas(
            self, width=PANEL_W, height=FOOTER_H,
            bg=BG_HEADER, bd=0, highlightthickness=0)
        self._ftr.pack(side="top", fill="x")
        self._ftr.create_line(0, 0, PANEL_W, 0, fill=ACCENT, width=1)
        self._ftr_text_id = self._ftr.create_text(
            8, FOOTER_H//2, text="", fill=TEXT_COL,
            font=("Courier New", 8), anchor="w")

        # ── Right-click context menu ──
        self._menu = tk.Menu(
            self, tearoff=0, bg="#13161e", fg=TEXT_COL,
            activebackground="#1e2235", activeforeground=TEXT_COL,
            font=("Helvetica", 9))
        self._menu.add_command(label="⏸  Pause / Resume",  command=self._toggle_pause)
        self._menu.add_command(label="🐢  Slower",          command=lambda: self._adj_speed(-1))
        self._menu.add_command(label="🐇  Faster",          command=lambda: self._adj_speed(+1))
        self._menu.add_separator()
        self._menu.add_command(label="↗  Move top-right",   command=self._snap_top_right)
        self._menu.add_command(label="↘  Move btm-right",   command=self._snap_btm_right)
        self._menu.add_command(label="↙  Move btm-left",    command=self._snap_btm_left)
        self._menu.add_command(label="↖  Move top-left",    command=self._snap_top_left)
        self._menu.add_separator()
        self._menu.add_command(label="✕  Quit",             command=self.destroy)

        self._tick_clock()

    # ─── Row list ────────────────────────────

    def _build_rows(self):
        """Convert current headlines into a flat row list."""
        rows = []
        for item in self._headlines:
            rows.append({
                "source": item["source"],
                "title":  item["title"],
                "url":    item.get("url", ""),
                "color":  src_color(item["source"]),
            })
        return rows

    def reload_rows(self):
        with self._lock:
            self._rows = self._build_rows()
        self._total_rows_h = len(self._rows) * ROW_H
        self._y_offset = 0.0
        self._update_footer()
        self._update_count()

    def _update_footer(self):
        """Rebuild the footer stocks/crypto text."""
        parts = []
        cmap = {"bitcoin":"BTC","ethereum":"ETH","solana":"SOL",
                "dogecoin":"DOGE","ripple":"XRP","cardano":"ADA"}
        for sym, info in self._stocks.items():
            chg = info["chg"]
            arr = "▲" if chg >= 0 else "▼"
            parts.append(f"{sym} ${info['price']:,.0f} {arr}{abs(chg):.1f}%")
        for cid, info in self._crypto.items():
            chg = info["chg"]
            arr = "▲" if chg >= 0 else "▼"
            sym = cmap.get(cid, cid[:4].upper())
            p   = info["price"]
            ps  = f"${p:,.2f}" if p >= 1 else f"${p:,.4f}"
            parts.append(f"{sym} {ps} {arr}{abs(chg):.1f}%")
        self._ftr.itemconfig(self._ftr_text_id,
                             text="  ◆  ".join(parts) if parts else "loading…")

    def _update_count(self):
        n = len(self._rows)
        src = len(RSS_FEEDS) + 4
        self._hdr.itemconfig(self._count_id,
                             text=f"{n} headlines · {src} sources")

    # ─── Draw ────────────────────────────────

    def _redraw_feed(self):
        self._canvas.delete("row")
        if not self._rows:
            self._canvas.create_text(
                PANEL_W//2, (PANEL_H - HEADER_H - FOOTER_H)//2,
                text="Loading headlines…", fill=SUBTEXT,
                font=FONT_BODY, tags="row")
            return

        feed_h   = PANEL_H - HEADER_H - FOOTER_H
        n        = len(self._rows)
        total_h  = n * ROW_H
        y_start  = -int(self._y_offset)

        # draw two passes for seamless looping
        for loop in range(2):
            base_y = y_start + loop * total_h
            for i, row in enumerate(self._rows):
                y = base_y + i * ROW_H
                if y + ROW_H < 0 or y > feed_h:
                    continue

                # row background
                bg = BG_ROW_A if i % 2 == 0 else BG_ROW_B
                is_hover = (loop == 0 and i == self._hover_row)
                if is_hover:
                    bg = "#1a2035"

                self._canvas.create_rectangle(
                    0, y, PANEL_W, y + ROW_H,
                    fill=bg, outline="", tags="row")

                # left color bar
                self._canvas.create_rectangle(
                    0, y, 3, y + ROW_H,
                    fill=row["color"], outline="", tags="row")

                # source badge
                src_txt = row["source"][:12]
                self._canvas.create_text(
                    10, y + ROW_H//2,
                    text=src_txt, fill=row["color"],
                    font=("Courier New", 7, "bold"),
                    anchor="w", tags="row")

                # headline text — truncate to fit
                title = row["title"]
                col   = "#ffffff" if is_hover and row["url"] else TEXT_COL
                self._canvas.create_text(
                    105, y + ROW_H//2,
                    text=title, fill=col,
                    font=FONT_BODY, anchor="w",
                    width=PANEL_W - 115,
                    tags="row")

                # link underline hint
                if is_hover and row["url"]:
                    self._canvas.create_line(
                        105, y + ROW_H - 4, PANEL_W - 8, y + ROW_H - 4,
                        fill=ACCENT2, width=1, tags="row")

                # separator
                self._canvas.create_line(
                    0, y + ROW_H - 1, PANEL_W, y + ROW_H - 1,
                    fill="#1a1d27", width=1, tags="row")

    # ─── Scroll loop ─────────────────────────

    def _scroll_tick(self):
        if not self._paused and self._total_rows_h > 0:
            self._y_offset += self._speed
            if self._y_offset >= self._total_rows_h:
                self._y_offset -= self._total_rows_h
        self._redraw_feed()
        self.after(SCROLL_MS, self._scroll_tick)

    # ─── Clock ───────────────────────────────

    def _tick_clock(self):
        self._hdr.itemconfig(
            self._clock_id,
            text=datetime.now().strftime("◈ %a %b %d  %H:%M:%S"))
        if self._weather:
            self._hdr.itemconfig(self._weather_id, text=self._weather)
        self.after(1000, self._tick_clock)

    # ─── Mouse ───────────────────────────────

    def _row_at(self, my):
        """Return the row index (in self._rows) under canvas y coordinate."""
        if not self._rows:
            return None
        feed_h  = PANEL_H - HEADER_H - FOOTER_H
        n       = len(self._rows)
        total_h = n * ROW_H
        y_start = -int(self._y_offset)
        # check both loop passes
        for loop in range(2):
            base_y = y_start + loop * total_h
            for i in range(n):
                y = base_y + i * ROW_H
                if y <= my < y + ROW_H:
                    return i
        return None

    def _on_motion(self, e):
        idx = self._row_at(e.y)
        if idx != self._hover_row:
            self._hover_row = idx
            if idx is not None and self._rows[idx]["url"]:
                self._canvas.config(cursor="hand2")
                self._paused = True
            else:
                self._canvas.config(cursor="")
                self._paused = False

    def _on_leave(self, e):
        self._hover_row = None
        self._paused = False
        self._canvas.config(cursor="")

    def _on_click(self, e):
        idx = self._row_at(e.y)
        if idx is not None:
            url = self._rows[idx]["url"]
            if url:
                webbrowser.open(url)

    def _on_right_click(self, e):
        self._menu.post(e.x_root, e.y_root)

    # ─── Drag to move ────────────────────────

    def _drag_start(self, e):
        self._drag_x = e.x_root - self.winfo_x()
        self._drag_y = e.y_root - self.winfo_y()

    def _drag_motion(self, e):
        x = e.x_root - self._drag_x
        y = e.y_root - self._drag_y
        self.geometry(f"+{x}+{y}")

    # ─── Snap positions ──────────────────────

    def _snap(self, x, y):
        self.geometry(f"{PANEL_W}x{PANEL_H}+{x}+{y}")

    def _snap_top_right(self):
        self._snap(self.winfo_screenwidth() - PANEL_W - 12, 12)

    def _snap_btm_right(self):
        self._snap(self.winfo_screenwidth() - PANEL_W - 12,
                   self.winfo_screenheight() - PANEL_H - 12)

    def _snap_btm_left(self):
        self._snap(12, self.winfo_screenheight() - PANEL_H - 12)

    def _snap_top_left(self):
        self._snap(12, 12)

    # ─── Controls ────────────────────────────

    def _toggle_pause(self):
        self._paused = not self._paused

    def _adj_speed(self, delta):
        self._speed = max(1, min(8, self._speed + delta))

    # ─── Data refresh schedulers ─────────────

    def _schedule_all(self):
        self._do_refresh_news()
        self._do_refresh_stocks()
        self._do_refresh_crypto()
        self._do_refresh_weather()

    def _do_refresh_news(self):
        def _w():
            news = fetch_all_news()
            with self._lock:
                self._headlines = news
            self.after(0, self.reload_rows)
        threading.Thread(target=_w, daemon=True).start()
        self.after(REFRESH_NEWS * 1000, self._do_refresh_news)

    def _do_refresh_stocks(self):
        def _w():
            s = fetch_stocks(STOCKS)
            with self._lock:
                self._stocks = s
            self.after(0, self._update_footer)
        threading.Thread(target=_w, daemon=True).start()
        self.after(REFRESH_STOCKS * 1000, self._do_refresh_stocks)

    def _do_refresh_crypto(self):
        def _w():
            c = fetch_crypto(CRYPTOS)
            with self._lock:
                self._crypto = c
            self.after(0, self._update_footer)
        threading.Thread(target=_w, daemon=True).start()
        self.after(REFRESH_CRYPTO * 1000, self._do_refresh_crypto)

    def _do_refresh_weather(self):
        def _w():
            wx = fetch_weather(CITY)
            with self._lock:
                self._weather = wx or ""
        threading.Thread(target=_w, daemon=True).start()
        self.after(600 * 1000, self._do_refresh_weather)


# ─────────────────────────────────────────────
if __name__ == "__main__":
    app = TickerApp()
    app.mainloop()
