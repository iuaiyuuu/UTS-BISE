"""Menyusun laporan UTS (.docx) dari output/results.json dan figures/."""
import json
import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent
R = json.load(open(ROOT / "output/results.json", encoding="utf-8"))
FIG = ROOT / "figures"
NAVY = RGBColor(0x1F, 0x3A, 0x5F)
MEMBERS = [("Muhammad Abiyyu Rahman", "25.51.1738"), ("Muhammad Gufron Hawaly", "25.51.1735"),
           ("I Kadek Wibisana Wraspati Yuda", "25.51.1740"), ("Elsa Monica Putri", "25.51.1809")]


def num(x, d=0):
    s = f"{x:,.{d}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".").replace("-", "−")


def pct(x, d=1):
    return num(x * 100, d) + "%"


def usd(x, d=0):
    return ("−" if x < 0 else "") + "$" + num(abs(x), d)


def pv(p):
    return "< 0,001" if p < 0.001 else num(p, 3)


def by(key, name, field):
    return next(r for r in R[key] if r[field] == name)


doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21), Cm(29.7)
sec.left_margin = sec.right_margin = Cm(2.2)
sec.top_margin, sec.bottom_margin = Cm(2.2), Cm(2)
WIDTH = 16.6
n = doc.styles["Normal"]
n.font.name, n.font.size = "Calibri", Pt(11)
n.paragraph_format.space_after, n.paragraph_format.line_spacing = Pt(6), 1.1
for lvl, size, before in [(1, 15, 16), (2, 12.5, 10)]:
    h = doc.styles[f"Heading {lvl}"]
    h.font.name, h.font.size, h.font.color.rgb, h.font.bold = "Calibri", Pt(size), NAVY, True
    h.paragraph_format.space_before, h.paragraph_format.space_after = Pt(before), Pt(4)
    h.paragraph_format.keep_with_next = True
    rf = h.element.rPr.rFonts
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        rf.attrib.pop(qn(attr), None)
    rf.set(qn("w:ascii"), "Calibri"); rf.set(qn("w:hAnsi"), "Calibri")

INLINE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`)")


def runs(p, text, size=None):
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**"):
            r = p.add_run(part[2:-2]); r.bold = True
        elif part.startswith("`"):
            r = p.add_run(part[1:-1]); r.font.name = "Consolas"; r.font.size = Pt((size or 11) - 1)
            continue
        else:
            r = p.add_run(part)
        if size:
            r.font.size = Pt(size)
    return p


def para(text, **kw):
    return runs(doc.add_paragraph(), text, **kw)


def bullet(text):
    p = runs(doc.add_paragraph(style="List Bullet"), text)
    p.paragraph_format.space_after = Pt(3)
    return p


def shade(el, fill):
    pr = el.get_or_add_pPr() if hasattr(el, "get_or_add_pPr") else el.get_or_add_tcPr()
    s = OxmlElement("w:shd")
    for k, v in (("w:val", "clear"), ("w:color", "auto"), ("w:fill", fill)):
        s.set(qn(k), v)
    pr.append(s)


def callout(text, fill="FFF4E5", color="E69138"):
    p = runs(doc.add_paragraph(), text)
    shade(p._p, fill)
    b = OxmlElement("w:pBdr"); l = OxmlElement("w:left")
    for k, v in (("w:val", "single"), ("w:sz", "18"), ("w:space", "6"), ("w:color", color)):
        l.set(qn(k), v)
    b.append(l); p._p.get_or_add_pPr().append(b)
    return p


counts = {"Tabel": 0, "Gambar": 0}


def caption(kind, text):
    counts[kind] += 1
    p = doc.add_paragraph()
    p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(6), Pt(3)
    if kind == "Tabel":
        p.paragraph_format.keep_with_next = True
    r = p.add_run(f"{kind} {counts[kind]}. "); r.bold = True; r.font.size = Pt(9.5); r.font.color.rgb = NAVY
    r = p.add_run(text); r.font.size = Pt(9.5)
    return counts[kind]


def table(rows, widths, size=9, numeric_from=None, title=None):
    if title:
        caption("Tabel", title)
    t = doc.add_table(rows=len(rows), cols=len(rows[0]))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    k = WIDTH / sum(widths)
    for i, row in enumerate(rows):
        tr = t.rows[i]._tr.get_or_add_trPr()
        cs = OxmlElement("w:cantSplit"); tr.append(cs)
        if i == 0:
            th = OxmlElement("w:tblHeader"); tr.append(th)
        for j, val in enumerate(row):
            c = t.cell(i, j)
            c.width = Cm(widths[j] * k)
            p = c.paragraphs[0]
            p.paragraph_format.space_after = Pt(1); p.paragraph_format.space_before = Pt(1); p.paragraph_format.line_spacing = 1.0
            runs(p, str(val), size=size)
            if numeric_from is not None and j >= numeric_from:
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            if i == 0:
                shade(c._tc, "D9E2F3")
                for r in p.runs:
                    r.bold = True
    sp = doc.add_paragraph(); sp.paragraph_format.space_after = Pt(4)
    return t


def figure(name, width, text, alt):
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True; p.paragraph_format.space_after = Pt(0)
    pic = p.add_run().add_picture(str(FIG / name), width=Cm(width))
    pic._inline.docPr.set("descr", alt)
    caption("Gambar", text)


