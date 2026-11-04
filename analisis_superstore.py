"""UTS BISE - Analisis Superstore Sales: preprocessing, statistik, dan visualisasi.

Jalankan dari folder mana pun:  python analisis_superstore.py
Hasil: figures/*.png, output/results.json, output/*.csv

Catatan metodologi: Sales pada 2020 mengalami pergeseran struktural (lihat bagian 3),
sehingga metrik utama lintas tahun adalah Profit dan Is_Loss. Sales dan margin hanya
dibandingkan di dalam tahun yang sama. Retur hanya tercatat pada 2020.
"""
import json
import warnings
from itertools import combinations
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from matplotlib.colors import LinearSegmentedColormap
from scipy import stats
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_selection import mutual_info_classif
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
from statsmodels.stats.multitest import multipletests

warnings.filterwarnings("ignore")
RS = 42
ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data/raw/superstore/SuperStore_Sales_Dataset.csv"
FIG, OUT = ROOT / "figures", ROOT / "output"
FIG.mkdir(exist_ok=True); OUT.mkdir(exist_ok=True)
R = {}  # seluruh angka untuk laporan

# Warna: biru = untung / 2019, aqua = 2020, oranye = rugi
BLUE, AQUA, ORANGE, INK, MUTED, GRID = "#2a78d6", "#1baf7a", "#eb6834", "#0b0b0b", "#52514e", "#e6e5e0"
plt.rcParams.update({
    "font.family": ["Calibri", "DejaVu Sans"], "font.size": 11, "axes.edgecolor": GRID,
    "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK,
    "axes.titlesize": 12.5, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": False,
    "grid.color": GRID, "grid.linewidth": 0.8, "figure.dpi": 100, "savefig.dpi": 200,
    "savefig.bbox": "tight", "savefig.facecolor": "white",
})
SEQ = LinearSegmentedColormap.from_list("seq", ["#f4f8fd", "#a9cbf0", "#2a78d6", "#123e78"])
DIV = LinearSegmentedColormap.from_list("div", [ORANGE, "#f1f0ec", BLUE])


def tbl(frame):
    return json.loads(frame.reset_index().to_json(orient="records"))


# %% 1. Load dan audit awal
raw = pd.read_csv(RAW, encoding="utf-8-sig")
raw = raw.rename(columns={raw.columns[0]: "Row ID"})
R["raw_shape"] = list(raw.shape)
R["missing_raw"] = {k: int(v) for k, v in raw.isna().sum().items() if v}
R["dup_exact"] = int(raw.duplicated().sum())
R["dup_excl_rowid"] = int(raw.drop(columns="Row ID").duplicated().sum())
R["dup_rowid"] = int(raw["Row ID"].duplicated().sum())
R["dup_order_product"] = int(raw.duplicated(["Order ID", "Product ID"]).sum())
R["product_id_multi_name"] = int((raw.groupby("Product ID")["Product Name"].nunique() > 1).sum())

# %% 2. Data cleaning
df = raw.copy()
for c in ["Order Date", "Ship Date"]:
    df[c] = pd.to_datetime(df[c], format="%d-%m-%Y")
R["date_range"] = [str(df["Order Date"].min().date()), str(df["Order Date"].max().date())]
multi_date = df.groupby("Order ID")["Order Date"].transform("nunique") > 1
R["orders_multi_date"] = int(df.loc[multi_date, "Order ID"].nunique())
df["Order Date"] = df.groupby("Order ID")["Order Date"].transform("min")
df["Order_Year"] = df["Order Date"].dt.year

# Retur tercatat hanya pada 2020: kosong = tidak diretur untuk 2020, tidak diketahui untuk 2019
R["returned_by_year"] = {int(y): int(n) for y, n in df.groupby("Order_Year")["Returns"].count().items()}
R["returned_orders_by_year"] = tbl(df.drop_duplicates("Order ID").groupby("Order_Year")["Returns"].agg(["count", "size"]))
df["Returned"] = np.where(df["Order_Year"] == 2020, df["Returns"].fillna(0), np.nan)
R["returned_consistent_in_order"] = bool((df[df["Order_Year"] == 2020].groupby("Order ID")["Returned"].nunique() == 1).all())
df = df.drop(columns=["Row ID", "Returns", "ind1", "ind2", "Country", "Customer Name", "Product Name"])

# %% 3. Filtering, outlier, dan audit pergeseran Sales 2020
df["Profit_Margin"] = df["Profit"] / df["Sales"]
R["ship_before_order"] = int((df["Ship Date"] < df["Order Date"]).sum())
R["sales_nonpositive"] = int((df["Sales"] <= 0).sum())
impossible = df["Profit"] > df["Sales"]
R["impossible_n"] = int(impossible.sum())
R["impossible_by_year"] = {int(k): int(v) for k, v in df[impossible].groupby("Order_Year").size().items()}
R["impossible_profit"] = float(df.loc[impossible, "Profit"].sum())
R["profit_total_raw"] = float(df["Profit"].sum())
high_margin = (df["Profit_Margin"] > 0.5) & ~impossible
R["high_margin_n"] = int(high_margin.sum())
R["high_margin_profit"] = float(df.loc[high_margin, "Profit"].sum())
R["margin_valid_positive_n"] = int(((df["Profit_Margin"] > 0) & (df["Profit_Margin"] <= 0.5)).sum())
R["margin_loss_gt_sales_n"] = int((df["Profit_Margin"] < -1).sum())

