import json, threading, time
from pathlib import Path
import pandas as pd, streamlit as st
import engine
from sources import OLX

st.set_page_config(page_title="OLX Motor Scraper", page_icon="🏍️", layout="centered")
st.markdown("""<style>
#MainMenu, footer, header {visibility: hidden;}
.block-container {max-width: 860px; padding-top: 2.2rem;}
h1 {font-weight: 700; letter-spacing: -.02em; margin-bottom: 0;}
.stButton>button, .stDownloadButton>button {border-radius: 10px; font-weight: 600;}
[data-testid="stMetric"] {background: rgba(128,128,128,.08); border-radius: 12px; padding: .7rem 1rem;}
[data-testid="stExpander"] {border-radius: 12px;}
</style>""", unsafe_allow_html=True)


@st.cache_resource
def shared(): return engine.new_state()


S, CF, LATEST = shared(), Path("config.json"), engine.D / "export" / "terbaru"
cfg = {**engine.DEFAULT, **(json.loads(CF.read_text()) if CF.exists() else {})}
ALLQ = engine.DEFAULT["queries"]

st.title("OLX Motor Scraper")
st.caption("Motor bekas · Jakarta & Jawa Barat · Brand, Model, Transmisi, Tahun, Kilometer, Kapasitas Mesin, Harga, Lokasi, URL")
t1, t2, t3 = st.tabs(["Jalankan", "Data", "Review"])