# ---------------------------------------------------------------- footer
fp = sec.footer.paragraphs[0]; fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = fp.add_run("UTS Business Information System Engineering  |  "); r.font.size = Pt(8.5)
for tag, txt in (("begin", None), (None, "PAGE"), ("end", None)):
    r = fp.add_run(); r.font.size = Pt(8.5)
    if tag:
        f = OxmlElement("w:fldChar"); f.set(qn("w:fldCharType"), tag); r._r.append(f)
    else:
        it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = txt; r._r.append(it)

# ---------------------------------------------------------------- judul
for text, size, bold in [("LAPORAN UJIAN TENGAH SEMESTER", 17, True), ("Business Information System Engineering (MT117)", 13, True),
                         ("S2 Informatika, Semester Ganjil 2026/2027", 11, False)]:
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_after = Pt(2)
    r = p.add_run(text); r.bold = bold; r.font.size = Pt(size); r.font.color.rgb = NAVY
p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("Analisis Kebocoran Profit pada Dataset 2: Superstore Sales"); r.font.size = Pt(12); r.italic = True
table([["No", "Nama", "NIM"]] + [[str(i + 1), a, b] for i, (a, b) in enumerate(MEMBERS)], [1, 11, 4], size=10)
para("Dosen pengampu: Robert Marco, S.T., M.T., Ph.D dan Dr. Hartatik, S.T., M.Cs", size=10)

# ---------------------------------------------------------------- ringkasan
sn = R["state_negative"]
gain, loss, tot = R["gain_total"], R["loss_total"], R["profit_total"]
tables_ = by("group_Sub-Category", "Tables", "Sub-Category")
central, west = by("group_Region", "Central", "Region"), by("group_Region", "West", "Region")
hrc = by("heat_region_category", "Central", "Region")
rw = by("return_region", "West", "Region")
ev = {e["Set"]: e for e in R["eval"]}
evs = ev["Seleksi per variabel"]
seg_chi = by("tests", "Is_Loss x Segment", "Hubungan")

doc.add_heading("Ringkasan Eksekutif", 1)
para(f"Setelah dibersihkan, data berisi {num(R['clean_shape'][0])} baris transaksi dari {num(R['n_orders'])} order (2019–2020) dengan profit bersih **{usd(tot)}**. "
     f"Masalah utamanya adalah kebocoran profit: transaksi rugi menggerus {usd(abs(loss))}, atau {pct(abs(loss) / gain)} dari keuntungan kotor {usd(gain)}. Kerugian ini terkonsentrasi dan dapat diprediksi.")
bullet(f"**Kerugian terkonsentrasi secara geografis.** {sn['n']} negara bagian yang bernilai negatif mencakup {pct(sn['line_share'])} baris, tetapi menyumbang {pct(sn['loss_share'])} nilai kerugian. Region Central rugi pada {pct(central['Loss_Rate'])} barisnya, dibanding West {pct(west['Loss_Rate'])}.")
bullet(f"**Produk memperkuat pola tersebut.** {pct(tables_['Loss_Rate'], 0)} baris Tables merugi, dan Furniture di Central merugi pada {num(hrc['Furniture'], 1)}% baris.")
bullet(f"**Segmen pelanggan tidak membedakan profit** (Cramér's V = {num(seg_chi['Efek'], 3)}, tidak signifikan). Keputusan harga sebaiknya berbasis wilayah dan produk, bukan segmen.")
bullet(f"**Retur West {pct(rw['Rate'])}**, tiga sampai enam kali region lain (order 2020).")
bullet(f"**Risiko rugi dapat diprediksi** sebelum pengiriman dengan ROC-AUC {num(evs['ROC_AUC'], 3)} pada data uji.")
callout(f"**Temuan kualitas data yang menentukan analisis.** Mulai 1 Januari 2020, nilai Sales bergeser sehingga Sales dan margin 2020 tidak sebanding dengan 2019, sementara Profit tetap stabil. Karena itu laporan ini memakai **Profit dan status rugi** sebagai metrik utama, dan klaim seperti “Sales naik” atau “margin anjlok” tidak dibuat. Buktinya ada di Bagian 2.2.")

# ---------------------------------------------------------------- 1
doc.add_heading("1. Dataset dan Tujuan Analisis", 1)
para(f"Kami memilih **Dataset 2, Superstore Sales** (kaggle.com/datasets/ayush12nagar/superstore-sales-dataset) karena memuat profit, segmen pelanggan, wilayah, produk, dan retur, sehingga paling langsung menghasilkan keputusan pemasaran. "
     f"Data mentah berukuran {num(R['raw_shape'][0])} baris × {R['raw_shape'][1]} kolom. Setiap baris adalah satu item dalam satu order, periode {R['date_range'][0]} sampai {R['date_range'][1]}, seluruhnya di Amerika Serikat. Satuan uang tidak dinyatakan di data dan kami asumsikan USD.")
para("**Pertanyaan bisnis:** di mana perusahaan kehilangan profit, apa yang berhubungan dengannya, dan keputusan apa yang perlu diambil? Untuk tahap pemodelan, target disiapkan berupa `Is_Loss` (1 jika Profit < 0).")