df_all = df.copy()
df = df[~impossible].copy()
df["Flag_Margin_Tinggi"] = (df["Profit_Margin"] > 0.5).astype(int)


def iqr_info(s):
    q1, q3 = s.quantile([0.25, 0.75])
    lo, hi = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
    return {"lo": float(lo), "hi": float(hi), "n": int(((s < lo) | (s > hi)).sum()), "pct": float(((s < lo) | (s > hi)).mean() * 100)}


R["iqr"] = {c: iqr_info(df[c]) for c in ["Quantity", "Profit"]}
R["iqr_sales_by_year"] = {int(y): iqr_info(g["Sales"]) for y, g in df.groupby("Order_Year")}

a, b = df[df["Order_Year"] == 2019], df[df["Order_Year"] == 2020]
keys = ["Product ID", "Quantity", "Profit_R"]
a, b = a.assign(Profit_R=a["Profit"].round(3)), b.assign(Profit_R=b["Profit"].round(3))


def pair_stats(x, y, same=False):
    m = x.merge(y, on=keys, suffixes=("_a", "_b"))
    m = m[m["Order ID_a"] != m["Order ID_b"]]
    dif = (m["Sales_b"] - m["Sales_a"]).abs()
    rounded = np.isclose(dif, dif.round(), atol=0.001)
    return {"pairs": len(m) // (2 if same else 1), "same_sales_pct": float((dif < 0.001).mean() * 100),
            "integer_nonzero_pct": float((rounded & (dif >= 0.5)).mean() * 100), "median_abs_diff": float(dif.median())}


R["shift_pairs"] = {"2019_2019": pair_stats(a, a, True), "2019_2020": pair_stats(a, b), "2020_2020": pair_stats(b, b, True)}
pu = df.assign(Unit=df["Sales"] / df["Quantity"]).pivot_table(index="Product ID", columns="Order_Year", values="Unit", aggfunc="median").dropna()
R["shift_unit_ratio"] = {"products": len(pu), "median": float((pu[2020] / pu[2019]).median())}
R["year_medians"] = tbl(df.groupby("Order_Year").agg(Baris=("Sales", "size"), Order=("Order ID", "nunique"), Sales=("Sales", "median"),
                                                     Quantity=("Quantity", "median"), Profit=("Profit", "median"),
                                                     Margin=("Profit_Margin", "median"), Loss_Rate=("Profit", lambda s: (s < 0).mean())))
near = df[(df["Order Date"] >= "2019-12-01") & (df["Order Date"] <= "2020-01-31")]
R["shift_boundary"] = tbl(near.groupby(near["Order Date"].dt.to_period("M").astype(str))[["Sales", "Profit"]].median().rename_axis("Bulan"))

# %% 4. Feature engineering dan transformasi
df["Unit_Price"] = df["Sales"] / df["Quantity"]
df["Is_Loss"] = (df["Profit"] < 0).astype(int)
df["Ship_Lead_Days"] = (df["Ship Date"] - df["Order Date"]).dt.days
df["Order_Month"] = df["Order Date"].dt.month
df["Order_Quarter"] = df["Order Date"].dt.quarter
df["Is_Weekend"] = (df["Order Date"].dt.dayofweek >= 5).astype(int)
df["Order_Lines"] = df.groupby("Order ID")["Sales"].transform("size")
df["Sales_Log"] = np.log1p(df["Sales"])
df["Unit_Price_Log"] = np.log1p(df["Unit_Price"])
df["Month_Sin"] = np.sin(2 * np.pi * df["Order_Month"] / 12)
df["Month_Cos"] = np.cos(2 * np.pi * df["Order_Month"] / 12)
df["Sales_Log_Z"] = df.groupby("Order_Year")["Sales_Log"].transform(lambda s: (s - s.mean()) / s.std())
ord_ = df[["Order ID", "Customer ID", "Order Date"]].drop_duplicates()
prior = {}
for _, g in ord_.groupby("Customer ID"):
    d = np.sort(g["Order Date"].values)
    prior.update(dict(zip(g["Order ID"], np.searchsorted(d, g["Order Date"].values, side="left"))))
df["Customer_Prior_Orders"] = df["Order ID"].map(prior).astype(int)

