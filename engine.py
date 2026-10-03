import re, json, difflib, time, random, sqlite3, shutil, hashlib, datetime as dt, traceback
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
import requests_cache, pandas as pd
from bs4 import BeautifulSoup
from sources import OLX, MODELS, REGIONS

D = Path("data"); D.mkdir(exist_ok=True)
SPEED = {"Hati-hati": (4, 8), "Seimbang": (2.5, 5), "Cepat": (1.5, 3)}
QUERIES = [k for k in MODELS if not any(k != j and k.lower().startswith(j.lower() + " ") for j in MODELS)]
DEFAULT = dict(target=10000, speed="Seimbang", queries=[q.lower() for q in QUERIES], max_pages=15, timeout=45, retries=2,
               max_fails=4, mode="auto", headed=False, dedup_judul=True, rescue=True, max_detail=150, semua=False, bad_pages=3, max_requests=6000, cache_hours=24, batch_size=60, batch_pause=90,
               price_min=3_000_000, price_max=300_000_000)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
BOT = ("captcha", "cf-chl", "just a moment", "access denied", "attention required", "unusual traffic", "are you a robot")
OUT = re.compile(r"\b(sleman|yogyakarta|bantul|jawa tengah|jawa timur|banten|tangerang|banjarnegara|banjarmasin)\b")
YR = re.compile(r"\b(19[9]\d|20[0-4]\d)\b")
RX = [(re.compile(rf"\b{re.escape(n.lower())}\b"), n, p) for n, p in sorted(REGIONS, key=lambda r: -len(r[0]))]
MP = [(re.compile(r"(?<![a-z0-9])" + r"[\s-]*".join(re.findall(r"[a-z]+|\d+", k.lower())) + r"(?![a-z0-9])"), k)
      for k in sorted(MODELS, key=len, reverse=True)]
ICON = {"OK": "✅", "KOSONG": "⚪", "HABIS": "⚪", "ULANG": "⚪", "GAGAL": "❌", "ANOMALI": "⛔"}


class Blocked(Exception): pass
class Stop(Exception): pass


def new_state():
    return dict(running=False, stop=False, ok=0, rejected=0, req=0, msg="Belum berjalan", log=[], errs={}, why={},
                cur="", cur_t=0, snaps=0, pages=[], pages_n=0, pg_ok=0, pg_bad=0, quota={}, dupn=0, outn=0, susn=0, resc=0, cd=0, ct=0, capped=0, t0=0)


def log(S, m, lv="INFO"):
    line = f"{time.strftime('%H:%M:%S')} [{lv}] {m}"
    S["log"].append(line); del S["log"][:-800]
    try:
        with open(D / "scraper.log", "a", encoding="utf-8") as fh: fh.write(time.strftime("%Y-%m-%d ") + line + "\n")
    except OSError: pass


def snap(S, url, body, tag):
    """Simpan cuplikan respons bermasalah (maks 3 per run) ke data/debug/."""
    if S["snaps"] >= 3: return
    S["snaps"] += 1; (D / "debug").mkdir(exist_ok=True)
    p = D / "debug" / f"{time.strftime('%H%M%S')}_{tag}.html"
    p.write_text(f"<!-- {url} -->\n" + str(body)[:200_000], encoding="utf-8"); log(S, f"snapshot disimpan: {p}", "WARN")