# ---------------------------------------------------------------- 2
doc.add_heading("2. Preprocessing Data", 1)
doc.add_heading("2.1 Data Cleaning", 2)
table([["Masalah", "Temuan", "Tindakan dan alasan"],
       ["Kolom kosong", f"`ind1` dan `ind2` kosong 100% ({num(R['missing_raw']['ind1'])} baris)", "Dihapus karena tidak berisi informasi."],
       ["Missing `Returns`", f"Kosong {num(R['missing_raw']['Returns'])} baris; isi hanya bernilai 1. Tidak ada satu pun retur tercatat pada 2019 (0 dari {num(R['returned_orders_by_year'][0]['size'])} order)", "2020: kosong diartikan tidak retur (0). 2019: tetap kosong karena tidak diketahui, bukan nol. Analisis retur hanya memakai 2020."],
       ["Duplikat", f"Duplikat persis {R['dup_exact']}. `Row ID` ganda {R['dup_rowid']} tetapi transaksinya berbeda. Order + produk sama: {R['dup_order_product']} pasang dengan jumlah berbeda", "Tidak ada baris dihapus karena semuanya transaksi berbeda. `Row ID` dibuang karena bukan pengenal yang andal."],
       ["Tipe dan konsistensi", f"Tanggal bertipe teks (dd-mm-yyyy); {R['orders_multi_date']} order punya dua tanggal; nama kolom pertama rusak", "Tanggal diparse, tanggal order diseragamkan ke yang paling awal, kolom diganti nama."],
       ["Kolom tidak berguna", f"`Country` konstan; `Customer Name` duplikat dari ID; `Product Name` tidak konsisten ({R['product_id_multi_name']} Product ID punya >1 nama)", "Dihapus. Identitas cukup memakai ID dan nama pribadi tidak diperlukan untuk analisis."]],
      [2.6, 7, 7], title="Hasil data cleaning")

doc.add_heading("2.2 Data Filtering dan Outlier Handling", 2)
sp = R["shift_pairs"]; ym = R["year_medians"]
para(f"**Pergeseran Sales 2020.** Median Sales per baris melompat dari {usd(ym[0]['Sales'], 2)} (2019) ke {usd(ym[1]['Sales'], 2)} (2020), sedangkan median Profit ({usd(ym[0]['Profit'], 2)} ke {usd(ym[1]['Profit'], 2)}) dan persentase baris rugi ({pct(ym[0]['Loss_Rate'])} ke {pct(ym[1]['Loss_Rate'])}) nyaris tidak berubah. Untuk mengujinya, kami membandingkan pasangan transaksi dengan produk, jumlah, dan profit yang sama persis:")
table([["Pasangan yang dibandingkan", "Jumlah pasangan", "Sales identik", "Selisih tepat bilangan bulat", "Median selisih"],
       ["Sesama 2019", num(sp["2019_2019"]["pairs"]), pct(sp["2019_2019"]["same_sales_pct"] / 100), pct(sp["2019_2019"]["integer_nonzero_pct"] / 100), usd(sp["2019_2019"]["median_abs_diff"], 2)],
       ["2019 dengan 2020", num(sp["2019_2020"]["pairs"]), pct(sp["2019_2020"]["same_sales_pct"] / 100), pct(sp["2019_2020"]["integer_nonzero_pct"] / 100), usd(sp["2019_2020"]["median_abs_diff"], 2)],
       ["Sesama 2020", num(sp["2020_2020"]["pairs"]), pct(sp["2020_2020"]["same_sales_pct"] / 100), pct(sp["2020_2020"]["integer_nonzero_pct"] / 100), usd(sp["2020_2020"]["median_abs_diff"], 2)]],
      [5, 2.6, 2.6, 3.4, 2.6], numeric_from=1, title="Bukti pergeseran Sales: transaksi dengan produk, jumlah, dan profit yang sama")
para(f"Pada 2019 transaksi yang sama selalu bernilai sama, sedangkan yang melibatkan 2020 hampir selalu berbeda sebesar bilangan bulat. Pola ini mengarah pada perubahan pencatatan atau rekayasa nilai, bukan kenaikan penjualan nyata; harga satuan median per produk pun naik {num(R['shift_unit_ratio']['median'], 1)} kali lipat dalam semalam. Penyebab pastinya tidak dapat dipastikan dari data, dan nilai aslinya tidak dapat dipulihkan. **Keputusan:** Sales dan margin hanya dibandingkan dalam tahun yang sama, dan fitur Sales distandardisasi per tahun.")
figure("02_tren_bulanan.png", 15.5, "Median Sales melompat tepat pada Januari 2020 (garis putus-putus), sedangkan median Profit tetap stabil. Jumlah order memuncak setiap akhir tahun.",
       "Tiga grafik garis bulanan: median Sales melompat pada Januari 2020, median Profit stabil, jumlah order memuncak akhir tahun")
para(f"**Nilai yang mustahil.** {R['impossible_n']} baris memiliki Profit > Sales, yang berarti biaya negatif, sehingga **dihapus**. Dampaknya besar: profit total turun {usd(R['impossible_profit'])} ({pct(R['impossible_profit'] / R['profit_total_raw'])}). Sebanyak {R['high_margin_n']} baris lain bermargin 50–100%. Baris ini mencurigakan karena {num(R['margin_valid_positive_n'])} baris untung lainnya tidak pernah melewati 50%, tetapi secara logika masih mungkin, sehingga **dipertahankan dan ditandai** (`Flag_Margin_Tinggi`). Filter lain tidak menemukan masalah: tanggal kirim sebelum order {R['ship_before_order']} baris dan Sales ≤ 0 sebanyak {R['sales_nonpositive']} baris.")
para(f"**Outlier statistik.** Metode IQR menandai {num(R['iqr']['Profit']['n'])} baris Profit ({pct(R['iqr']['Profit']['pct'] / 100)}) dan {R['iqr']['Quantity']['n']} baris Quantity ({pct(R['iqr']['Quantity']['pct'] / 100)}). Baris ini **tidak dihapus** karena transaksi ekstrem justru informasi bisnis: {pct(R['loss_top5pct_share'])} nilai kerugian berasal dari 5% baris rugi terburuk. Dampaknya ditangani dengan transformasi log dan uji berbasis peringkat. Kerugian melebihi nilai Sales ({R['margin_loss_gt_sales_n']} baris) juga dipertahankan karena masih mungkin terjadi.")
s = R["sensitivity"]
table([["Skenario", "Baris", "Total profit", "Technology", "Office Supplies", "% rugi Central", "% rugi West"]] +
      [[x["Skenario"], num(x["Baris"]), usd(x["Total_Profit"]), usd(x["Technology"]), usd(x["Office"]), pct(x["Loss_Central"]), pct(x["Loss_West"])] for x in s],
      [5.2, 1.5, 2, 2, 2.1, 1.9, 1.9], numeric_from=1, title="Sensitivitas: pola utama stabil, tetapi nilai total bergantung pada penanganan anomali")