R["clean_shape"] = list(df.shape)
R["n_orders"] = int(df["Order ID"].nunique())
R["n_customers"] = int(df["Customer ID"].nunique())
R["n_products"] = int(df["Product ID"].nunique())
R["n_states"] = int(df["State"].nunique())
R["n_cities"] = int(df["City"].nunique())
R["profit_total"] = float(df["Profit"].sum())
R["loss_rate"] = float(df["Is_Loss"].mean())
R["loss_total"] = float(df.loc[df["Is_Loss"] == 1, "Profit"].sum())
R["gain_total"] = float(df.loc[df["Is_Loss"] == 0, "Profit"].sum())
R["skew"] = {"Sales_2019": float(a["Sales"].skew()), "Sales_2020": float(b["Sales"].skew()),
             "SalesLog_2019": float(np.log1p(a["Sales"]).skew()), "SalesLog_2020": float(np.log1p(b["Sales"]).skew())}

# %% 5. Statistik deskriptif
def desc(s, name):
    return {"Variabel": name, "n": int(s.size), "mean": float(s.mean()), "median": float(s.median()), "std": float(s.std()),
            "q1": float(s.quantile(0.25)), "q3": float(s.quantile(0.75)), "min": float(s.min()), "max": float(s.max()),
            "skew": float(s.skew()), "kurt": float(s.kurt())}


y19, y20 = df[df["Order_Year"] == 2019], df[df["Order_Year"] == 2020]
R["describe"] = [desc(df["Profit"], "Profit"), desc(df["Quantity"], "Quantity"), desc(df["Ship_Lead_Days"], "Lama kirim (hari)"),
                 desc(y19["Sales"], "Sales 2019"), desc(y20["Sales"], "Sales 2020"),
                 desc(y19["Unit_Price"], "Harga satuan 2019"), desc(y20["Unit_Price"], "Harga satuan 2020"),
                 desc(y19["Profit_Margin"], "Margin 2019"), desc(y20["Profit_Margin"], "Margin 2020")]


def group_table(col, frame=df):
    g = frame.groupby(col).agg(Baris=("Profit", "size"), Profit=("Profit", "sum"), Median_Profit=("Profit", "median"), Loss_Rate=("Is_Loss", "mean"))
    f19 = frame[frame["Order_Year"] == 2019].groupby(col)[["Sales", "Profit"]].sum()
    g["Margin_2019"] = f19["Profit"] / f19["Sales"]
    g["Rugi_USD"] = frame[frame["Is_Loss"] == 1].groupby(col)["Profit"].sum().reindex(g.index).fillna(0)
    return g


for col in ["Category", "Sub-Category", "Region", "Segment", "Ship Mode", "Payment Mode"]:
    R["group_" + col] = tbl(group_table(col).sort_values("Profit", ascending=False))
st = group_table("State")
R["state_top_loss"] = tbl(st[st["Baris"] >= 30].sort_values("Profit").head(10))
R["state_top_profit"] = tbl(st[st["Baris"] >= 30].sort_values("Profit", ascending=False).head(5))
neg = st[st["Profit"] < 0].index
R["state_negative"] = {"n": len(neg), "names": sorted(neg), "loss_share": float(df[(df["State"].isin(neg)) & (df["Is_Loss"] == 1)]["Profit"].sum() / R["loss_total"]),
                       "line_share": float(df["State"].isin(neg).mean()), "profit": float(df[df["State"].isin(neg)]["Profit"].sum())}
t = df[df["Is_Loss"] == 1]["Profit"]
R["loss_top5pct_share"] = float(t.nsmallest(int(len(t) * 0.05)).sum() / t.sum())
R["orders_by_year"] = {int(k): int(v) for k, v in df.groupby("Order_Year")["Order ID"].nunique().items()}
R["profit_by_year"] = {int(k): float(v) for k, v in df.groupby("Order_Year")["Profit"].sum().items()}
od = df.drop_duplicates("Order ID")
R["q4_order_share"] = float((od["Order_Quarter"] == 4).mean())
R["q4_profit_share"] = float(df.loc[df["Order_Quarter"] == 4, "Profit"].sum() / df["Profit"].sum())
cp = df.groupby("Customer ID")["Profit"].sum().sort_values(ascending=False)
R["top20_cust_profit_share"] = float(cp.iloc[: int(np.ceil(len(cp) * 0.2))].sum() / cp.sum())
R["cust_negative_share"] = float((cp < 0).mean())
ret20 = y20.drop_duplicates("Order ID").assign(Returned=lambda x: x["Returned"].astype(int))
R["return_region"] = tbl(ret20.groupby("Region")["Returned"].agg(Retur="sum", Order="count", Rate="mean"))
R["return_overall"] = float(ret20["Returned"].mean())
R["heat_region_category"] = tbl((df.pivot_table(index="Region", columns="Category", values="Is_Loss") * 100).round(2))
R["loss_by_year_region"] = tbl(df.pivot_table(index="Region", columns="Order_Year", values="Is_Loss").round(4).rename(columns=str))
R["loss_by_year_category"] = tbl(df.pivot_table(index="Category", columns="Order_Year", values="Is_Loss").round(4).rename(columns=str))
R["machines_note"] = {"profit": float(df[df["Sub-Category"] == "Machines"]["Profit"].sum()),
                      "profit_no_flag": float(df[(df["Sub-Category"] == "Machines") & (df["Flag_Margin_Tinggi"] == 0)]["Profit"].sum())}

