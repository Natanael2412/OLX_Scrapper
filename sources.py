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
# cc = kapasitas nominal yang lazim ditulis (mis. Vixion 150, MT-15 155). Model yang tidak ada di sini masuk daftar "Ditolak".
_M = {
    "Honda": ("Beat:110:M, Beat Street:110:M, Scoopy:110:M, Genio:110:M, Spacy:110:M, Vario 110:110:M, Vario 125:125:M, Vario 150:150:M, Vario 160:160:M, Vario:125:M, "
              "PCX 160:160:M, PCX:150:M, ADV 150:150:M, ADV 160:160:M, X-ADV:745:M, Forza:250:M, Stylo 160:160:M, "
              "CB150R:150:K, CB150 Verza:150:K, Verza:150:K, CB150X:150:K, CBR150R:150:K, CBR250R:250:K, CBR250RR:250:K, CRF150L:150:K, CRF250L:250:K, CRF250 Rally:250:K, "
              "Supra X 125:125:K, Supra X 100:100:K, Supra X:125:K, Supra Fit:100:K, Supra GTR 150:150:K, Revo:110:K, Blade 125:125:K, Blade:110:K, Sonic:150:K, Tiger:200:K, "
              "Mega Pro:150:K, Karisma:125:K, GL Pro:160:K, Astrea:100:K, CS1:125:K, Monkey:125:K, Super Cub:125:K, CT125:125:K, Grom:125:K, "
              "CB650R:649:K, CBR650R:649:K, CB500X:471:K, CBR500R:471:K, NC750X:745:K, Africa Twin:1084:K, CB1000R:998:K, CBR1000RR:999:K, Rebel 500:471:K, Gold Wing:1833:K"),
    "Yamaha": ("Mio Sporty:113:M, Mio Smile:113:M, Mio J:113:M, Mio Soul:113:M, Mio M3:125:M, Mio Z:125:M, Mio Gear:125:M, Mio S:125:M, Mio:113:M, "
               "Soul GT 125:125:M, Soul GT:115:M, Soul:110:M, Fino 125:125:M, Fino:115:M, Freego:125:M, Gear 125:125:M, Lexi:125:M, Fazzio:125:M, Filano:125:M, Nouvo:115:M, "
               "NMAX:155:M, XMAX:250:M, TMAX:530:M, Aerox 125:125:M, Aerox:155:M, Xeon:125:M, "
               "Vixion R:155:K, Vixion:150:K, MT-15:155:K, MT-25:250:K, MT-03:321:K, MT-07:689:K, R15:155:K, R25:250:K, R3:321:K, WR155:155:K, XSR155:155:K, Byson:150:K, Xabre:150:K, "
               "Jupiter Z1:115:K, Jupiter Z:110:K, Jupiter MX:135:K, MX King:150:K, Vega:115:K, Scorpio:225:K, RX King:135:K, RX-Z:135:K, F1ZR:110:K, Crypton:105:K"),
    "Suzuki": ("Address:113:M, Nex:115:M, Burgman Street:125:M, Skydrive:125:M, Spin:125:M, Hayate:125:M, "
               "Satria F150:150:K, Satria FU:150:K, Satria 120R:120:K, Raider:150:K, Thunder:125:K, Shogun 125:125:K, Shogun:110:K, Smash:110:K, Arashi:125:K, Inazuma:250:K, "
               "GSX-R150:150:K, GSX-S150:150:K, GSX250R:248:K, V-Strom 250:248:K, GSX-S750:749:K, GSX-R600:599:K, GSX-R750:750:K, GSX-R1000:999:K, Hayabusa:1340:K"),
    "Kawasaki": ("Ninja 250:250:K, Ninja 150:150:K, Ninja 300:296:K, Ninja 400:399:K, Ninja 650:649:K, Ninja 1000:1043:K, Ninja H2:998:K, ZX-25R:250:K, ZX-6R:636:K, ZX-10R:998:K, "
                 "Z250:250:K, Z300:296:K, Z400:399:K, Z650:649:K, Z800:806:K, Z900:948:K, Z1000:1043:K, ER-6N:649:K, Versys 250:249:K, Versys 650:649:K, Versys 1000:1043:K, Vulcan S:649:K, "
                 "KLX 150:150:K, KLX 230:233:K, D-Tracker:150:K, W175:177:K, W250:249:K, W800:773:K"),
    "Vespa": ("Vespa LX:125:M, Vespa S:125:M, Vespa Primavera 125:125:M, Vespa Primavera 150:155:M, Vespa Primavera:155:M, Vespa Sprint 125:125:M, Vespa Sprint 150:155:M, Vespa Sprint:155:M, "
              "Vespa GTS 150:155:M, Vespa GTS 300:278:M, Vespa GTV 300:278:M, Vespa 946:155:M, Vespa PX:150:K"),
    "Piaggio": "Medley:155:M",
    "Benelli": "TNT 135:135:K, TNT 25:249:K, TNT 249S:249:K, TNT 300:302:K, TNT 600i:600:K, Leoncino 250:249:K, Leoncino 500:500:K, TRK 251:249:K, TRK 502:500:K, Imperiale 400:374:K, Zafferano 250:249:M",
    "Royal Enfield": "Classic 350:349:K, Meteor 350:349:K, Hunter 350:349:K, Himalayan:411:K, Scram 411:411:K, Interceptor 650:648:K, Continental GT 650:648:K, Classic 500:499:K, Bullet 500:499:K, Thunderbird 500:499:K",
    "TVS": "Apache RTR 160:160:K, Apache RTR 200:200:K, Apache RR 310:312:K, Ntorq 125:125:M, Jupiter 125:125:M",
    "Bajaj": "Pulsar 200 NS:200:K, Pulsar 180:178:K, Pulsar 150:149:K, Avenger 220:220:K, Dominar 400:373:K",
    "KTM": "Duke 125:125:K, Duke 200:200:K, Duke 250:248:K, Duke 390:373:K, Duke 790:799:K, Duke 890:889:K, RC 200:200:K, RC 250:248:K, RC 390:373:K, 250 Adventure:248:K, 390 Adventure:373:K",
    "BMW": "G 310 R:313:K, G 310 GS:313:K, S 1000 RR:999:K, S 1000 R:999:K, S 1000 XR:999:K, R 1250 GS:1254:K, R 1200 GS:1170:K, F 850 GS:853:K, F 750 GS:853:K, F 800 GS:798:K, R nineT:1170:K, R 1250 RT:1254:K, C 400 X:350:M, C 400 GT:350:M",
    "Harley-Davidson": "Iron 883:883:K, Forty-Eight:1202:K, Sportster 1200:1202:K, Street 750:749:K, Nightster:975:K, Sportster S:1252:K, Pan America:1252:K",
    "Ducati": "Monster 821:821:K, Monster 797:803:K, Monster 696:696:K, Scrambler:803:K, Panigale V4:1103:K, Panigale V2:955:K, Multistrada 950:937:K, Hypermotard 950:937:K",
    "Triumph": "Tiger 800:799:K, Tiger 900:888:K, Tiger 1200:1215:K, Trident 660:660:K, Speed 400:398:K, Scrambler 400 X:398:K, Daytona 675:675:K, Rocket 3:2458:K",
    "CFMoto": "250NK:249:K, 150NK:149:K, 300NK:292:K, 650NK:649:K, 650MT:649:K",
    "Husqvarna": "Svartpilen 250:248:K, Vitpilen 250:248:K",
}
MODELS = {n.strip(): (b, int(cc), "Matic" if t.strip() == "M" else "Manual")
          for b, s in _M.items() for n, cc, t in (i.rsplit(":", 2) for i in s.split(",") if i.strip())}
# Koreksi kapasitas menurut tahun untuk model yang berganti mesin: nama -> (operator, tahun, cc)
YEAR_RULES = {"R15": ("<=", 2016, 150), "PCX": (">=", 2021, 160), "Vario": ("<=", 2011, 110)}