para(f"Persentase rugi per region hampir tidak berubah, jadi temuan utama tidak bergantung pada keputusan ini. Sebaliknya, peringkat total profit Technology dan Office Supplies dapat bertukar, sehingga keduanya sebaiknya dianggap setara. Machines juga rapuh: profitnya {usd(R['machines_note']['profit'])}, tetapi menjadi {usd(R['machines_note']['profit_no_flag'])} tanpa satu baris yang ditandai.")

doc.add_heading("2.3 Feature Transformation", 2)
bullet(f"**Log:** `log(1 + Sales)` dan `log(1 + harga satuan)` karena distribusinya sangat miring. Skewness Sales 2019 turun dari {num(R['skew']['Sales_2019'], 2)} menjadi {num(R['skew']['SalesLog_2019'], 2)}; pada 2020 dari {num(R['skew']['Sales_2020'], 2)} menjadi {num(R['skew']['SalesLog_2020'], 2)}.")
bullet("**Standardisasi per tahun** untuk Sales dan harga satuan agar pergeseran 2020 tidak terbaca sebagai sinyal; **StandardScaler** untuk fitur numerik lain.")
bullet("**One-hot encoding** untuk Sub-Category, Region, Segment, Ship Mode, dan Payment Mode karena nominal, dengan satu kategori acuan dihapus.")
bullet("**Target encoding** untuk State (49 kategori) dengan smoothing dan skema out-of-fold per order, agar jumlah kolom tidak meledak dan target tidak bocor.")
bullet("**Sin dan cos bulan** agar Desember dan Januari terbaca berdekatan.")
para("Semua parameter transformasi dihitung dari data train saja, lalu diterapkan ke data validasi dan test.")

doc.add_heading("2.4 Feature Engineering", 2)
table([["Fitur baru", "Definisi", "Kegunaan"],
       ["`Is_Loss`", "1 jika Profit < 0", "Target; metrik utama kebocoran profit"],
       ["`Profit_Margin`", "Profit / Sales", "Analisis dalam tahun yang sama; tidak dipakai sebagai fitur model karena membocorkan target"],
       ["`Unit_Price`", "Sales / Quantity", "Tingkat harga produk"],
       ["`Ship_Lead_Days`", "Ship Date − Order Date", "Kinerja logistik; tidak dipakai model karena baru diketahui setelah order"],
       ["`Order_Lines`", "Jumlah baris dalam satu order", "Ukuran keranjang belanja"],
       ["`Customer_Prior_Orders`", "Jumlah order pelanggan sebelumnya", "Loyalitas; tidak dipakai model karena nilainya naik mengikuti waktu (lihat Bagian 4)"],
       ["Komponen waktu", "Tahun, bulan, kuartal, akhir pekan", "Musiman dan kontrol tahun"]],
      [4, 5.2, 7.4], title="Fitur hasil feature engineering")

doc.add_heading("2.5 Dimensionality Reduction dan Feature Selection", 2)
pc = R["pca"]; vs = R["var_scores"]
para(f"**PCA** membutuhkan {pc['k90']} dari {R['n_features_candidate']} komponen untuk menjelaskan {pct(pc['var_k90'])} varians, dengan dua komponen pertama hanya {pct(pc['pc1'])} dan {pct(pc['pc2'])}. Artinya tidak ada struktur berdimensi rendah yang kuat. **Seleksi fitur** menggabungkan dua pendekatan dengan tiga skor: filter (mutual information), embedded (Lasso L1 dan Random Forest importance). Variabel lolos jika masuk 6 besar pada minimal 2 dari 3 skor, dan dinilai per variabel supaya kategori tidak terpecah.")
table([["Variabel", "Mutual info", "Lasso |koef|", "RF importance", "Vote", "Status"]] +
      [[x["Variabel"], num(x["MI"], 3), num(x["L1"], 3), num(x["RF"], 3), x["Vote"], "Dipilih" if x["Vote"] >= 2 else "Dibuang"] for x in vs],
      [5, 2.2, 2.2, 2.4, 1.2, 2], numeric_from=1, title="Skor seleksi fitur per variabel (dihitung hanya pada data train, lihat Bagian 2.6)")
table([["Set fitur", "Jumlah fitur", "AUC validasi", "AUC test (CI 95%)", "PR-AUC test", "Recall", "Precision"]] +
      [[e["Set"], e["Fitur"], num(e["Val_AUC"], 3), f"{num(e['ROC_AUC'], 3)} ({num(e['AUC_CI'][0], 3)}–{num(e['AUC_CI'][1], 3)})", num(e["PR_AUC"], 3), num(e["Recall"], 3), num(e["Precision"], 3)] for e in R["eval"]],
      [4.4, 1.6, 1.8, 3.6, 1.7, 1.4, 1.6], numeric_from=1, title="Perbandingan set fitur memakai Logistic Regression")