# %% 6. Statistik inferensial
R["normality"] = []
for name, s in [("Profit", df["Profit"]), ("Sales 2019", y19["Sales"]), ("Sales 2020", y20["Sales"]), ("log(1+Sales) 2019", y19["Sales_Log"]), ("log(1+Sales) 2020", y20["Sales_Log"])]:
    k2, p = stats.normaltest(s)
    R["normality"].append({"Variabel": name, "K2": float(k2), "p": float(p), "skew": float(s.skew()), "kurt": float(s.kurt())})

tests = []


def kruskal(y, g, frame=df, note="semua"):
    groups = [x[y].values for _, x in frame.groupby(g)]
    h, p = stats.kruskal(*groups)
    k, n = len(groups), sum(map(len, groups))
    return {"Uji": "Kruskal-Wallis", "Hubungan": f"{y} ~ {g}", "Statistik": float(h), "df": k - 1, "p": float(p),
            "Efek": float(max((h - k + 1) / (n - k), 0)), "Ukuran_Efek": "ε²", "Data": note}


def chi(x, g, frame=df, note="semua"):
    ct = pd.crosstab(frame[x], frame[g])
    x2, p, dof, _ = stats.chi2_contingency(ct)
    v = np.sqrt(x2 / (ct.values.sum() * (min(ct.shape) - 1)))
    return {"Uji": "Chi-square", "Hubungan": f"{x} x {g}", "Statistik": float(x2), "df": int(dof), "p": float(p),
            "Efek": float(v), "Ukuran_Efek": "Cramér's V", "Data": note}


for g in ["Category", "Region", "Segment", "Ship Mode", "Payment Mode"]:
    tests.append(kruskal("Profit", g))
for g in ["Sub-Category", "Category", "Region", "Segment", "Ship Mode", "Payment Mode"]:
    tests.append(chi("Is_Loss", g))
state_n = df["State"].map(df["State"].value_counts())
df_state = df.assign(Negara_Bagian=df["State"].where(state_n >= 30, "Lainnya"))  # gabung n < 30 agar frekuensi harapan memadai
R["state_test_groups"] = int(df_state["Negara_Bagian"].nunique())
tests.append(chi("Is_Loss", "Negara_Bagian", df_state))
for g in ["Region", "Segment", "Ship Mode"]:
    tests.append(chi("Returned", g, ret20, "order 2020"))
line20 = y20.assign(Returned=y20["Returned"].astype(int))
u, p = stats.mannwhitneyu(line20.loc[line20["Returned"] == 1, "Profit"], line20.loc[line20["Returned"] == 0, "Profit"])
n1, n2 = int(line20["Returned"].sum()), int((line20["Returned"] == 0).sum())
tests.append({"Uji": "Mann-Whitney", "Hubungan": "Profit ~ Returned", "Statistik": float(u), "df": None, "p": float(p),
              "Efek": float(2 * u / (n1 * n2) - 1), "Ukuran_Efek": "rank-biserial", "Data": "baris 2020"})
for t_, q in zip(tests, multipletests([t_["p"] for t_ in tests], method="holm")[1]):
    t_["p_holm"] = float(q)
R["tests"] = tests
R["stability"] = [dict(chi("Is_Loss", g, fr, str(y))) for g in ["Region", "Category", "Sub-Category"] for y, fr in [(2019, y19), (2020, y20)]]

pairs = [("Sales", "Profit"), ("Sales", "Quantity"), ("Quantity", "Profit"), ("Unit_Price", "Profit_Margin"), ("Ship_Lead_Days", "Profit"),
         ("Order_Lines", "Profit"), ("Customer_Prior_Orders", "Profit_Margin")]
sp = []
for x, y in pairs:
    row = {"Pasangan": f"{x} - {y}", "rho_gabungan": float(stats.spearmanr(df[x], df[y])[0])}
    for yr, fr in [(2019, y19), (2020, y20)]:
        rho, p = stats.spearmanr(fr[x], fr[y])
        se = 1.06 / np.sqrt(len(fr) - 3)
        row.update({f"rho_{yr}": float(rho), f"lo_{yr}": float(np.tanh(np.arctanh(rho) - 1.96 * se)), f"hi_{yr}": float(np.tanh(np.arctanh(rho) + 1.96 * se)), f"p_{yr}": float(p)})
    sp.append(row)
adj = multipletests([r[f"p_{y}"] for r in sp for y in (2019, 2020)], method="holm")[1]
for i, r in enumerate(sp):
    r["p_holm_2019"], r["p_holm_2020"] = float(adj[2 * i]), float(adj[2 * i + 1])
R["spearman"] = sp

ph = []
for x, y in combinations(["West", "East", "South", "Central"], 2):
    xa, xb = df.loc[df["Region"] == x, "Profit"], df.loc[df["Region"] == y, "Profit"]
    u, p = stats.mannwhitneyu(xa, xb)
    ph.append({"Pasangan": f"{x} vs {y}", "median_a": float(xa.median()), "median_b": float(xb.median()),
               "rank_biserial": float(2 * u / (len(xa) * len(xb)) - 1), "p": float(p)})