# ---------- Fetcher: jeda adaptif, cache, batch, batas request, circuit breaker ----------
class Fetcher:
    def __init__(s, cfg, S):
        s.cfg, s.S, s.rob, s.n, s.fails, s.streak, s.mult, s.last = cfg, S, {}, 0, 0, 0, 1.0, {}
        s.ses = requests_cache.CachedSession(str(D / "http_cache"), backend="sqlite",
                                             expire_after=cfg["cache_hours"] * 3600, allowable_codes=(200,))
        s.ses.headers.update({"User-Agent": cfg.get("ua") or UA, "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
                              "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"})

    def _robots(s, base): return s.ses.get(base + "/robots.txt", timeout=(10, 20)).text

    def _fetch(s, url):
        r = s.ses.get(url, timeout=(10, s.cfg["timeout"])); return r.status_code, r.text, r.from_cache, r.headers

    def wait(s, sec):
        end = time.time() + sec
        while time.time() < end:
            if s.S["stop"]: raise Stop
            time.sleep(min(1, max(0, end - time.time())))

    def allowed(s, url):
        u = urlparse(url); base = f"{u.scheme}://{u.netloc}"
        first = base not in s.rob
        if first:
            rp = RobotFileParser()
            try: rp.parse(s._robots(base).splitlines())
            except Exception as e:
                rp = None; log(s.S, f"robots.txt tidak terbaca ({type(e).__name__}); lanjut tanpa aturan robots", "WARN")
            s.rob[base] = rp
        ok = s.rob[base] is None or s.rob[base].can_fetch("*", url)
        if first: log(s.S, f"robots.txt {'terbaca' if s.rob[base] else 'tidak tersedia'}: URL pencarian {'DIIZINKAN' if ok else 'DILARANG'}", "INFO" if ok else "WARN")
        return ok

    def get(s, url):
        if s.S["stop"]: raise Stop
        if not s.allowed(url):
            s.last = dict(status="robots", sec=0, kb=0); log(s.S, f"robots.txt melarang: {url}", "WARN"); return None
        c = s.cfg
        if s.n >= c["max_requests"]: s.S["msg"] = "Batas request per run tercapai"; raise Stop
        for a in range(c["retries"]):
            t0 = time.time(); s.S["cur"], s.S["cur_t"] = url, t0; hdr = {}; st = kind = body = None; msg = ""
            try:
                st, body, cached, hdr = s._fetch(url)
                if cached:
                    s.S["cur"] = ""; s.last = dict(status=200, sec=0.0, kb=len(body) // 1024); return body
            except Exception as e:
                kind, msg = type(e).__name__, str(e).split("\n")[0][:140]
                if kind == "Error": kind = msg[:40]       # galat Playwright (mis. net::ERR_...)
            el = time.time() - t0; s.n += 1; s.S["req"] = s.n; s.S["cur"] = ""
            s.last = dict(status=st or kind, sec=el, kb=len(body or "") // 1024)
            if st == 404: log(s.S, f"404 (akhir hasil): {url}", "WARN"); return None
            if kind is None and st == 200 and len(body) < 30000 and any(k in body.lower() for k in BOT): kind = "TantanganBot"
            if kind is None and st != 200: kind = f"HTTP{st}"
            if kind is None:
                s.fails = 0; s.streak += 1
                if s.streak % 15 == 0 and s.mult > 1: s.mult = max(1.0, s.mult * .75); log(s.S, f"jeda dipercepat ×{s.mult:.1f}")
                lo, hi = c["delay"]; s.wait(random.uniform(lo, hi) * s.mult)
                if s.n % c["batch_size"] == 0:
                    log(s.S, f"batch selesai ({s.n} request), istirahat {c['batch_pause']}s"); s.wait(c["batch_pause"])
                return body
            s.fails += 1; s.streak = 0; s.mult = min(s.mult * 2, 8); s.S["errs"][kind] = s.S["errs"].get(kind, 0) + 1
            log(s.S, f"GAGAL {kind} {el:.1f}s (percobaan {a + 1}/{c['retries']}, beruntun {s.fails}, jeda ×{s.mult:.0f}) {url} {msg}", "ERROR")
            if body is not None: snap(s.S, url, body, kind)
            if s.fails >= c["max_fails"]: raise Blocked(f"{s.fails} kegagalan beruntun, terakhir {kind}")
            ra = hdr.get("Retry-After", "")
            s.wait(min(int(ra), 900) if ra.isdigit() else min(10 * 2 ** a, 120))
        return None


def diagnose(url):
    """Tes bertahap: DNS -> pembanding -> TCP -> TLS -> respons HTTP pertama. Mengembalikan (baris, level)."""
    import socket, ssl, requests
    out, host = [], urlparse(url).netloc
    try:
        t = time.time(); out.append(f"DNS {host} -> {socket.gethostbyname(host)} ({time.time() - t:.1f}s)")
    except Exception as e: return out + [f"DNS GAGAL: {e}. Periksa internet/DNS/VPN."], "dns"
    try:
        t = time.time(); r = requests.get("https://example.com", timeout=(10, 20)); out.append(f"Pembanding example.com -> HTTP {r.status_code} ({time.time() - t:.1f}s)")
    except Exception as e: return out + [f"Pembanding example.com gagal ({type(e).__name__}): internet/VPN/proxy di komputer ini bermasalah."], "net"
    t = time.time()
    try: sk = socket.create_connection((host, 443), timeout=10); out.append(f"1. TCP connect OK ({time.time() - t:.1f}s)")
    except Exception as e: return out + [f"1. TCP connect GAGAL setelah {time.time() - t:.0f}s ({type(e).__name__}) -> IP Anda diblokir sementara atau rute ISP ke situs bermasalah. Coba jaringan lain (hotspot HP); jangan ulangi percobaan terus-menerus."], "tcp"
    t = time.time()
    try: sk = ssl.create_default_context().wrap_socket(sk, server_hostname=host); out.append(f"2. TLS OK ({time.time() - t:.1f}s, {sk.version()})")
    except Exception as e: sk.close(); return out + [f"2. TLS GAGAL setelah {time.time() - t:.0f}s ({type(e).__name__}) -> koneksi diputus saat handshake: penyaringan jaringan/ISP atau server."], "tls"
    t = time.time(); sk.settimeout(25)
    try:
        sk.sendall(f"GET / HTTP/1.1\r\nHost: {host}\r\nUser-Agent: {UA}\r\nAccept: text/html\r\nAccept-Language: id-ID,id;q=0.9\r\nConnection: close\r\n\r\n".encode())
        first = sk.recv(300).decode("latin1").split("\r\n")[0] or "(kosong: koneksi ditutup tanpa jawaban)"
    except Exception as e: return out + [f"3. Tidak ada respons HTTP setelah {time.time() - t:.0f}s ({type(e).__name__}) -> TCP & TLS berhasil, tetapi situs tidak menjawab: penyaringan di sisi situs terhadap klien/IP ini, atau server sangat lambat. Bandingkan dengan membuka URL di browser."], "http"
    finally: sk.close()
    code = first.split(" ")[1] if first.startswith("HTTP/") and " " in first else "?"
    out.append(f"3. Respons pertama setelah {time.time() - t:.1f}s: {first}")
    return out, ("ok" if code[:1] in ("2", "3") else "http")


# ---------- Mode browser (Playwright biasa, tanpa stealth) ----------
class BrowserFetcher(Fetcher):
    """Browser sungguhan; memakai jeda, cache, batas request, dan circuit breaker yang sama dengan Fetcher."""
    def __init__(s, cfg, S):
        s.cfg, s.S, s.rob, s.n, s.fails, s.streak, s.mult, s.last, s.used = cfg, S, {}, 0, 0, 0, 1.0, {}, 0
        import sys, asyncio
        if sys.platform == "win32": asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        from playwright.sync_api import sync_playwright
        s.pw = sync_playwright().start(); head = not cfg.get("headed")
        try: s.br = s.pw.chromium.launch(channel="chrome", headless=head)      # pakai Google Chrome bila terpasang
        except Exception: s.br = s.pw.chromium.launch(headless=head)           # jika tidak, Chromium bawaan Playwright
        kw = dict(locale="id-ID", timezone_id="Asia/Jakarta", viewport={"width": 1366, "height": 850})
        if head:
            pg = s.br.new_page(); kw["user_agent"] = pg.evaluate("navigator.userAgent").replace("HeadlessChrome", "Chrome"); pg.close()
        s.ctx = s.br.new_context(**kw)
        s.ctx.route("**/*", lambda r: r.abort() if r.request.resource_type in ("image", "media", "font") else r.continue_())
        s.page = s.ctx.new_page()

    def _robots(s, base):
        s.page.goto(base + "/robots.txt", timeout=20000); return s.page.inner_text("body")

    def _fetch(s, url):
        f = D / "html_cache" / (hashlib.md5(url.encode()).hexdigest() + ".html")
        if f.exists() and time.time() - f.stat().st_mtime < s.cfg["cache_hours"] * 3600: return 200, f.read_text(encoding="utf-8"), True, {}
        resp = s.page.goto(url, wait_until="domcontentloaded", timeout=s.cfg["timeout"] * 1000)
        try: s.page.wait_for_selector('a[href*="/item/"]', timeout=3000)
        except Exception: pass                                                  # bisa jadi hasil kosong
        body, st = s.page.content(), (resp.status if resp else None)
        if st == 200: f.parent.mkdir(exist_ok=True); f.write_text(body, encoding="utf-8")
        s.used += 1
        if s.used % 250 == 0: s.page.close(); s.page = s.ctx.new_page()          # daur ulang tab agar memori tidak membengkak
        return st, body, False, {}

    def close(s):
        for o in (s.ctx, s.br):
            try: o.close()
            except Exception: pass
        try: s.pw.stop()
        except Exception: pass


def make_fetcher(cfg, S):
    """auto: coba requests (cepat, ringan); bila gagal pindah ke browser. Keduanya wajib lolos preflight."""
    if cfg["mode"] in ("auto", "requests"):
        q = {**cfg, "timeout": 15, "retries": 1, "max_fails": 1} if cfg["mode"] == "auto" else cfg
        try: preflight(cfg, Fetcher(q, S), S); log(S, "Mode aktif: requests"); return Fetcher(cfg, S)
        except Blocked as e:
            if cfg["mode"] == "requests": raise
            log(S, f"Mode requests gagal ({e}); mencoba mode browser...", "WARN"); S["errs"] = {}
    try: b = BrowserFetcher(cfg, S)
    except ImportError: raise Blocked("mode browser butuh Playwright: pip install playwright, lalu: playwright install chromium")
    except Exception as e: raise Blocked(f"browser gagal dijalankan ({str(e).splitlines()[0][:120]}). Coba: playwright install chromium")
    try: preflight(cfg, b, S)
    except Exception: b.close(); raise
    log(S, "Mode aktif: browser"); return b


# ---------- Parsing kartu iklan ----------
def num(t):
    if not t: return None
    vals = []
    for raw, u in re.findall(r"(\d[\d.,]*)\s*(jt|juta|rb|ribu|k(?!m))?", str(t).lower()):
        raw = raw.strip(".,")
        v = float(raw.replace(",", ".")) if u and re.fullmatch(r"\d+[.,]\d{1,2}", raw) else float(re.sub(r"[.,]", "", raw))
        vals.append(v * {"jt": 1e6, "juta": 1e6, "rb": 1e3, "ribu": 1e3, "k": 1e3}.get(u, 1))
    return int(vals[0]) if vals else None   # hanya angka pertama


def find_cards(soup):
    """Elemen berulang (tag+class sama) yang berisi tepat 1 link iklan (/item/) dan harga 'Rp'. Kartu promo kredit (banyak 'Rp') tetap terbaca."""
    g = {}
    for el in soup.find_all(["li", "div", "article", "a"]):
        links = {a["href"].split("?")[0] for a in ([el] if el.name == "a" else []) + el.find_all("a", href=True) if "/item/" in (a.get("href") or "")}
        t = el.get_text(" ", strip=True)
        if len(links) == 1 and len(t) < 700 and re.search(r"rp\.?\s?\d", t, re.I):
            g.setdefault((el.name, tuple(el.get("class") or [])), []).append(el)
    best = max(g.values(), key=len, default=[])
    return best if len(best) >= 3 else []


def auto_fields(c):
    links = ([c] if c.name == "a" else []) + c.find_all("a", href=True)
    a = max((x for x in links if "/item/" in (x.get("href") or "")), key=lambda x: len(x.get_text()))
    parts = [p.strip() for p in c.get_text(" | ", strip=True).split(" | ") if p.strip()]
    price = next((p for p in parts if p.lower().startswith("rp")), None)   # harga = segmen "Rp" pertama (DP/cicilan datang sesudahnya)
    if price and not re.search(r"\d", price) and parts.index(price) + 1 < len(parts): price += " " + parts[parts.index(price) + 1]
    year = next((p for p in parts if YR.fullmatch(p)), None)
    url = urljoin(OLX["base"], a["href"]).split("?")[0].split("#")[0]
    m = re.search(r"iid-(\d+)", url); slug = re.sub(r"-iid-\d+$", "", url.rstrip("/").rsplit("/", 1)[-1])
    return dict(url=url, id=m[1] if m else hashlib.md5(url.encode()).hexdigest()[:12], title=slug.replace("-", " "),
                price=price, year=year, parts=parts, text=" ".join(parts))   # judul diambil dari slug URL (andal)


def parse(html):
    soup = BeautifulSoup(html, "lxml")
    return [auto_fields(c) for c in find_cards(soup)], (soup.title.get_text(strip=True) if soup.title else "")


# ---------- Cleaning ----------
KN = {k: re.sub(r"[^a-z0-9]", "", k.lower()) for k in MODELS}
QMAP = {v: k for k, v in KN.items()}
PROMO = re.compile(r"\b(?:dp|kredit|credit|cicil|cicilan|angsuran|tdp|kredivo)\b", re.I)
CASH = re.compile(r"(?:harga\s*)?(?:cash|tunai|otr)\s*(?:harga)?\s*[:=\-]?\s*(?:rp\.?\s*)?(\d[\d.,]*\s*(?:jt|juta|rb|ribu)?)", re.I)


def alias(t):
    if re.search(r"\bninja\b", t):
        return "Ninja 250" if re.search(r"\b250\b", t) else "Ninja 150" if re.search(r"\b(150|rr|zx[\s-]?150)\b", t) else None


def fuzzy(t, qkey):
    """Toleransi salah ketik (Scoppy, Scooopy, Scopy...). Model yang sedang dicari (qkey) diberi ambang lebih longgar."""
    w = re.findall(r"[a-z0-9]+", t); cs = set(w) | {a + b for a, b in zip(w, w[1:])} | {a + b + c for a, b, c in zip(w, w[1:], w[2:])}
    best, bs = None, 0.0
    for k, kn in KN.items():
        if len(kn) < 5: continue
        s = max((difflib.SequenceMatcher(None, kn, c).ratio() for c in cs if abs(len(c) - len(kn)) <= 2 and (c == kn or not (kn.startswith(c) or c.startswith(kn)))), default=0.0)   # bukan potongan nama
        if s >= (0.7 if k == qkey else 0.82) and s > bs: best, bs = k, s
    return best


def find_model(raw, qkey):
    t = raw["title"].lower()
    for src in (t, raw["text"].lower()):
        k = next((k for rx, k in MP if rx.search(src)), None) or alias(src)
        if k: return k
    return fuzzy(t, qkey)


def pick_region(parts):
    """Wilayah dicocokkan HANYA dari segmen lokasi kartu (batas kata, nama terpanjang dulu)."""
    for p in [x for x in reversed(parts[-3:]) if "," in x] + list(reversed(parts[-2:])):
        t = p.lower()
        if OUT.search(t): continue
        for rx, name, prov in RX:
            if rx.search(t): return name, prov, p
    return None, None, (parts[-2] if len(parts) > 1 else "")


def clean(raw, prov, cfg, qkey=None):
    key = find_model(raw, qkey)
    brand, cc, trans = MODELS[key] if key else (None,) * 3
    city, rprov, lraw = pick_region(raw["parts"])
    ym = YR.search(raw["text"]); year = int(raw["year"]) if raw["year"] else (int(ym[1]) if ym else None)
    km, price, why = raw.get("km"), num(raw["price"]), []
    if not key: why.append("model tidak dikenali")
    if not city: why.append("lokasi tidak dikenali")
    elif rprov != prov: why.append("lokasi di luar wilayah query")
    if not year or not 1995 <= year <= dt.date.today().year + 1: why.append("tahun tidak valid")
    if price is None or not cfg["price_min"] <= price <= cfg["price_max"]: why.append("harga tidak wajar")
    row = dict(ad_id=raw["id"], url=raw["url"], brand=brand, model=key, transmisi=trans, tahun=year, kilometer=km, cc=cc,
               harga=price, lokasi=f"{city}, {rprov}" if city else None, provinsi=rprov, lokasi_mentah=lraw)
    return row, why


# ---------- Penyimpanan, penilaian & ekspor rapi ----------
LC = ["ad_id", "url", "brand", "model", "transmisi", "tahun", "kilometer", "cc", "harga", "lokasi", "provinsi", "lokasi_mentah"]


def db():
    c = sqlite3.connect(D / "olx.db")
    c.execute("CREATE TABLE IF NOT EXISTS listings (ad_id TEXT PRIMARY KEY, url TEXT, brand TEXT, model TEXT, transmisi TEXT, tahun INTEGER, kilometer INTEGER, cc INTEGER, harga INTEGER, lokasi TEXT, provinsi TEXT, lokasi_mentah TEXT, dupkey TEXT, first_seen TEXT, last_seen TEXT, active INTEGER, rescued INTEGER DEFAULT 0)")
    if "rescued" not in [r[1] for r in c.execute("PRAGMA table_info(listings)")]: c.execute("ALTER TABLE listings ADD COLUMN rescued INTEGER DEFAULT 0")
    c.execute("CREATE TABLE IF NOT EXISTS rejected (ad_id TEXT PRIMARY KEY, url TEXT, reason TEXT, lokasi_mentah TEXT, ts TEXT)")
    return c


def save(con, r, now):
    sets = ",".join("harga=CASE WHEN rescued=1 THEN harga ELSE excluded.harga END" if c == "harga" else f"{c}=excluded.{c}" for c in LC[1:])
    con.execute(f"INSERT INTO listings ({','.join(LC)},first_seen,last_seen,active) VALUES ({','.join('?' * len(LC))},?,?,1) "
                f"ON CONFLICT(ad_id) DO UPDATE SET {sets},last_seen=excluded.last_seen,active=1", [r[c] for c in LC] + [now, now])
    con.execute("DELETE FROM rejected WHERE ad_id=?", (r["ad_id"],))


def flagged(cfg=None):
    """Satu-satunya tempat aturan kebersihan. Urutan: duplikat -> outlier -> promo kredit janggal (saling lepas)."""
    cfg = {**DEFAULT, **(cfg or {})}
    con = db(); df = pd.read_sql("SELECT * FROM listings ORDER BY first_seen, ad_id", con); con.close()
    df["judul"] = df.url.map(lambda u: re.sub(r"-iid-\d+$", "", u.rstrip("/").rsplit("/", 1)[-1]))
    key = df.model.astype(str) + "|" + df.tahun.astype(str) + "|" + df.kilometer.astype(str) + "|" + df.harga.astype(str) + "|" + df.lokasi_mentah.fillna("").str.lower()
    if cfg["dedup_judul"]: key = key + "|" + df.judul                      # repost = judul, kecamatan, harga, tahun, km, model sama
    df["dup_flag"] = key.duplicated(keep="first").astype(int)
    g = df[df.dup_flag == 0].groupby(["model", "tahun"]).harga
    df["med"], df["n"] = g.transform("median"), g.transform("size")
    big = (df.n >= 12) & (df.dup_flag == 0)
    df["outlier"] = (big & ((df.harga < .6 * df.med) | (df.harga > 1.4 * df.med))).astype(int)      # menyimpang > 40% dari median
    promo = df.judul.str.replace("-", " ").str.contains(PROMO)
    df["suspect"] = (big & (df.outlier == 0) & promo & (df.harga < .75 * df.med) & (df.rescued == 0)).astype(int)
    df["bersih"] = ((df.dup_flag == 0) & (df.outlier == 0) & (df.suspect == 0)).astype(int)
    return df


def refresh(S, cfg):
    df = flagged(cfg); ok = df[df.bersih == 1]
    S["ok"], S["quota"] = len(ok), ok.provinsi.value_counts().to_dict()
    S["dupn"], S["outn"], S["susn"] = int(df.dup_flag.sum()), int(df.outlier.sum()), int(df.suspect.sum())


def export(cfg=None):
    from openpyxl.styles import Font, PatternFill
    df = flagged(cfg); ts = time.strftime("%Y%m%d_%H%M"); run = D / "export" / ts; run.mkdir(parents=True, exist_ok=True)
    names = dict(brand="Brand", model="Model", transmisi="Transmisi", tahun="Tahun", kilometer="Kilometer", cc="Kapasitas Mesin", harga="Harga", lokasi="Lokasi", url="URL")
    out = df[df.bersih == 1].rename(columns=names)[list(names.values())]
    out = out.sort_values(["Brand", "Model", "Tahun", "Harga"]).reset_index(drop=True)
    out.to_csv(run / "motor_bekas.csv", index=False, encoding="utf-8-sig")
    out.to_json(run / "motor_bekas.json", orient="records", force_ascii=False, indent=2)
    with pd.ExcelWriter(run / "motor_bekas.xlsx", engine="openpyxl") as w:
        out.to_excel(w, index=False, sheet_name="Data"); ws = w.sheets["Data"]
        ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions
        for col in ws.columns:
            h = col[0]; h.font = Font(bold=True, color="FFFFFF"); h.fill = PatternFill("solid", fgColor="1F2937")
            ws.column_dimensions[h.column_letter].width = min(max(len(str(c.value or "")) for c in col[:300]) + 4, 60)
            if h.value in ("Harga", "Kilometer"):
                for c in col[1:]: c.number_format = "#,##0"
            if h.value == "URL" and len(out) <= 60000:                  # batas hyperlink Excel ±65.530 per sheet
                for c in col[1:]: c.hyperlink = c.value; c.style = "Hyperlink"
    for name, m in (("duplikat", df.dup_flag == 1), ("outlier", df.outlier == 1), ("promo_kredit", df.suspect == 1)):
        df[m].drop(columns=["med", "n", "dupkey"], errors="ignore").to_csv(run / f"review_{name}.csv", index=False, encoding="utf-8-sig")
    con = db(); pd.read_sql("SELECT * FROM rejected", con).to_csv(run / "review_ditolak.csv", index=False, encoding="utf-8-sig"); con.close()
    latest = D / "export" / "terbaru"; (D / "backup").mkdir(exist_ok=True)
    if latest.exists(): shutil.move(str(latest), str(D / "backup" / f"terbaru_{ts}"))   # versi lama tidak pernah ditimpa
    shutil.copytree(run, latest)
    return len(out), int(df.dup_flag.sum()), int(df.outlier.sum()), int(df.suspect.sum())


# ---------- Crawl ----------
def url_of(slug, q, var, page):
    return OLX["url"].format(loc=slug, q=q.replace(" ", "-")) + var["qs"] + (f"&page={page}" if page > 1 else "")


def page_log(S, f, v, kartu, baru, tag):
    L = f.last; S["pages_n"] += 1; good = v in ("OK", "KOSONG", "HABIS", "ULANG"); S["pg_ok" if good else "pg_bad"] += 1
    S["pages"].append({"#": S["pages_n"], "Hasil": f"{ICON[v]} {v}", "HTTP": str(L.get("status")), "Detik": round(L.get("sec", 0), 1),
                       "KB": L.get("kb", 0), "Kartu": kartu, "Baru": baru, "Query": tag}); del S["pages"][:-60]
    log(S, f"#{S['pages_n']} {v:<7} HTTP {L.get('status')} | {L.get('sec', 0):.1f}s | {L.get('kb', 0)}KB | {kartu} kartu | {baru} baru | {tag}", "INFO" if good else "ERROR")


def preflight(cfg, f, S):
    """Satu halaman uji harus terbaca normal sebelum crawl dimulai; kalau tidak, berhenti dengan diagnosis."""
    prov, slug = next(iter(OLX["locations"].items())); var = OLX["variants"][min(6, len(OLX["variants"]) - 1)]
    u1 = url_of(slug, "beat", var, 1); S["msg"] = "Menguji halaman awal..."
    html = f.get(u1); raws, title = parse(html) if html else ([], "")
    good = sum(1 for r in raws if r["price"] and r["year"])
    log(S, f"PREFLIGHT HTTP {f.last.get('status')} | {len(raws)} kartu ({good} lengkap harga+tahun) | judul='{title[:70]}'")
    if not html or len(raws) < 3 or good < len(raws) * 0.7:
        if html: snap(S, u1, html, "preflight")
        raise Blocked(f"preflight gagal: HTTP {f.last.get('status')}, {len(raws)} kartu ({good} lengkap), judul='{title[:50]}'")
    h2 = f.get(url_of(slug, "beat", var, 2)); r2 = parse(h2)[0] if h2 else []
    new2 = len({r["id"] for r in r2} - {r["id"] for r in raws}); weak = not new2 and len(raws) >= 15
    log(S, f"PREFLIGHT halaman 2: {len(r2)} kartu, {new2} baru" + (" -> paginasi mungkin tidak berfungsi (1 halaman per kombinasi)" if weak else ""), "WARN" if weak else "INFO")


def crawl(cfg, f, S, con, now, mem, balanced):
    """balanced=True: kuota sama per provinsi. balanced=False: tanpa kuota (mengisi sisa target). Target dihitung dari data BERSIH."""
    quota, bad = -(-cfg["target"] // len(OLX["locations"])), 0
    combos = [(q.strip(), v) for q in cfg["queries"] for v in OLX["variants"]]; random.Random(7).shuffle(combos)  # sampel merata
    S["ct"], limit = len(combos) * len(OLX["locations"]), (100 if cfg["semua"] else cfg["max_pages"])
    for q, var in combos:
        qkey = QMAP.get(re.sub(r"[^a-z0-9]", "", q.lower()))
        for prov, slug in OLX["locations"].items():
            ck = (q, var["qs"], prov)
            if ck in mem["done"] or (balanced and S["quota"].get(prov, 0) >= quota): continue
            prev = None
            for page in range(1, limit + 1):
                url = url_of(slug, q, var, page); tag = f"{prov} · {q} · km~{var['km'] // 1000}rb · h{page}"; S["msg"] = tag
                html = f.get(url); raws, title = parse(html) if html else ([], ""); urls = {r["id"] for r in raws}
                new = [r for r in raws if r["id"] not in mem["seen"]]
                v = ("HABIS" if f.last.get("status") == 404 else "GAGAL") if html is None else \
                    "ULANG" if raws and urls == prev else "OK" if raws else "KOSONG" if OLX["title_marker"] in title.lower() else "ANOMALI"
                page_log(S, f, v, len(raws), len(new), tag)
                bad = bad + 1 if v in ("GAGAL", "ANOMALI") else 0
                if v == "ANOMALI": snap(S, url, html, "anomali")
                if bad >= cfg["bad_pages"]: raise Blocked(f"{bad} halaman bermasalah beruntun (terakhir {v})")
                if v != "OK": break
                prev = urls
                for raw in new:
                    mem["seen"].add(raw["id"]); raw["km"] = var["km"]
                    row, why = clean(raw, prov, cfg, qkey)
                    if why:
                        con.execute("INSERT OR REPLACE INTO rejected VALUES (?,?,?,?,?)", (raw["id"], raw["url"], "; ".join(why), row["lokasi_mentah"], now))
                        S["rejected"] += 1
                        for w in why: S["why"][w] = S["why"].get(w, 0) + 1
                    else: save(con, row, now)
                con.commit(); refresh(S, cfg)
                if not cfg["semua"] and S["ok"] >= cfg["target"]: S["msg"] = "Target tercapai"; raise Stop
            else:      # loop halaman tidak berhenti sendiri = mentok batas kedalaman
                S["capped"] += 1; log(S, f"Kedalaman maksimum ({limit} halaman) tercapai: {tag}; sebagian iklan kombinasi ini mungkin tidak terambil", "WARN")
            mem["done"].add(ck); S["cd"] = len(mem["done"])


def cash_price(html):
    """Harga cash dari DESKRIPSI iklan (bukan seluruh halaman). Mengembalikan (harga|None, deskripsi_ditemukan)."""
    soup = BeautifulSoup(html, "lxml")
    el = soup.select_one('[data-aut-id="itemDescriptionContent"]') or soup.select_one('meta[property="og:description"]')
    if el is None: return None, False
    m = CASH.search(el.get("content", "") if el.name == "meta" else el.get_text(" ", strip=True))
    return (num(m[1]) if m else None), True


def rescue(cfg, f, S, con):
    """Iklan promo kredit berharga janggal: buka halaman detail, cari harga cash di deskripsi, terima bila masuk akal (±40% median)."""
    sus = flagged(cfg).query("suspect == 1").head(cfg["max_detail"]); log(S, f"Mencari harga cash di deskripsi: {len(sus)} iklan")
    for _, r in sus.iterrows():
        S["msg"] = f"Deskripsi: {r.judul[:50]}"; html = f.get(r.url)
        if html is None: continue
        cash, found = cash_price(html)
        if not found: log(S, "deskripsi tidak ditemukan (selector mungkin berubah)", "WARN"); snap(S, r.url, html, "deskripsi")
        ok = bool(cash) and r.med * .6 <= cash <= r.med * 1.4
        con.execute("UPDATE listings SET rescued=?, harga=? WHERE ad_id=?", (1 if ok else -1, int(cash) if ok else int(r.harga), str(r.ad_id)))
        con.commit(); S["resc"] += int(ok); refresh(S, cfg)
        log(S, f"{'✓' if ok else '✗'} cash={cash} (kartu {int(r.harga):,}) {r.judul[:45]}")


def run(cfg, S):
    cfg = {**DEFAULT, **cfg}; cfg["delay"] = SPEED[cfg["speed"]]
    S.update(new_state(), running=True, msg="Menyiapkan..."); S["log"] = []; S["t0"] = time.time()
    now = dt.datetime.now().isoformat(timespec="seconds"); con, done, f, mem = db(), False, None, dict(seen=set(), done=set())
    try:
        al = cfg["semua"]; f = make_fetcher(cfg, S); crawl(cfg, f, S, con, now, mem, not al)
        if not al and S["ok"] < cfg["target"]: log(S, "Kuota seimbang selesai; lanjut tanpa kuota provinsi sampai target atau data habis"); crawl(cfg, f, S, con, now, mem, False)
        if (al or S["ok"] < cfg["target"]) and cfg["rescue"]: rescue(cfg, f, S, con)
        done = True; S["msg"] = (f"Selesai: semua data tersedia sudah diambil ({S['ok']:,} bersih)" if al else "Selesai" if S["ok"] >= cfg["target"]
                                 else f"Selesai: semua data tersedia sudah diambil ({S['ok']:,} bersih dari target {cfg['target']:,})")
    except Stop:
        if not S["msg"].startswith(("Target", "Batas")): S["msg"] = "Dihentikan (progres tersimpan)"
        if S["msg"].startswith("Batas"): S["msg"] += " - jalankan lagi dalam 24 jam untuk melanjutkan (halaman yang sudah diambil dipakai dari cache)"
    except Blocked as e:
        S["msg"] = "Dihentikan otomatis untuk melindungi IP"; log(S, str(e), "ERROR")
        for ln in diagnose(OLX["base"])[0]: log(S, ln, "WARN")
    except Exception:
        S["msg"] = "Error"; log(S, traceback.format_exc(), "ERROR")
    finally:
        if f is not None and hasattr(f, "close"): f.close()
        if done: con.execute("UPDATE listings SET active=0 WHERE last_seen<?", (now,))
        con.commit(); con.close()
        try: refresh(S, cfg)
        except Exception: pass
        log(S, f"RINGKASAN bersih={S['ok']} duplikat={S['dupn']} outlier={S['outn']} promo_dicurigai={S['susn']} dirawat_cash={S['resc']} ditolak={S['rejected']} request={S['req']} error={S['errs']} alasan_tolak={dict(sorted(S['why'].items(), key=lambda x: -x[1])[:5])}")
        try: n, d, o, s_ = export(cfg); log(S, f"Ekspor: {n} baris bersih; dipisah ke review: {d} duplikat, {o} outlier, {s_} promo kredit -> data/export/terbaru")
        except Exception as e: log(S, f"Ekspor gagal: {e}", "ERROR")
        S["running"] = False


def check(cfg):
    """Cek bertahap tanpa crawl. TCP/TLS gagal -> berhenti. HTTP tak dijawab -> uji browser. OK -> uji requests, lalu browser bila gagal."""
    from concurrent.futures import ThreadPoolExecutor
    def job():
        c = {**DEFAULT, **cfg, "delay": (0.5, 1)}; out, level = diagnose(OLX["base"])
        if level not in ("ok", "http"): return out + ["⏹ Uji halaman dilewati: masalah ada di jaringan/koneksi, bukan di parsing."]
        for name in (["requests"] if level == "ok" else []) + ["browser"]:
            S, f = new_state(), None
            try:
                f = Fetcher({**c, "timeout": 15, "retries": 1, "max_fails": 1}, S) if name == "requests" else BrowserFetcher(c, S)
                preflight(c, f, S); out += S["log"] + [f"✅ mode {name}: halaman terbaca normal."]; break
            except ImportError: out.append("ℹ️ mode browser butuh Playwright: pip install playwright, lalu: playwright install chromium")
            except Exception as e: out += S["log"][-3:] + [f"❌ mode {name}: {str(e).splitlines()[0][:200]}"]
            finally:
                if f is not None and hasattr(f, "close"): f.close()
        return out
    with ThreadPoolExecutor(1) as ex: return ex.submit(job).result()   # thread terpisah: aman untuk Playwright di Streamlit