para(f"**Keputusan:** dipakai **seleksi per variabel**, karena dengan {evs['Fitur']} fitur kinerjanya setara dengan semua kandidat (AUC validasi tertinggi), sedangkan PCA dan seleksi per dummy menurunkan kinerja. Sebagai pembanding, proporsi kelas rugi pada data test adalah {num(R['eval_base_pr'], 3)}, jadi PR-AUC {num(evs['PR_AUC'], 3)} jauh di atas tebakan acak. Tanpa fitur Sales dan harga satuan, AUC tetap {num(R['eval_nosales']['ROC_AUC'], 3)}, sehingga sinyal utamanya berasal dari wilayah dan produk, bukan dari Sales yang bermasalah. Data final setelah model dilatih ulang pada train + validasi: train {num(R['audit']['train_shape'][0])} × {R['audit']['train_shape'][1]} dan test {num(R['audit']['test_shape'][0])} × {R['audit']['test_shape'][1]}, tanpa nilai kosong maupun tak hingga.")

doc.add_heading("2.6 Split Data", 2)
sl = R["split"]
para("Data dibagi secara **kronologis**, bukan acak, karena model nantinya memprediksi transaksi masa depan. Satu order tidak pernah terpecah sehingga tidak ada kebocoran antarbagian "
     f"(order yang tumpang tindih: {R['split_overlap']}).")
table([["Bagian", "Periode", "Baris", "% rugi", "Fungsi"],
       ["Train", f"{sl['fit']['from']} s.d. {sl['fit']['to']}", num(sl["fit"]["n"]), pct(sl["fit"]["loss"]), "Melatih model dan memilih fitur"],
       ["Validasi", f"{sl['val']['from']} s.d. {sl['val']['to']}", num(sl["val"]["n"]), pct(sl["val"]["loss"]), "Membandingkan set fitur"],
       ["Test", f"{sl['test']['from']} s.d. {sl['test']['to']}", num(sl["test"]["n"]), pct(sl["test"]["loss"]), "Evaluasi akhir"]],
      [2, 5.4, 1.5, 1.5, 6], title="Pembagian data")
para("Proporsi rugi sekitar 19% tergolong tidak seimbang, tetapi kami memakai `class_weight=\"balanced\"` dan tidak memakai oversampling, supaya tidak menciptakan transaksi sintetis.")

# ---------------------------------------------------------------- 3
doc.add_heading("3. Statistik Deskriptif dan Distribusi Data", 1)
table([["Variabel", "n", "Mean", "Median", "Std", "Q1", "Q3", "Min", "Maks", "Skew", "Kurt"]] +
      [[d["Variabel"], num(d["n"])] + [num(d[k] * (100 if "Margin" in d["Variabel"] else 1), 1 if d["Variabel"].split()[0] in ("Quantity", "Lama") or "Margin" in d["Variabel"] else 2) for k in ("mean", "median", "std", "q1", "q3", "min", "max")] + [num(d["skew"], 2), num(d["kurt"], 1)] for d in R["describe"]],
      [3.2, 1.1, 1.3, 1.3, 1.3, 1.2, 1.2, 1.5, 1.4, 1.1, 1.1], size=8, numeric_from=1, title="Statistik deskriptif (margin dalam persen; Sales dan margin dipisah per tahun)")
pd_ = R["describe"][0]
para(f"**Profit** bersifat sangat tidak normal: rata-rata {usd(pd_['mean'], 2)} jauh di atas median {usd(pd_['median'], 2)}, skewness {num(pd_['skew'], 2)}, kurtosis {num(pd_['kurt'], 0)}, dan rentang {usd(pd_['min'])} sampai {usd(pd_['max'])}. Sebagian besar transaksi untung kecil, tetapi segelintir transaksi rugi besar menentukan hasil akhir. Maka median dan persentase rugi lebih representatif daripada rata-rata. **Uji normalitas** D'Agostino K² menolak normalitas pada semua variabel (p < 0,001), termasuk Sales setelah transformasi log, sehingga analisis inferensial memakai uji nonparametrik.")
rows = [["Kelompok", "Baris", "Total profit", "Median profit", "% baris rugi", "Margin 2019", "Nilai rugi"]]
for key, field in [("group_Region", "Region"), ("group_Category", "Category"), ("group_Segment", "Segment")]:
    for x in R[key]:
        rows.append([x[field], num(x["Baris"]), usd(x["Profit"]), usd(x["Median_Profit"], 2), pct(x["Loss_Rate"]), pct(x["Margin_2019"]), usd(x["Rugi_USD"])])
table(rows, [4, 1.5, 2.2, 2.2, 2, 2, 2.2], numeric_from=1, title="Ringkasan per region, kategori, dan segmen")
oy, py = R["orders_by_year"], R["profit_by_year"]
para(f"Central dan Furniture menonjol sebagai titik lemah, sementara ketiga segmen hampir sama. Antartahun, jumlah order naik dari {num(oy['2019'])} ke {num(oy['2020'])} ({pct(oy['2020'] / oy['2019'] - 1)}) dan profit naik dari {usd(py['2019'])} ke {usd(py['2020'])} ({pct(py['2020'] / py['2019'] - 1)}). Kuartal IV menyumbang {pct(R['q4_order_share'])} order tetapi hanya {pct(R['q4_profit_share'])} profit. Dari sisi pelanggan, 20% teratas menghasilkan {pct(R['top20_cust_profit_share'], 0)} profit bersih dan {pct(R['cust_negative_share'], 0)} pelanggan bernilai negatif.")