for r, q in zip(ph, multipletests([r["p"] for r in ph], method="holm")[1]):
    r["p_holm"] = float(q)
R["posthoc_region"] = ph

X_lg = pd.get_dummies(df[["Region", "Category", "Segment"]], dtype=float).drop(columns=["Region_West", "Category_Office Supplies", "Segment_Consumer"])
X_lg["Sales_Log_Z"] = df["Sales_Log_Z"]
X_lg["Quantity"] = df["Quantity"]
X_lg["Tahun_2020"] = (df["Order_Year"] == 2020).astype(float)
logit = sm.Logit(df["Is_Loss"], sm.add_constant(X_lg)).fit(disp=0, cov_type="cluster", cov_kwds={"groups": pd.factorize(df["Order ID"])[0]})
ci = logit.conf_int()
R["logit"] = [{"Variabel": k, "OR": float(np.exp(logit.params[k])), "lo": float(np.exp(ci.loc[k, 0])), "hi": float(np.exp(ci.loc[k, 1])), "p": float(logit.pvalues[k])}
              for k in logit.params.index if k != "const"]
R["logit_pseudo_r2"] = float(logit.prsquared)

# %% 7. Sensitivitas terhadap keputusan data anomali
def sens(frame, name):
    fr = frame.assign(Is_Loss=(frame["Profit"] < 0).astype(int))
    c = fr.groupby("Category")["Profit"].sum()
    r = fr.groupby("Region")["Is_Loss"].mean()
    return {"Skenario": name, "Baris": len(fr), "Total_Profit": float(fr["Profit"].sum()), "Furniture": float(c["Furniture"]),
            "Technology": float(c["Technology"]), "Office": float(c["Office Supplies"]), "Loss_Central": float(r["Central"]), "Loss_West": float(r["West"]),
            "V_Region": chi("Is_Loss", "Region", fr)["Efek"]}


R["sensitivity"] = [sens(df_all, "Semua baris dipertahankan"), sens(df, "Dipakai: buang Profit > Sales"), sens(df[df["Flag_Margin_Tinggi"] == 0], "Buang semua margin > 50%")]

# %% 8. Split kronologis: train fit / validasi / test (satu order tidak pernah terpecah)
def cut(frame, q):
    c = frame.groupby("Order Date").size().sort_index().cumsum() / len(frame)
    return c[c >= q].index[0]


cut_test = cut(df, 0.8)
train, test = df[df["Order Date"] <= cut_test].copy(), df[df["Order Date"] > cut_test].copy()
cut_val = cut(train, 0.8)
fit, val = train[train["Order Date"] <= cut_val].copy(), train[train["Order Date"] > cut_val].copy()
R["split"] = {n: {"n": len(f), "from": str(f["Order Date"].min().date()), "to": str(f["Order Date"].max().date()), "loss": float(f["Is_Loss"].mean())}
              for n, f in [("fit", fit), ("val", val), ("test", test)]}
R["split_overlap"] = len(set(train["Order ID"]) & set(test["Order ID"])) + len(set(fit["Order ID"]) & set(val["Order ID"]))

CONT = ["Sales_Z", "Unit_Price_Z", "Quantity", "Order_Lines", "Month_Sin", "Month_Cos", "State_Loss_TE"]
CATS = ["Sub-Category", "Region", "Segment", "Ship Mode", "Payment Mode"]
REF = ["Sub-Category_Paper", "Region_West", "Segment_Consumer", "Ship Mode_Standard Class", "Payment Mode_COD"]


def te_map(fr, m=20):
    g = fr.groupby("State")["Is_Loss"].agg(["sum", "count"])
    return (g["sum"] + m * fr["Is_Loss"].mean()) / (g["count"] + m)


def prepare(A, B):
    """Fit semua transformasi di A saja, lalu terapkan ke A dan B (anti data leakage)."""
    A, B = A.copy(), B.copy()
    rate = A["Is_Loss"].mean()
    A["State_Loss_TE"] = np.nan
    for i, j in GroupKFold(5).split(A, groups=A["Order ID"]):
        A.iloc[j, A.columns.get_loc("State_Loss_TE")] = A.iloc[j]["State"].map(te_map(A.iloc[i])).fillna(rate).values
    B["State_Loss_TE"] = B["State"].map(te_map(A)).fillna(rate)
    for src, dst in [("Sales_Log", "Sales_Z"), ("Unit_Price_Log", "Unit_Price_Z")]:
        par = A.groupby("Order_Year")[src].agg(["mean", "std"])
        for fr in (A, B):
            fr[dst] = (fr[src] - fr["Order_Year"].map(par["mean"])) / fr["Order_Year"].map(par["std"])
    def design(fr):
        return pd.concat([fr[CONT + ["Is_Weekend"]], pd.get_dummies(fr[CATS], dtype=int)], axis=1)
    XA = design(A).drop(columns=REF)
    XB = design(B).reindex(columns=design(A).columns, fill_value=0).drop(columns=REF)
    sc = StandardScaler().fit(XA[CONT])
    XA[CONT], XB[CONT] = sc.transform(XA[CONT]), sc.transform(XB[CONT])
    return XA, XB


