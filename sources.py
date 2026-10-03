# Satu sumber data: wilayah, model, dan konfigurasi OLX.
# Wilayah target (nama, provinsi). Dipakai untuk mencocokkan teks lokasi iklan (batas kata, nama terpanjang dulu).
REGIONS = [(n, "DKI Jakarta") for n in ["Jakarta Selatan", "Jakarta Timur", "Jakarta Barat", "Jakarta Utara", "Jakarta Pusat", "Kepulauan Seribu", "Jakarta"]] + \
          [(n, "Jawa Barat") for n in ["Bandung Barat", "Bandung", "Cimahi", "Bogor", "Depok", "Bekasi", "Karawang", "Purwakarta", "Subang", "Cianjur",
           "Sukabumi", "Cirebon", "Indramayu", "Majalengka", "Kuningan", "Sumedang", "Garut", "Tasikmalaya", "Ciamis", "Pangandaran", "Banjar"]]

OLX = {
    "base": "https://www.olx.co.id",
    "url": "https://www.olx.co.id/{loc}/motor-bekas_c200/q-{q}",
    "locations": {"DKI Jakarta": "jakarta-dki_g2000007", "Jawa Barat": "jawa-barat_g2000009"},
    "title_marker": "olx",   # judul halaman normal harus memuat kata ini (membedakan 'kosong' vs 'halaman blokir')
    # km dari filter jarak tempuh OLX: titik tengah tiap rentang 5.000 km
    "variants": [{"qs": "?filter=mileage_eq_0", "km": 0}] + [{"qs": f"?filter=mileage_eq_{n}", "km": (n - 5) * 1000 + 2500} for n in range(5, 101, 5)],
}

# Master model "Nama:cc:T" (T: M=Matic, K=Manual). Mengisi kapasitas mesin & transmisi bila tidak tertulis di iklan.
# Mohon diperiksa/ditambah sesuai kebutuhan; model yang tidak ada di sini masuk daftar "Ditolak".
_M = {
    "Honda": "Beat:110:M, Beat Street:110:M, Scoopy:110:M, Genio:110:M, Vario 110:110:M, Vario 125:125:M, Vario 150:150:M, Vario 160:160:M, Vario:125:M, PCX 160:160:M, PCX:150:M, ADV 150:150:M, ADV 160:160:M, Forza:250:M, Stylo 160:160:M, CB150R:150:K, CB150 Verza:150:K, Verza:150:K, CBR150R:150:K, CBR250RR:250:K, CRF150L:150:K, Supra X 125:125:K, Supra X:125:K, Supra GTR 150:150:K, Revo:110:K, Blade:110:K, Sonic:150:K",
    "Yamaha": "Mio Sporty:113:M, Mio Smile:113:M, Mio J:113:M, Mio Soul:113:M, Mio M3:125:M, Mio Z:125:M, Mio Gear:125:M, Mio S:125:M, Mio:113:M, Soul GT 125:125:M, Soul GT:115:M, Fino 125:125:M, Fino:115:M, Freego:125:M, Gear 125:125:M, Lexi:125:M, NMAX:155:M, XMAX:250:M, Aerox 125:125:M, Aerox:155:M, Xeon:125:M, Vixion R:155:K, Vixion:150:K, MT-15:155:K, MT-25:250:K, R15:155:K, R25:250:K, WR155:155:K, Byson:150:K, Jupiter Z1:115:K, Jupiter MX:135:K, MX King:150:K, Vega:115:K",
    "Suzuki": "Address:113:M, Nex:115:M, Burgman Street:125:M, Satria F150:150:K, Raider:150:K, Smash:110:K, GSX-R150:150:K, GSX-S150:150:K",
    "Kawasaki": "Ninja 250:250:K, Ninja 150:150:K, ZX-25R:250:K, Z250:250:K, KLX 150:150:K, W175:177:K",
}
MODELS = {n.strip(): (b, int(cc), "Matic" if t == "M" else "Manual")
          for b, s in _M.items() for n, cc, t in (i.rsplit(":", 2) for i in s.split(","))}