# ---------------------------------------------------------------- 4
doc.add_heading("4. Uji Statistik Inferensial dan Hubungan Antar Variabel", 1)
para("Karena data tidak normal, kami memakai **Kruskal-Wallis** dan **Mann-Whitney** untuk Profit, **Chi-square** untuk variabel kategorik, dan **Spearman** untuk korelasi, dengan taraf signifikansi α = 0,05. Nilai p dikoreksi metode **Holm** karena banyak uji dilakukan sekaligus. Dengan ribuan baris, efek kecil pun mudah signifikan, sehingga **ukuran efek** ikut dilaporkan. H₀ setiap uji: tidak ada perbedaan atau hubungan antarkelompok.")
LBLT = {"~": "menurut", "x": "dan"}
def rel(h):
    return h.replace("Negara_Bagian", "Negara bagian").replace("Is_Loss x ", "Status rugi × ").replace("Returned x ", "Retur × ").replace("Profit ~ Returned", "Profit × Retur").replace("Profit ~ ", "Profit × ")
table([["Hubungan", "Uji", "Data", "Statistik (df)", "p Holm", "Ukuran efek", "Keputusan"]] +
      [[rel(t["Hubungan"]), t["Uji"], t["Data"], num(t["Statistik"], 1) + (f" ({t['df']})" if t["df"] else ""), pv(t["p_holm"]), f"{t['Ukuran_Efek']} = {num(t['Efek'], 3)}", "**Tolak H₀**" if t["p_holm"] < 0.05 else "Gagal tolak"] for t in R["tests"]],
      [4, 2.5, 1.7, 2.3, 1.3, 3, 1.8], size=8.5, title="Hasil uji inferensial")
v_sub = by("tests", "Is_Loss x Sub-Category", "Hubungan")
v_reg = by("tests", "Is_Loss x Region", "Hubungan")
v_st = by("tests", "Is_Loss x Negara_Bagian", "Hubungan")
v_cat = by("tests", "Is_Loss x Category", "Hubungan")
k_cat = by("tests", "Profit ~ Category", "Hubungan")
v_ret = by("tests", "Returned x Region", "Hubungan")
stab = {(s_["Hubungan"], s_["Data"]): s_["Efek"] for s_ in R["stability"]}
para("**Interpretasi:**")
bullet(f"**Negara bagian** (V = {num(v_st['Efek'], 2)}; {R['state_test_groups']} kelompok, yang n < 30 digabung) dan **sub-kategori** (V = {num(v_sub['Efek'], 2)}) adalah pembeda terkuat status rugi, dengan efek kuat, diikuti **kategori** (V = {num(v_cat['Efek'], 2)}) dan **region** (V = {num(v_reg['Efek'], 2)}). Pola ini konsisten pada kedua tahun: V region {num(stab[('Is_Loss x Region', '2019')], 2)} dan {num(stab[('Is_Loss x Region', '2020')], 2)}, V sub-kategori {num(stab[('Is_Loss x Sub-Category', '2019')], 2)} dan {num(stab[('Is_Loss x Sub-Category', '2020')], 2)}.")
bullet(f"Untuk nilai **Profit**, perbedaan kategori dan region signifikan tetapi efeknya kecil (ε² = {num(k_cat['Efek'], 3)} untuk kategori). Jadi variasi terbesar Profit ada di tingkat transaksi, dan status rugi lebih informatif untuk keputusan.")
bullet(f"**Segmen, cara kirim, dan cara bayar tidak berhubungan** secara signifikan dengan profit maupun status rugi.")
bullet(f"**Retur** berhubungan dengan region (V = {num(v_ret['Efek'], 2)}): West {pct(rw['Rate'])}, sedangkan keseluruhan {pct(R['return_overall'])}. Profit baris yang diretur tidak berbeda signifikan.")
ph = R["posthoc_region"]
ns = [x["Pasangan"] for x in ph if x["p_holm"] >= 0.05]
para(f"**Uji lanjut region** (Mann-Whitney berpasangan, Holm): semua pasangan berbeda signifikan kecuali {', '.join(ns)}. Perbedaan terbesar adalah West dengan Central (median {usd(by('posthoc_region', 'West vs Central', 'Pasangan')['median_a'], 2)} dan {usd(by('posthoc_region', 'West vs Central', 'Pasangan')['median_b'], 2)}).")
sr = R["spearman"]
PAIRNAME = {"Sales - Profit": "Sales – Profit", "Sales - Quantity": "Sales – Quantity", "Quantity - Profit": "Quantity – Profit", "Unit_Price - Profit_Margin": "Harga satuan – Margin",
            "Ship_Lead_Days - Profit": "Lama kirim – Profit", "Order_Lines - Profit": "Baris per order – Profit", "Customer_Prior_Orders - Profit_Margin": "Order sebelumnya – Margin"}
table([["Pasangan variabel", "ρ gabungan", "ρ 2019 (CI 95%)", "p Holm 2019", "ρ 2020 (CI 95%)", "p Holm 2020"]] +
      [[PAIRNAME[x["Pasangan"]], num(x["rho_gabungan"], 3), f"{num(x['rho_2019'], 3)} ({num(x['lo_2019'], 2)}; {num(x['hi_2019'], 2)})", pv(x["p_holm_2019"]), f"{num(x['rho_2020'], 3)} ({num(x['lo_2020'], 2)}; {num(x['hi_2020'], 2)})", pv(x["p_holm_2020"])] for x in sr],
      [4.5, 1.8, 3.5, 1.6, 3.5, 1.6], numeric_from=1, title="Korelasi Spearman per tahun")