X_fit, X_val = prepare(fit, val)
y_fit, y_val = fit["Is_Loss"], val["Is_Loss"]
R["n_features_candidate"] = X_fit.shape[1]
R["n_variables_candidate"] = len(CONT) + 1 + len(CATS)

# %% 9. Reduksi dimensi dan seleksi fitur (dipelajari hanya dari train fit)
pca_full = PCA(random_state=RS).fit(X_fit)
cumvar = np.cumsum(pca_full.explained_variance_ratio_)
k90 = int(np.searchsorted(cumvar, 0.9) + 1)
R["pca"] = {"k90": k90, "var_k90": float(cumvar[k90 - 1]), "pc1": float(pca_full.explained_variance_ratio_[0]), "pc2": float(pca_full.explained_variance_ratio_[1]),
            "top_pc1": pd.Series(pca_full.components_[0], X_fit.columns).abs().nlargest(3).index.tolist(),
            "top_pc2": pd.Series(pca_full.components_[1], X_fit.columns).abs().nlargest(3).index.tolist()}

feat = X_fit.columns
disc = [c not in ("Sales_Z", "Unit_Price_Z", "Month_Sin", "Month_Cos", "State_Loss_TE") for c in feat]
mi = pd.Series(mutual_info_classif(X_fit, y_fit, discrete_features=disc, random_state=RS), feat)
l1 = LogisticRegression(penalty="l1", solver="liblinear", C=0.02, max_iter=3000, class_weight="balanced").fit(X_fit, y_fit)
coef = pd.Series(np.abs(l1.coef_[0]), feat)
rf = RandomForestClassifier(n_estimators=400, min_samples_leaf=5, random_state=RS, n_jobs=-1, class_weight="balanced").fit(X_fit, y_fit)
imp = pd.Series(rf.feature_importances_, feat)


def group_of(c):
    for g in CATS:
        if c.startswith(g + "_"):
            return g
    return "Bulan (sin+cos)" if c.startswith("Month_") else c


grp = pd.Series({c: group_of(c) for c in feat})
gs = pd.DataFrame({"MI": mi.groupby(grp).sum(), "L1": coef.groupby(grp).sum(), "RF": imp.groupby(grp).sum()})
TOP = 6
gv = pd.DataFrame({m: gs[m].rank(ascending=False) <= TOP for m in gs.columns})
gs["Vote"] = gv.sum(axis=1)
sel_vars = gs[gs["Vote"] >= 2].index.tolist()
selected = [c for c in feat if grp[c] in sel_vars]
R["var_scores"] = tbl(gs.sort_values(["Vote", "RF"], ascending=False).rename_axis("Variabel"))
R["selected_vars"] = sel_vars
R["selected_n"] = len(selected)

KD = 15
dv = pd.DataFrame({"MI": feat.isin(mi.nlargest(KD).index), "L1": feat.isin(coef[coef > 0].nlargest(KD).index), "RF": feat.isin(imp.nlargest(KD).index)}, index=feat).sum(axis=1)
sel_dummy = dv[dv >= 2].index.tolist()


def fit_eval(Xa, ya, Xb, yb, groups=None):
    m = LogisticRegression(max_iter=3000, class_weight="balanced").fit(Xa, ya)
    p = m.predict_proba(Xb)[:, 1]
    yhat = (p >= 0.5).astype(int)
    out = {"Fitur": int(Xa.shape[1]), "ROC_AUC": float(roc_auc_score(yb, p)), "PR_AUC": float(average_precision_score(yb, p)),
           "Precision": float(precision_score(yb, yhat)), "Recall": float(recall_score(yb, yhat)), "F1": float(f1_score(yb, yhat))}
    if groups is not None:
        rng = np.random.default_rng(RS)
        idx = list(pd.Series(np.arange(len(yb))).groupby(np.asarray(groups)).apply(lambda s: s.values))
        sc = []
        for _ in range(500):
            pick = np.concatenate([idx[i] for i in rng.integers(0, len(idx), len(idx))])
            sc.append(roc_auc_score(yb.values[pick], p[pick]))
        out["AUC_CI"] = [float(np.percentile(sc, 2.5)), float(np.percentile(sc, 97.5))]
    return out


P = PCA(n_components=k90, random_state=RS).fit(X_fit)
val_rows = [("Semua kandidat", fit_eval(X_fit, y_fit, X_val, y_val)), ("Seleksi per variabel", fit_eval(X_fit[selected], y_fit, X_val[selected], y_val)),
            ("Seleksi per dummy", fit_eval(X_fit[sel_dummy], y_fit, X_val[sel_dummy], y_val)), (f"PCA {k90} komponen", fit_eval(P.transform(X_fit), y_fit, P.transform(X_val), y_val))]

