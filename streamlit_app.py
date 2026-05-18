"""
Schaakopening Essenties — Interactief FP&A Dashboard
Haalt data live op uit e-Boekhouden.nl (gecached per uur).
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from zeep import Client
from zeep.xsd.const import SkipValue as ZeepSkip
from datetime import datetime, date

st.set_page_config(
    page_title="Schaakopening Essenties — Dashboard",
    page_icon="♟️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CONSTANTEN ──────────────────────────────────────────────────────────────
WSDL      = "https://soap.e-boekhouden.nl/soap.asmx?wsdl"
DATUM_VAN = date(2024, 1, 1)
DATUM_TOT = date(2026, 12, 31)

REKENING_NAMEN = {
    8000: "Omzet premium",        8010: "Omzet losse producten",
    8020: "Omzet hostingbijdragen", 7000: "Inkopen",
    4335: "Afschr. Inventarissen", 4340: "Afschr. Hardware",
    4500: "Contributies/abonnementen", 4510: "Reclame en advertenties",
    4520: "Representatiekosten",   4530: "Reis- en verblijfkosten",
    4540: "Relatiegeschenken",     4550: "Bankkosten",
    4555: "Mollie kosten",         4560: "ICS garantstelling",
    4590: "Overige verkoopkosten", 4600: "Kilometervergoeding",
    4700: "Kantoorbenodigdheden",  4720: "Software abonnementen",
    4740: "Drukwerk/porti/vrachten", 4750: "Telefoon en internet",
    4755: "Ontwikkelingskosten",   4760: "Hostingkosten",
    4790: "Overige kantoorkosten", 4794: "Marketingkosten",
    4810: "Accountants/administratie", 4850: "Cursussen/seminars",
    4860: "Vakliteratuur",         4900: "Betalingsverschillen",
    4950: "Oninbare vorderingen",  9000: "Rente spaarrekening",
}

OMZET_RK      = [8000, 8010, 8020]
COS_RK        = [7000]
MARKETING_RK  = [4510, 4520, 4540, 4590, 4794]
AFSCHR_RK     = [4335, 4340]
ONTWIKKEL_RK  = [4755]
REIS_RK       = [4530, 4600]
KANTOOR_RK    = [4500, 4550, 4555, 4560, 4700, 4720, 4740, 4750, 4760, 4790, 4810]
OVERIG_RK     = [4850, 4860, 4900, 4950]
FINANCIEEL_RK = [9000]
PL_CODES      = (OMZET_RK + COS_RK + MARKETING_RK + AFSCHR_RK + ONTWIKKEL_RK
                 + REIS_RK + KANTOOR_RK + OVERIG_RK + FINANCIEEL_RK)
OPEX_C        = MARKETING_RK + KANTOOR_RK + ONTWIKKEL_RK + REIS_RK + AFSCHR_RK + OVERIG_RK
EBIT_C        = OMZET_RK + COS_RK + OPEX_C
NETTO_C       = EBIT_C + FINANCIEEL_RK

MAANDEN_NL    = ["Jan","Feb","Mrt","Apr","Mei","Jun","Jul","Aug","Sep","Okt","Nov","Dec"]
NAVY          = "#1F3864"
BLUE          = "#2E75B6"
RED           = "#C00000"
GREEN         = "#375623"

# ─── STIJL ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background:#F5F7FA; }
[data-testid="stSidebar"]          { background:#1F3864; }
[data-testid="stSidebar"] * { color: white !important; }
[data-testid="stSidebar"] .stSelectbox label { color: #BDD7EE !important; }
.kpi { background:white; border-radius:8px; padding:18px 20px 14px;
       border-top:4px solid #2E75B6; box-shadow:0 1px 6px rgba(0,0,0,.08); }
.kpi-label { font-size:10px; color:#888; text-transform:uppercase;
             letter-spacing:.8px; font-weight:700; margin-bottom:4px; }
.kpi-value { font-size:26px; font-weight:800; color:#1F3864; line-height:1.1; }
.kpi-value.red { color:#C00000; }
.kpi-sub   { font-size:11px; margin-top:6px; min-height:16px; }
.grow-pos  { color:#375623; font-weight:700; }
.grow-neg  { color:#C00000; font-weight:700; }
.sec-hdr   { background:#1F3864; color:white; padding:7px 14px; border-radius:5px;
             font-size:12px; font-weight:700; letter-spacing:.4px;
             margin:20px 0 10px; }
</style>
""", unsafe_allow_html=True)