with t1:
    with st.expander("Pengaturan"):
        cfg["semua"] = st.checkbox("Ambil semua data yang tersedia (tanpa target)", cfg["semua"],
                                   help="Jalan sampai semua kombinasi model × rentang km × provinsi selesai. Perkiraan kasar: 3.000–6.000 request, 5–10 jam. Bisa dihentikan dan dilanjutkan (cache 24 jam).")
        cfg["target"] = st.number_input("Target data bersih", 500, 50000, cfg["target"], step=500, disabled=cfg["semua"])
        cfg["max_requests"] = st.number_input("Batas request per run (pengaman)", 500, 50000, cfg["max_requests"], step=500,
                                              help="Run berhenti sendiri di batas ini. Jalankan lagi dalam 24 jam untuk melanjutkan; halaman yang sudah diambil dipakai dari cache.")
        cfg["speed"] = st.radio("Kecepatan", list(engine.SPEED), list(engine.SPEED).index(cfg["speed"]), horizontal=True,
                                help="Lebih lambat = lebih aman untuk IP. Jeda otomatis melambat bila ada error.")
        MODES = ["auto", "requests", "browser"]
        cfg["mode"] = st.radio("Mode ambil halaman", MODES, MODES.index(cfg["mode"]), horizontal=True,
                               help="auto: coba requests dulu, pindah ke browser (Playwright) bila gagal.")
        cfg["headed"] = st.checkbox("Tampilkan jendela browser", cfg["headed"], help="Untuk mode browser. Jendela terlihat bisa lebih stabil.")
        cfg["dedup_judul"] = st.checkbox("Duplikat harus berjudul sama", cfg["dedup_judul"],
                                         help="Aktif: repost = judul, kecamatan, harga, tahun, km, dan model sama. Nonaktif: lebih ketat (judul diabaikan).")
        cfg["rescue"] = st.checkbox("Cari harga cash di deskripsi", cfg["rescue"],
                                    help="Untuk iklan promo kredit berharga janggal. Hanya jalan bila target belum tercapai; membuka beberapa halaman detail.")
        cfg["queries"] = st.multiselect("Model yang dicari", ALLQ, [q for q in cfg["queries"] if q in ALLQ])
    b = st.columns([1, 1, 1, 2])
    if b[0].button("▶ Mulai", type="primary", disabled=S["running"] or not cfg["queries"], use_container_width=True):
        CF.write_text(json.dumps(cfg, indent=2)); S["running"] = True
        threading.Thread(target=engine.run, args=(cfg, S), daemon=True).start(); st.rerun()
    if b[1].button("⏹ Stop", disabled=not S["running"], use_container_width=True): S["stop"] = True
    if b[2].button("🩺 Cek", disabled=S["running"], use_container_width=True, help="Uji koneksi & halaman OLX (±5 request)"):
        with st.spinner("Memeriksa koneksi & halaman (bisa 1–2 menit)..."): st.code("\n".join(engine.check(cfg)), language=None)

    @st.fragment(run_every=2)
    def top():
        q = -(-cfg["target"] // len(OLX["locations"]))
        if cfg["semua"]:
            eta = f" · sisa ±{(time.time() - S['t0']) / S['cd'] * (S['ct'] - S['cd']) / 3600:.1f} jam (kasar)" if S["cd"] >= 20 and S["running"] else ""
            st.progress(min(S["cd"] / max(S["ct"], 1), 1.0), text=f"{S['ok']:,} data bersih · {S['cd']:,}/{S['ct']:,} pencarian (model × provinsi){eta}")
        else: st.progress(min(S["ok"] / cfg["target"], 1.0), text=f"{S['ok']:,} / {cfg['target']:,} data bersih")
        for c, p in zip(st.columns(len(OLX["locations"])), OLX["locations"]):
            if cfg["semua"]: c.caption(f"{p}: {S['quota'].get(p, 0):,} bersih")
            else: c.progress(min(S["quota"].get(p, 0) / q, 1.0), text=f"{p} · {S['quota'].get(p, 0):,}/{q:,}")
        m = st.columns(4)
        m[0].metric("Bersih", f"{S['ok']:,}"); m[1].metric("Duplikat", S["dupn"]); m[2].metric("Outlier", S["outn"]); m[3].metric("Ditolak", S["rejected"])
        st.caption(f"Halaman: {S['pg_ok']} OK · {S['pg_bad']} bermasalah · {S['req']} request · {S['susn']} promo kredit dicurigai" + (f" · {S['capped']} kombinasi mentok kedalaman" if S["capped"] else ""))
        if S["req"]: st.caption(engine.speed(S))
        st.caption(("🟢 " if S["running"] else "⚪ ") + S["msg"])
        if S["cur"]: st.caption(f"⏳ menunggu respons {time.time() - S['cur_t']:.0f}s")
        if S["errs"]: st.error("Error: " + ", ".join(f"{k}×{v}" for k, v in S["errs"].items()))
        if S["pages"]: st.dataframe(pd.DataFrame(S["pages"][-8:][::-1]), hide_index=True)
    top()
    lvl = st.radio("Log", ["Semua", "Peringatan+", "Error"], horizontal=True, label_visibility="collapsed")

    @st.fragment(run_every=2)
    def logs():
        keep = {"Semua": ("",), "Peringatan+": ("[WARN]", "[ERROR]"), "Error": ("[ERROR]",)}[lvl]
        lg = [x for x in S["log"] if any(k in x for k in keep)]
        st.code("\n".join(lg[-60:]) or "(log kosong)", language=None)
    logs()
    lf = engine.D / "scraper.log"
    if lf.exists(): st.download_button("⬇ scraper.log", lf.read_bytes(), "scraper.log", key="lg")

with t2:
    if st.button("↻ Terapkan aturan terbaru & ekspor ulang (tanpa scraping)", disabled=S["running"]):
        with st.spinner("Memproses..."): n, d, o, s_ = engine.export(cfg)
        st.success(f"{n:,} bersih · {d} duplikat · {o} outlier · {s_} promo kredit dicurigai")
    if (LATEST / "motor_bekas.csv").exists():
        df = pd.read_csv(LATEST / "motor_bekas.csv"); st.caption(f"{len(df):,} baris bersih · {LATEST}")
        for col, (ext, mime) in zip(st.columns(3), [("csv", "text/csv"), ("json", "application/json"),
                                                    ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")]):
            col.download_button(f"⬇ {ext.upper()}", (LATEST / f"motor_bekas.{ext}").read_bytes(), f"motor_bekas.{ext}", mime, use_container_width=True, key=ext)
        st.dataframe(df, hide_index=True, column_config={"URL": st.column_config.LinkColumn("URL")} if "URL" in df.columns else None)
    else: st.info("Belum ada data. Jalankan scraping dulu.")

with t3:
    st.caption("Data yang dikeluarkan dari ekspor beserta alasannya. Tidak ada yang dihapus permanen.")
    for name, label in [("ditolak", "Ditolak"), ("duplikat", "Duplikat"), ("outlier", "Outlier harga"), ("promo_kredit", "Promo kredit (harga dicurigai)")]:
        p = LATEST / f"review_{name}.csv"
        if p.exists():
            r = pd.read_csv(p, dtype=str)
            with st.expander(f"{label} · {len(r):,}"):
                if name == "ditolak" and len(r): st.bar_chart(r["reason"].str.split("; ").explode().value_counts())
                st.dataframe(r, hide_index=True)