X_tr, X_te = prepare(train, test)
y_tr, y_te = train["Is_Loss"], test["Is_Loss"]
P2 = PCA(n_components=k90, random_state=RS).fit(X_tr)
test_rows = {"Semua kandidat": fit_eval(X_tr, y_tr, X_te, y_te, test["Order ID"]), "Seleksi per variabel": fit_eval(X_tr[selected], y_tr, X_te[selected], y_te, test["Order ID"]),
             "Seleksi per dummy": fit_eval(X_tr[sel_dummy], y_tr, X_te[sel_dummy], y_te, test["Order ID"]),
             f"PCA {k90} komponen": fit_eval(P2.transform(X_tr), y_tr, P2.transform(X_te), y_te, test["Order ID"])}
R["eval"] = [{"Set": n, "Val_AUC": v["ROC_AUC"], "Fitur": v["Fitur"], **{k: test_rows[n][k] for k in ("ROC_AUC", "AUC_CI", "PR_AUC", "Precision", "Recall", "F1")}} for n, v in val_rows]
R["eval_base_pr"] = float(y_te.mean())
R["sel_dummy_n"] = len(sel_dummy)
nosales = [c for c in selected if c not in ("Sales_Z", "Unit_Price_Z")]
R["eval_nosales"] = fit_eval(X_tr[nosales], y_tr, X_te[nosales], y_te)

R["audit"] = {"missing_train": int(X_tr[selected].isna().sum().sum()), "missing_test": int(X_te[selected].isna().sum().sum()), "inf": int(np.isinf(X_tr[selected].values).sum() + np.isinf(X_te[selected].values).sum()),
              "same_columns": list(X_tr[selected].columns) == list(X_te[selected].columns), "train_shape": list(X_tr[selected].shape), "test_shape": list(X_te[selected].shape),
              "split_overlap": R["split_overlap"]}
X_tr[selected].assign(Is_Loss=y_tr.values).to_csv(OUT / "train_final.csv", index=False)
X_te[selected].assign(Is_Loss=y_te.values).to_csv(OUT / "test_final.csv", index=False)
df.to_csv(OUT / "superstore_bersih.csv", index=False)

# %% 10. Visualisasi
LBL = {"Sales": "Sales", "Quantity": "Quantity", "Unit_Price": "Harga satuan", "Profit": "Profit", "Profit_Margin": "Margin",
       "Ship_Lead_Days": "Lama kirim", "Order_Lines": "Baris/order"}

# Histogram per tahun
fig, ax = plt.subplots(1, 3, figsize=(12, 3.6))
ax[0].hist(df["Profit"].clip(-200, 300), bins=50, color=BLUE, rwidth=0.92)
ax[0].set(title="Profit per baris", xlabel="USD (dipotong di -200 dan 300)", ylabel="Jumlah baris")
ax[0].axvline(0, color=MUTED, lw=0.8)
for fr, col, lab in [(y19, BLUE, "2019"), (y20, AQUA, "2020")]:
    ax[1].hist(fr["Sales_Log"], bins=np.linspace(0, 9.5, 36), color=col, alpha=0.55, label=lab, density=True)
    ax[2].hist(fr["Profit_Margin"].clip(-1.5, 1), bins=np.linspace(-1.5, 1, 36), color=col, alpha=0.55, label=lab, density=True)
ax[1].set(title="log(1 + Sales): bergeser di 2020", xlabel="log(1 + Sales)", ylabel="Kepadatan")
ax[2].set(title="Margin: menyempit di 2020", xlabel="Profit / Sales (dipotong di -150% dan 100%)")
for x_ in ax[1:]:
    x_.legend(frameon=False)
for x_ in ax:
    x_.grid(axis="y"); x_.set_axisbelow(True)
plt.tight_layout(); plt.savefig(FIG / "01_histogram.png"); plt.close()

# Tren bulanan: tiga panel, bukan banyak sumbu
mon = df.groupby(df["Order Date"].dt.to_period("M").dt.to_timestamp()).agg(Order=("Order ID", "nunique"), Sales=("Sales", "median"), Profit=("Profit", "median"))
fig, ax = plt.subplots(3, 1, figsize=(10, 4.7), sharex=True)
for x_, c, title in zip(ax, ["Sales", "Profit", "Order"], ["Median Sales per baris (USD): melompat tepat di Januari 2020", "Median Profit per baris (USD): tetap stabil", "Jumlah order per bulan: puncak tiap akhir tahun"]):
    x_.plot(mon.index, mon[c], color=BLUE, lw=2)
    x_.axvline(pd.Timestamp("2020-01-01"), color=ORANGE, lw=1, ls="--")
    x_.set_title(title); x_.grid(axis="y"); x_.set_axisbelow(True); x_.set_ylim(bottom=0)
plt.tight_layout(); plt.savefig(FIG / "02_tren_bulanan.png"); plt.close()
R["order_peak"] = {str(k.date())[:7]: int(v) for k, v in mon["Order"].nlargest(3).items()}