# ─── DATA OPHALEN (gecached, 1 uur TTL) ──────────────────────────────────────
def _zget(obj, key, default=None):
    try:
        return obj[key]
    except (KeyError, TypeError):
        return default

@st.cache_data(ttl=3600, show_spinner="Data ophalen uit e-Boekhouden…")
def load_data():
    client = Client(WSDL)
    res = client.service.OpenSession(
        Username=st.secrets["USERNAME"],
        SecurityCode1=st.secrets["API_KEY"],
        SecurityCode2=st.secrets["SECURITY_CODE_2"],
    )
    if res["ErrorMsg"] and res["ErrorMsg"]["LastErrorCode"]:
        raise RuntimeError(res["ErrorMsg"]["LastErrorDescription"])
    sid = res["SessionID"]

    rows = []
    try:
        nr_van = 0
        while True:
            r = client.service.GetMutaties(
                SessionID=sid,
                SecurityCode2=st.secrets["SECURITY_CODE_2"],
                cFilter={
                    "MutatieNr":     ZeepSkip,
                    "MutatieNrVan":  nr_van if nr_van > 0 else ZeepSkip,
                    "MutatieNrTm":   ZeepSkip,
                    "Factuurnummer": ZeepSkip,
                    "DatumVan":      datetime(DATUM_VAN.year, DATUM_VAN.month, DATUM_VAN.day),
                    "DatumTm":       datetime(DATUM_TOT.year, DATUM_TOT.month, DATUM_TOT.day),
                }
            )
            mutaties = []
            if r["Mutaties"] and r["Mutaties"]["cMutatieList"]:
                mutaties = r["Mutaties"]["cMutatieList"]

            for m in mutaties:
                regels = []
                if m["MutatieRegels"] and m["MutatieRegels"]["cMutatieListRegel"]:
                    regels = m["MutatieRegels"]["cMutatieListRegel"]
                tg_codes = set()
                for regel in regels:
                    try:
                        tg_codes.add(int(str(regel["TegenrekeningCode"] or "").strip()))
                    except (ValueError, TypeError):
                        pass
                for regel in regels:
                    try:
                        gb = int(str(regel["TegenrekeningCode"] or "").strip())
                    except (ValueError, TypeError):
                        gb = None
                    rows.append({
                        "MutatieNr":     _zget(m, "MutatieNr"),
                        "Soort":         str(_zget(m, "Soort") or ""),
                        "Datum":         _zget(m, "Datum"),
                        "Omschrijving":  str(_zget(m, "Omschrijving") or ""),
                        "GrootboekCode": gb,
                        "BedragExclBTW": float(_zget(regel, "BedragExclBTW") or 0),
                        "Kant":          "T",
                    })
                try:
                    rek = int(str(_zget(m, "Rekening") or "").strip())
                except (ValueError, TypeError):
                    rek = None
                if rek in PL_CODES and rek not in tg_codes:
                    som = sum(float(_zget(rg, "BedragExclBTW") or 0) for rg in regels)
                    rows.append({
                        "MutatieNr":     _zget(m, "MutatieNr"),
                        "Soort":         str(_zget(m, "Soort") or ""),
                        "Datum":         _zget(m, "Datum"),
                        "Omschrijving":  str(_zget(m, "Omschrijving") or ""),
                        "GrootboekCode": rek,
                        "BedragExclBTW": -som,
                        "Kant":          "R",
                    })
            if len(mutaties) < 500:
                break
            nr_van = max(m["MutatieNr"] for m in mutaties) + 1
    finally:
        try:
            client.service.CloseSession(SessionID=sid)
        except Exception:
            pass

    df = pd.DataFrame(rows)
    df["Datum"]  = pd.to_datetime(df["Datum"])
    df["Jaar"]   = df["Datum"].dt.year
    df["Maand"]  = df["Datum"].dt.month
    df["RekeningNaam"] = (df["GrootboekCode"].map(REKENING_NAMEN)
                          .fillna(df["GrootboekCode"].astype(str)))

    def cat(code):
        if code in OMZET_RK:      return "Omzet"
        if code in COS_RK:        return "Inkopen"
        if code in MARKETING_RK:  return "Marketing"
        if code in AFSCHR_RK:     return "Afschrijvingen"
        if code in ONTWIKKEL_RK:  return "Ontwikkeling"
        if code in REIS_RK:       return "Reis & Verblijf"
        if code in KANTOOR_RK:    return "Kantoor & Algemeen"
        if code in OVERIG_RK:     return "Overige kosten"
        if code in FINANCIEEL_RK: return "Financieel"
        return "Overig"

    df["Categorie"] = df["GrootboekCode"].apply(
        lambda x: cat(x) if pd.notna(x) else "Onbekend")

    NEGATE = {"GeldUitgegeven", "FactuurOntvangen"}
    df["PLBedrag"] = df["BedragExclBTW"]
    mask = (df["Kant"] == "T") & df["Soort"].isin(NEGATE)
    df.loc[mask, "PLBedrag"] = -df.loc[mask, "BedragExclBTW"]
    return df

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def tot(df, jaar, codes):
    sub = df[df["GrootboekCode"].isin(codes)]
    if jaar != "Alle jaren":
        sub = sub[sub["Jaar"] == jaar]
    return sub["PLBedrag"].sum()