pr = next(x for x in sr if x["Pasangan"].startswith("Customer_Prior"))
sp0 = sr[0]
para(f"Sales berhubungan positif sedang dengan Profit, tetapi melemah dari ρ = {num(sp0['rho_2019'], 2)} ke {num(sp0['rho_2020'], 2)} akibat pergeseran Sales. Lama kirim dan ukuran order tidak berhubungan dengan Profit. **Contoh pentingnya analisis per tahun:** order sebelumnya dan margin tampak berkorelasi negatif bila digabung (ρ = {num(pr['rho_gabungan'], 2)}), yang bisa keliru dibaca sebagai “pelanggan setia kurang menguntungkan”. Per tahun, korelasinya hilang (ρ = {num(pr['rho_2019'], 2)} dan {num(pr['rho_2020'], 2)}), karena keduanya hanya sama-sama mengikuti waktu.")
LG = {"Region_Central": "Region Central (acuan West)", "Region_East": "Region East", "Region_South": "Region South", "Category_Furniture": "Furniture (acuan Office Supplies)", "Category_Technology": "Technology",
      "Segment_Corporate": "Corporate (acuan Consumer)", "Segment_Home Office": "Home Office", "Sales_Log_Z": "log Sales, standar per tahun", "Quantity": "Quantity", "Tahun_2020": "Tahun 2020 (acuan 2019)"}
table([["Variabel", "Odds ratio", "CI 95%", "p"]] + [[LG[x["Variabel"]], num(x["OR"], 2), f"{num(x['lo'], 2)} – {num(x['hi'], 2)}", pv(x["p"])] for x in R["logit"]],
      [7.5, 2.4, 3.6, 2], numeric_from=1, title="Regresi logistik risiko rugi (galat baku cluster per order)")
lg = {x["Variabel"]: x for x in R["logit"]}
para(f"Setelah variabel lain dikendalikan, peluang (odds) rugi di **Central {num(lg['Region_Central']['OR'], 1)} kali** West dan pada **Furniture {num(lg['Category_Furniture']['OR'], 1)} kali** Office Supplies. Segmen, Quantity, dan tahun tidak signifikan. Tidak signifikannya tahun memperkuat bahwa risiko rugi stabil antartahun. Model ini sengaja sederhana untuk tujuan penjelasan (pseudo R² = {num(R['logit_pseudo_r2'], 3)}).")

# ---------------------------------------------------------------- 5
doc.add_heading("5. Visualisasi Data", 1)
doc.add_heading("5.1 Histogram", 2)
figure("01_histogram.png", 16.4, "Distribusi Profit, log Sales, dan margin per tahun.", "Tiga histogram: Profit terpusat dekat nol, log Sales bergeser ke kanan pada 2020, margin menyempit pada 2020")
para("Histogram dipilih untuk melihat bentuk distribusi. Profit terpusat tepat di atas nol dengan ekor panjang di kedua sisi. Log Sales dan margin memperlihatkan dua distribusi yang jelas berbeda antara 2019 dan 2020, yang mendukung keputusan untuk tidak menggabungkan kedua tahun pada variabel berbasis Sales.")
doc.add_heading("5.2 Heatmap", 2)
figure("05_heatmap_korelasi.png", 16.4, "Korelasi Spearman antar variabel numerik, dipisah per tahun.", "Dua heatmap korelasi untuk 2019 dan 2020")
para(f"Heatmap korelasi meringkas banyak hubungan sekaligus. Perbandingan kedua panel memperlihatkan hubungan yang melibatkan Sales melemah pada 2020, misalnya Sales dengan Profit dari {num(R['corr_sales_profit']['2019'], 2)} ke {num(R['corr_sales_profit']['2020'], 2)}. Lama kirim dan baris per order hampir nol terhadap semua variabel.")
figure("06_heatmap_rugi.png", 13, "Persentase baris rugi menurut region dan kategori.", "Heatmap persentase rugi region dan kategori; Central Furniture tertinggi")
hw = by("heat_region_category", "West", "Region")
para(f"Heatmap ini menunjukkan interaksi yang tidak terlihat bila region dan kategori dilihat terpisah. **Furniture di Central merugi pada {num(hrc['Furniture'], 1)}% baris**, hampir tiga kali Furniture di West ({num(hw['Furniture'], 1)}%). Technology justru lebih bermasalah di East daripada Central, sehingga kebijakan perlu spesifik per kombinasi region dan kategori.")
doc.add_heading("5.3 Bar Chart", 2)
figure("03_bar_subkategori.png", 14, "Total profit per sub-kategori, 2019–2020.", "Diagram batang profit per sub-kategori; Tables terendah dan Accessories tertinggi")
sup = by("group_Sub-Category", "Supplies", "Sub-Category")
para(f"Bar chart memudahkan perbandingan antarproduk. Tables ({usd(tables_['Profit'])}) dan Supplies ({usd(sup['Profit'])}) merugi secara total, sedangkan Machines dan Bookcases berada di sekitar impas. Accessories, Phones, Copiers, dan Paper menjadi penopang profit. Copiers menonjol: median {usd(by('group_Sub-Category', 'Copiers', 'Sub-Category')['Median_Profit'])} per baris, tetapi hanya {by('group_Sub-Category', 'Copiers', 'Sub-Category')['Baris']} baris.")
figure("04_bar_rugi_wilayah.png", 16.4, "Persentase baris rugi per region dan per negara bagian.", "Diagram batang persentase rugi per region dan negara bagian tertinggi")
stl = R["state_top_loss"]
para(f"Kerugian sangat terkonsentrasi secara geografis. {stl[0]['State']} mencatat kerugian bersih terbesar ({usd(stl[0]['Profit'])}), disusul {stl[1]['State']} ({usd(stl[1]['Profit'])}), {stl[2]['State']} ({usd(stl[2]['Profit'])}), dan {stl[3]['State']} ({usd(stl[3]['Profit'])}). Sebaliknya, California dan New York memiliki persentase rugi di bawah 6%.")