# Bar profit per sub-kategori
s = df.groupby("Sub-Category")["Profit"].sum().sort_values()
fig, ax = plt.subplots(figsize=(9, 5))
ax.barh(s.index, s.values, color=[ORANGE if v < 0 else BLUE for v in s.values], height=0.72)
ax.axvline(0, color=MUTED, lw=0.8)
for y_, v in enumerate(s.values):
    ax.text(v + (350 if v >= 0 else -350), y_, f"{v:,.0f}".replace(",", "."), va="center", ha="left" if v >= 0 else "right", fontsize=10, color=MUTED)
ax.set(title="Total profit per sub-kategori, 2019-2020", xlabel="Total profit (USD)")
ax.set_xlim(s.min() * 1.7, s.max() * 1.18)
ax.grid(axis="x"); ax.set_axisbelow(True)
plt.savefig(FIG / "03_bar_subkategori.png"); plt.close()

# Bar rugi per wilayah
stp = st[st["Baris"] >= 30].sort_values("Loss_Rate").tail(12)
rg = group_table("Region").sort_values("Loss_Rate")
fig, ax = plt.subplots(1, 2, figsize=(12, 4.2), gridspec_kw={"width_ratios": [1, 1.4]})
ax[0].barh(rg.index, rg["Loss_Rate"] * 100, color=ORANGE, height=0.6)
for i, v in enumerate(rg["Loss_Rate"] * 100):
    ax[0].text(v + 0.5, i, f"{v:.1f}%", va="center", fontsize=10, color=MUTED)
ax[0].set(title="Baris rugi per region", xlabel="Persentase baris rugi"); ax[0].set_xlim(0, 38)
ax[1].barh(stp.index, stp["Loss_Rate"] * 100, color=ORANGE, height=0.7)
for i, (v, n) in enumerate(zip(stp["Loss_Rate"] * 100, stp["Baris"])):
    ax[1].text(v + 0.7, i, f"{v:.0f}%  (n={n})", va="center", fontsize=10, color=MUTED)
ax[1].set(title="12 negara bagian dengan baris rugi tertinggi (n ≥ 30)", xlabel="Persentase baris rugi"); ax[1].set_xlim(0, 68)
for x_ in ax:
    x_.grid(axis="x"); x_.set_axisbelow(True)
plt.tight_layout(); plt.savefig(FIG / "04_bar_rugi_wilayah.png"); plt.close()

# Heatmap korelasi per tahun
cv = ["Sales", "Quantity", "Unit_Price", "Profit", "Profit_Margin", "Ship_Lead_Days", "Order_Lines"]
names = [LBL[c] for c in cv]
fig, ax = plt.subplots(1, 2, figsize=(12.5, 5.2))
for k_, (x_, fr, title) in enumerate(zip(ax, [y19, y20], ["2019", "2020"])):
    cm = fr[cv].corr("spearman")
    im = x_.imshow(cm, cmap=DIV, vmin=-1, vmax=1)
    x_.set_xticks(range(len(cv)), names, rotation=40, ha="right"); x_.set_yticks(range(len(cv)), names if k_ == 0 else [""] * len(cv))
    for i in range(len(cv)):
        for j in range(len(cv)):
            v = cm.iloc[i, j]
            x_.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=9.5, color="white" if abs(v) > 0.7 else INK)
    for sp_ in x_.spines.values():
        sp_.set_visible(False)
    x_.set_title(f"Korelasi Spearman {title}")
fig.colorbar(im, ax=ax, shrink=0.8, label="rho")
plt.savefig(FIG / "05_heatmap_korelasi.png"); plt.close()
R["corr_sales_profit"] = {"2019": float(y19[["Sales", "Profit"]].corr("spearman").iloc[0, 1]), "2020": float(y20[["Sales", "Profit"]].corr("spearman").iloc[0, 1])}

# Heatmap rugi region x kategori
pv = df.pivot_table(index="Region", columns="Category", values="Is_Loss") * 100
pv = pv.loc[["West", "South", "East", "Central"], ["Office Supplies", "Technology", "Furniture"]]
fig, ax = plt.subplots(figsize=(8.6, 3.7))
im = ax.imshow(pv, cmap=SEQ, vmin=0, vmax=pv.values.max(), aspect="auto")
ax.set_xticks(range(3), pv.columns); ax.set_yticks(range(4), pv.index)
for i in range(4):
    for j in range(3):
        v = pv.iloc[i, j]
        ax.text(j, i, f"{v:.1f}%", ha="center", va="center", color="white" if v > pv.values.max() * 0.55 else INK)
for sp_ in ax.spines.values():
    sp_.set_visible(False)
ax.set_title("Persentase baris rugi: region x kategori")
fig.colorbar(im, ax=ax, shrink=0.85, label="% baris rugi")
plt.savefig(FIG / "06_heatmap_rugi.png"); plt.close()

json.dump(R, open(OUT / "results.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("Selesai. Baris bersih:", df.shape, "| variabel terpilih:", sel_vars)