def eur(v):
    if v is None: return "—"
    s = "-" if v < 0 else ""
    return f"{s}€ {abs(v):,.0f}".replace(",", ".")

def pct(v):
    return f"{v*100:.1f}%" if v is not None else "—"

def groei_html(v, vp, label):
    if vp is None or vp == 0: return ""
    g = (v - vp) / abs(vp)
    arrow = "▲" if g >= 0 else "▼"
    cls   = "grow-pos" if g >= 0 else "grow-neg"
    return f'<span class="{cls}">{arrow} {abs(g)*100:.1f}%</span> vs {label}'

# ─── HEADER ──────────────────────────────────────────────────────────────────
col_t, col_ts = st.columns([3, 1])
col_t.markdown(f"## ♟️ &nbsp;Schaakopening Essenties")
col_ts.markdown(
    f"<div style='text-align:right;color:#888;font-size:12px;padding-top:18px'>"
    f"Vernieuwd: {datetime.now().strftime('%d %b %Y %H:%M')}</div>",
    unsafe_allow_html=True)

# ─── SIDEBAR ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ♟️ Filters")
    st.markdown("---")
    jaar_keuze = st.selectbox("Jaar", [2026, 2025, 2024], index=0,
                              help="Selecteer het jaar voor de KPI-tiles")
    vergelijk  = st.selectbox("Vergelijk met",
                              [j for j in [2025, 2024] if j != jaar_keuze] + ["—"],
                              index=0)
    vergelijk  = None if vergelijk == "—" else vergelijk
    st.markdown("---")
    if st.button("🔄 Data vernieuwen", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("Data wordt elk uur automatisch vernieuwd.")

# ─── DATA LADEN ──────────────────────────────────────────────────────────────
try:
    df = load_data()
except Exception as e:
    st.error(f"❌ Verbindingsfout: {e}")
    st.stop()

# ─── KPI TILES ───────────────────────────────────────────────────────────────
omzet = tot(df, jaar_keuze, OMZET_RK)
ebit  = tot(df, jaar_keuze, EBIT_C)
netto = tot(df, jaar_keuze, NETTO_C)
nm    = netto / omzet if omzet else None

omzet_v = tot(df, vergelijk, OMZET_RK) if vergelijk else None
ebit_v  = tot(df, vergelijk, EBIT_C)   if vergelijk else None
netto_v = tot(df, vergelijk, NETTO_C)  if vergelijk else None
vl      = str(vergelijk) if vergelijk else ""

def kpi_html(label, value, prev=None, comp_label="", is_pct=False):
    val_str = pct(value) if is_pct else eur(value)
    neg     = value is not None and value < 0
    sub     = groei_html(value, prev, comp_label) if not is_pct else "&nbsp;"
    return (f'<div class="kpi"><div class="kpi-label">{label}</div>'
            f'<div class="kpi-value{"  red" if neg else ""}">{val_str}</div>'
            f'<div class="kpi-sub">{sub}</div></div>')

k1, k2, k3, k4 = st.columns(4)
k1.markdown(kpi_html("Omzet",          omzet, omzet_v, vl), unsafe_allow_html=True)
k2.markdown(kpi_html("EBIT",           ebit,  ebit_v,  vl), unsafe_allow_html=True)
k3.markdown(kpi_html("Nettoresultaat", netto, netto_v, vl), unsafe_allow_html=True)
k4.markdown(kpi_html("Nettomarge %",   nm,    is_pct=True), unsafe_allow_html=True)

# ─── GRAFIEKEN ───────────────────────────────────────────────────────────────
st.markdown('<div class="sec-hdr">GRAFIEKEN</div>', unsafe_allow_html=True)
g1, g2 = st.columns(2)

# Grafiek 1: Omzet per maand per jaar
with g1:
    st.markdown("**Omzet per maand**")
    maand_rows = []
    for j in [2024, 2025, 2026]:
        for m in range(1, 13):
            v = df[(df["Jaar"]==j) & (df["Maand"]==m) &
                   df["GrootboekCode"].isin(OMZET_RK)]["PLBedrag"].sum()
            maand_rows.append({"Jaar": str(j), "Maand": MAANDEN_NL[m-1],
                                "MaandNr": m, "Omzet": v if v != 0 else None})
    df_m = pd.DataFrame(maand_rows).dropna(subset=["Omzet"])
    if not df_m.empty:
        fig1 = px.bar(df_m, x="Maand", y="Omzet", color="Jaar", barmode="group",
                      color_discrete_map={"2024":"#9DC3E6","2025":"#2E75B6","2026":"#1F3864"},
                      category_orders={"Maand": MAANDEN_NL})
        fig1.update_layout(
            plot_bgcolor="white", paper_bgcolor="white", font_family="Arial",
            margin=dict(t=10, b=30, l=10, r=10), height=300,
            yaxis=dict(tickprefix="€", gridcolor="#EFEFEF", zeroline=True,
                       zerolinecolor="#CCCCCC"),
            xaxis=dict(gridcolor="#EFEFEF"),
            legend=dict(orientation="h", yanchor="bottom", y=1.01,
                        xanchor="right", x=1, title=""),
        )
        st.plotly_chart(fig1, use_container_width=True)

# Grafiek 2: Kosten per jaar gestapeld
with g2:
    st.markdown("**Operationele kosten per jaar**")
    cost_cats = [
        ("Marketing",       MARKETING_RK),
        ("Kantoor & Alg.",  KANTOOR_RK),
        ("Ontwikkeling",    ONTWIKKEL_RK),
        ("Reis & Verblijf", REIS_RK),
        ("Afschrijvingen",  AFSCHR_RK),
        ("Overige kosten",  OVERIG_RK),
    ]
    cost_rows = []
    for j in [2024, 2025, 2026]:
        for cat_name, codes in cost_cats:
            v = -tot(df, j, codes)
            if v > 0.01:
                cost_rows.append({"Jaar": str(j), "Categorie": cat_name, "Kosten": v})
    df_c = pd.DataFrame(cost_rows)
    if not df_c.empty:
        fig2 = px.bar(df_c, x="Jaar", y="Kosten", color="Categorie", barmode="stack",
                      color_discrete_sequence=[
                          "#1F3864","#2E75B6","#4472C4","#5B9BD5","#9DC3E6","#D6E4F0"])
        fig2.update_layout(
            plot_bgcolor="white", paper_bgcolor="white", font_family="Arial",
            margin=dict(t=10, b=30, l=10, r=10), height=300,
            yaxis=dict(tickprefix="€", gridcolor="#EFEFEF", zeroline=True,
                       zerolinecolor="#CCCCCC"),
            legend=dict(orientation="h", yanchor="bottom", y=1.01,
                        xanchor="right", x=1, title=""),
        )
        st.plotly_chart(fig2, use_container_width=True)

# ─── RESULTATENREKENING ───────────────────────────────────────────────────────
st.markdown('<div class="sec-hdr">RESULTATENREKENING</div>', unsafe_allow_html=True)

pl_secties = [
    ("Omzet",               OMZET_RK,          False),
    ("Kostprijs (COS)",     COS_RK,             False),
    ("Brutowinst",          OMZET_RK + COS_RK,  True),
    ("  Marketing",         MARKETING_RK,       False),
    ("  Kantoor & Alg.",    KANTOOR_RK,         False),
    ("  Ontwikkeling",      ONTWIKKEL_RK,       False),
    ("  Reis & Verblijf",   REIS_RK,            False),
    ("  Afschrijvingen",    AFSCHR_RK,          False),
    ("  Overige kosten",    OVERIG_RK,          False),
    ("Totaal OPEX",         OPEX_C,             True),
    ("EBIT",                EBIT_C,             True),
    ("Financieel",          FINANCIEEL_RK,      False),
    ("Nettoresultaat",      NETTO_C,            True),
]

pl_rows = []
for label, codes, is_tot in pl_secties:
    row = {"": label}
    for j in [2024, 2025, 2026]:
        v = tot(df, j, codes)
        row[str(j)] = round(v, 2) if round(v, 2) != 0 else None
    row["_bold"] = is_tot
    pl_rows.append(row)

df_pl = pd.DataFrame(pl_rows)
bold_idx = df_pl[df_pl["_bold"]].index.tolist()
df_pl = df_pl.drop(columns=["_bold"]).set_index("")

def style_pl(df):
    styles = pd.DataFrame("", index=df.index, columns=df.columns)
    for idx in bold_idx:
        if idx < len(df):
            styles.iloc[idx] = "font-weight:bold; background-color:#EEF3F9"
    for col in df.columns:
        for i, v in enumerate(df[col]):
            if isinstance(v, float) and v < 0:
                styles.iloc[i][col] += "; color:#C00000"
    return styles

st.dataframe(
    df_pl.style
         .apply(lambda _: style_pl(df_pl), axis=None)
         .format(lambda v: eur(v) if isinstance(v, float) else ("—" if v is None else v)),
    use_container_width=True,
    height=460,
)

# ─── DETAIL BOEKINGEN ────────────────────────────────────────────────────────
with st.expander("📋 Boekingsdetail bekijken"):
    col_f1, col_f2 = st.columns(2)
    jaren_filter = col_f1.multiselect("Jaar", [2024, 2025, 2026],
                                      default=[jaar_keuze])
    cat_filter   = col_f2.multiselect("Categorie",
                                      sorted(df["Categorie"].unique()),
                                      default=sorted(df["Categorie"].unique()))
    df_detail = df[
        df["Jaar"].isin(jaren_filter) &
        df["Categorie"].isin(cat_filter) &
        df["GrootboekCode"].isin(PL_CODES)
    ].copy()
    df_detail["Datum"]    = df_detail["Datum"].dt.strftime("%d-%m-%Y")
    df_detail["PLBedrag"] = df_detail["PLBedrag"].round(2)
    st.dataframe(
        df_detail[["Datum","Soort","GrootboekCode","RekeningNaam",
                   "Categorie","Omschrijving","PLBedrag"]],
        use_container_width=True, height=320,
    )
    st.caption(f"{len(df_detail)} boekingen")