# ---------------------------------------------------------------- 6
doc.add_heading("6. Insight Pemasaran dan Keputusan Bisnis", 1)
cal, ny = by("state_top_profit", "California", "State"), by("state_top_profit", "New York", "State")
binders = by("group_Sub-Category", "Binders", "Sub-Category")
table([["Prioritas", "Temuan", "Keputusan yang disarankan", "Ukuran keberhasilan"],
       ["1. Wilayah rugi", f"{sn['n']} negara bagian: {pct(sn['loss_share'], 0)} nilai rugi, profit bersih {usd(sn['profit'])}", "Audit harga, promosi, dan biaya di Texas, Illinois, Ohio, dan Pennsylvania dulu, lalu batasi promosi di sana lewat uji coba bertahap", "% baris rugi; profit per negara bagian"],
       ["2. Produk rugi", f"Tables rugi {pct(tables_['Loss_Rate'], 0)} baris; Binders nilai rugi terbesar ({usd(binders['Rugi_USD'])}); Furniture di Central rugi {num(hrc['Furniture'], 0)}%", "Tetapkan batas harga minimum untuk Tables dan Furniture di Central; kaji struktur biaya Binders", "Profit per sub-kategori"],
       ["3. Penargetan", "Segmen tidak membedakan profit, status rugi, maupun retur", "Hentikan penetapan diskon berbasis segmen; gunakan segmen hanya untuk pesan komunikasi", "Profit per kampanye"],
       ["4. Retur West", f"{pct(rw['Rate'])} order West diretur, keseluruhan {pct(R['return_overall'])}", "Telusuri alasan retur di West (produk, pengiriman, deskripsi) sebelum menambah anggaran promosi di sana", "% retur West"],
       ["5. Produk unggulan", "Paper, Labels, Envelopes, Art, dan Copiers tidak pernah rugi", "Jadikan produk utama bundling dan cross-sell, terutama di wilayah rugi", "Profit per order"],
       ["6. Akhir tahun", f"Kuartal IV: {pct(R['q4_order_share'])} order, {pct(R['q4_profit_share'])} profit", "Rencanakan promosi akhir tahun dengan batas margin, bukan mengejar volume semata", "Profit Q4 per order"],
       ["7. Pelanggan", f"20% teratas: {pct(R['top20_cust_profit_share'], 0)} profit bersih; {pct(R['cust_negative_share'], 0)} pelanggan negatif", "Program loyalitas untuk pelanggan bernilai tinggi; tinjau syarat untuk pelanggan yang selalu rugi", "Retensi pelanggan teratas"],
       ["8. Peringatan dini", f"Model memprediksi rugi dengan recall {pct(evs['Recall'], 0)} dan precision {pct(evs['Precision'], 0)}", "Uji coba sebagai alat bantu persetujuan harga, dengan transaksi berisiko ditinjau sebelum diproses", "Nilai rugi yang tercegah"]],
      [2.3, 5.3, 6, 3], size=9, title="Rekomendasi berdasarkan prioritas")
para(f"**Skenario peluang:** bila {sn['n']} negara bagian tersebut hanya mencapai titik impas, profit bertambah {usd(abs(sn['profit']))}, atau **{pct(abs(sn['profit']) / tot, 0)}** dari profit saat ini. Ini gambaran besarnya peluang dengan asumsi volume tetap, bukan proyeksi.")

# ---------------------------------------------------------------- 7
doc.add_heading("7. Keterbatasan", 1)
bullet("**Tidak ada kolom diskon maupun biaya.** Penyebab rugi tidak dapat disimpulkan; hubungan yang ditemukan bersifat asosiasi. Rekomendasi perlu diuji coba sebelum diterapkan penuh, dan data diskon perlu diperoleh.")
bullet(f"**Kualitas Sales dipertanyakan.** Sales dan margin 2020 tidak dapat dipulihkan, dan {R['impossible_n']} baris yang dihapus memengaruhi profit total sebesar {pct(R['impossible_profit'] / R['profit_total_raw'])}. Pemilik data perlu mengonfirmasi penyebabnya.")
bullet("**Retur hanya tersedia untuk 2020**, sehingga tidak ada perbandingan antartahun.")
bullet("**Periode data hanya dua tahun**, dan data test hanya mencakup kuartal IV 2020, sehingga kinerja model pada musim lain belum teruji.")
bullet("**Baris dalam satu order tidak sepenuhnya independen.** Regresi logistik sudah memperhitungkannya, sedangkan uji lain pada tingkat baris dapat sedikit melebih-lebihkan signifikansi; karena itu ukuran efek lebih diutamakan.")
para("Kode analisis lengkap tersedia pada berkas `analisis_superstore.py` dan dapat dijalankan ulang untuk menghasilkan seluruh angka dan grafik dalam laporan ini.", size=10)

out = ROOT / "UTS_BISE_Laporan_Superstore.docx"
doc.save(out)
print("ditulis", out.name)
