"""
Schaakopening Essenties — Interactief FP&A Dashboard
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from zeep import Client
from zeep.xsd.const import SkipValue as ZeepSkip
from datetime import datetime, date

st.set_page_config(
    page_title="Schaakopening Essenties",
    page_icon="♟️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CONSTANTEN ──────────────────────────────────────────────────────────────
WSDL      = "https://soap.e-boekhouden.nl/soap.asmx?wsdl"
DATUM_VAN = date(2024, 1, 1)
DATUM_TOT = date(2026, 12, 31)

REKENING_NAMEN = {
    8000:"Omzet premium", 8010:"Omzet losse producten", 8020:"Omzet hostingbijdragen",
    7000:"Inkopen", 4335:"Afschr. Inventarissen", 4340:"Afschr. Hardware",
    4500:"Contributies/abonnementen", 4510:"Reclame en advertenties",
    4520:"Representatiekosten", 4530:"Reis- en verblijfkosten",
    4540:"Relatiegeschenken", 4550:"Bankkosten", 4555:"Mollie kosten",
    4560:"ICS garantstelling", 4590:"Overige verkoopkosten",
    4600:"Kilometervergoeding", 4700:"Kantoorbenodigdheden",
    4720:"Software abonnementen", 4740:"Drukwerk/porti/vrachten",
    4750:"Telefoon en internet", 4755:"Ontwikkelingskosten",
    4760:"Hostingkosten", 4790:"Overige kantoorkosten",
    4794:"Marketingkosten", 4810:"Accountants/administratie",
    4850:"Cursussen/seminars", 4860:"Vakliteratuur",
    4900:"Betalingsverschillen", 4950:"Oninbare vorderingen",
    9000:"Rente spaarrekening",
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

# ─── CSS ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background:#F0F2F6; }
[data-testid="stSidebar"]          { background:#1F3864 !important; }
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] div  { color:#FFFFFF !important; }
[data-testid="stSidebar"] .stButton>button {
    background:#2E75B6; color:white; border:none;
    width:100%; border-radius:6px; padding:8px;
}
.kpi {
    background:white; border-radius:10px; padding:20px 22px 16px;
    box-shadow:0 2px 8px rgba(0,0,0,.09); height:110px;
}
.kpi-label { font-size:10px; color:#999; text-transform:uppercase;
             letter-spacing:1px; font-weight:700; }
.kpi-value { font-size:28px; font-weight:800; line-height:1.15; margin:4px 0 6px; }
.kpi-sub   { font-size:11px; font-weight:600; }
.grow-pos  { color:#375623; }
.grow-neg  { color:#C00000; }
.pl-table  { width:100%; border-collapse:collapse; font-family:Arial,sans-serif;
             font-size:13px; margin-top:4px; }
.pl-table th { background:#1F3864; color:white; padding:9px 14px;
               text-align:right; font-weight:700; font-size:11px;
               letter-spacing:.5px; text-transform:uppercase; }
.pl-table th:first-child { text-align:left; }
.pl-table td { padding:7px 14px; border-bottom:1px solid #EEF0F3; }
.pl-table tr:hover td { background:#F7F9FC; }
.pl-sec  { background:#2E75B6 !important; color:white !important;
           font-weight:700; font-size:12px; letter-spacing:.4px; }
.pl-sec td { color:white !important; border-bottom:none !important; }
.pl-sub  { background:#EEF3FA !important; font-weight:700; }
.pl-tot  { background:#1F3864 !important; }
.pl-tot td { color:white !important; font-weight:800;
             font-size:14px; border-bottom:none !important; }
.pl-neg  { color:#C00000 !important; }
.pl-ind  { padding-left:28px !important; color:#444; }
</style>
""", unsafe_allow_html=True)

# ─── DATA ────────────────────────────────────────────────────────────────────
def _zget(obj, key, default=None):
    try:    return obj[key]
    except: return default

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
                    "MutatieNr": ZeepSkip, "MutatieNrVan": nr_van if nr_van > 0 else ZeepSkip,
                    "MutatieNrTm": ZeepSkip, "Factuurnummer": ZeepSkip,
                    "DatumVan": datetime(DATUM_VAN.year, DATUM_VAN.month, DATUM_VAN.day),
                    "DatumTm":  datetime(DATUM_TOT.year, DATUM_TOT.month, DATUM_TOT.day),
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
                for rg in regels:
                    try: tg_codes.add(int(str(rg["TegenrekeningCode"] or "").strip()))
                    except: pass
                for rg in regels:
                    try:    gb = int(str(rg["TegenrekeningCode"] or "").strip())
                    except: gb = None
                    rows.append({
                        "MutatieNr": _zget(m,"MutatieNr"), "Soort": str(_zget(m,"Soort") or ""),
                        "Datum": _zget(m,"Datum"), "Omschrijving": str(_zget(m,"Omschrijving") or ""),
                        "GrootboekCode": gb,
                        "BedragExclBTW": float(_zget(rg,"BedragExclBTW") or 0), "Kant": "T",
                    })
                try:    rek = int(str(_zget(m,"Rekening") or "").strip())
                except: rek = None
                if rek in PL_CODES and rek not in tg_codes:
                    som = sum(float(_zget(rg,"BedragExclBTW") or 0) for rg in regels)
                    rows.append({
                        "MutatieNr": _zget(m,"MutatieNr"), "Soort": str(_zget(m,"Soort") or ""),
                        "Datum": _zget(m,"Datum"), "Omschrijving": str(_zget(m,"Omschrijving") or ""),
                        "GrootboekCode": rek, "BedragExclBTW": -som, "Kant": "R",
                    })
            if len(mutaties) < 500: break
            nr_van = max(m["MutatieNr"] for m in mutaties) + 1
    finally:
        try: client.service.CloseSession(SessionID=sid)
        except: pass

    df = pd.DataFrame(rows)
    df["Datum"]  = pd.to_datetime(df["Datum"])
    df["Jaar"]   = df["Datum"].dt.year
    df["Maand"]  = df["Datum"].dt.month
    df["RekeningNaam"] = df["GrootboekCode"].map(REKENING_NAMEN).fillna(df["GrootboekCode"].astype(str))

    def cat(c):
        if c in OMZET_RK:      return "Omzet"
        if c in COS_RK:        return "Inkopen"
        if c in MARKETING_RK:  return "Marketing"
        if c in AFSCHR_RK:     return "Afschrijvingen"
        if c in ONTWIKKEL_RK:  return "Ontwikkeling"
        if c in REIS_RK:       return "Reis & Verblijf"
        if c in KANTOOR_RK:    return "Kantoor & Algemeen"
        if c in OVERIG_RK:     return "Overige kosten"
        if c in FINANCIEEL_RK: return "Financieel"
        return "Overig"
    df["Categorie"] = df["GrootboekCode"].apply(lambda x: cat(x) if pd.notna(x) else "Onbekend")

    NEGATE = {"GeldUitgegeven","FactuurOntvangen"}
    df["PLBedrag"] = df["BedragExclBTW"]
    mask = (df["Kant"] == "T") & df["Soort"].isin(NEGATE)
    df.loc[mask,"PLBedrag"] = -df.loc[mask,"BedragExclBTW"]
    return df

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def tot(df, jaar, codes):
    sub = df[df["GrootboekCode"].isin(codes)]
    if jaar != "Alle": sub = sub[sub["Jaar"] == jaar]
    return sub["PLBedrag"].sum()

def eur(v, dash=True):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—" if dash else ""
    if round(v, 0) == 0: return "—" if dash else "–"
    s = "-" if v < 0 else ""
    return f"{s}€ {abs(v):,.0f}".replace(",", ".")

def groei(v, vp):
    if vp is None or vp == 0: return ""
    g = (v - vp) / abs(vp)
    arrow, cls = ("▲","grow-pos") if g >= 0 else ("▼","grow-neg")
    return f'<span class="{cls}">{arrow} {abs(g)*100:.1f}%</span>'

# ─── SIDEBAR ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ♟️ Schaakopening")
    st.markdown("---")
    jaar_keuze = st.selectbox("Jaar (KPI's)", [2026, 2025, 2024])
    opties_vgl = [j for j in [2025, 2024] if j != jaar_keuze]
    vergelijk  = st.selectbox("Vergelijk met", opties_vgl + ["—"])
    vergelijk  = None if vergelijk == "—" else int(vergelijk)
    st.markdown("---")
    if st.button("🔄 Data vernieuwen"):
        st.cache_data.clear(); st.rerun()
    st.caption(f"Vernieuwd: {datetime.now().strftime('%d %b %Y %H:%M')}")
    st.caption("Automatisch elk uur.")

# ─── DATA LADEN ──────────────────────────────────────────────────────────────
try:
    df = load_data()
except Exception as e:
    st.error(f"❌ Verbindingsfout met e-Boekhouden: {e}")
    st.stop()

# ─── HEADER ──────────────────────────────────────────────────────────────────
st.markdown(
    f"<h2 style='color:#1F3864;margin-bottom:2px'>♟️ &nbsp;Schaakopening Essenties</h2>"
    f"<p style='color:#999;font-size:12px;margin-top:0'>Financial Dashboard &nbsp;|&nbsp; "
    f"Bron: e-Boekhouden.nl</p>",
    unsafe_allow_html=True)

# ─── KPI TILES ───────────────────────────────────────────────────────────────
omzet = tot(df, jaar_keuze, OMZET_RK)
ebit  = tot(df, jaar_keuze, EBIT_C)
netto = tot(df, jaar_keuze, NETTO_C)
nm    = netto / omzet if omzet else None

omzet_v = tot(df, vergelijk, OMZET_RK) if vergelijk else None
ebit_v  = tot(df, vergelijk, EBIT_C)   if vergelijk else None
netto_v = tot(df, vergelijk, NETTO_C)  if vergelijk else None
vl      = str(vergelijk) if vergelijk else ""

def kpi_tile(label, value, prev, color, suffix="", is_pct=False):
    val_str = (f"{value*100:.1f}%" if is_pct and value is not None
               else eur(value, dash=False))
    neg   = value is not None and value < 0
    vcol  = "#C00000" if neg else "#1F3864"
    sub   = groei(value, prev) + (f"&nbsp;vs {vl}" if prev is not None else "")
    return (f'<div class="kpi" style="border-top:5px solid {color}">'
            f'<div class="kpi-label">{label}</div>'
            f'<div class="kpi-value" style="color:{vcol}">{val_str}{suffix}</div>'
            f'<div class="kpi-sub">{sub or "&nbsp;"}</div></div>')

k1, k2, k3, k4 = st.columns(4)
k1.markdown(kpi_tile("Omzet",          omzet, omzet_v, "#2E75B6"), unsafe_allow_html=True)
k2.markdown(kpi_tile("EBIT",           ebit,  ebit_v,  "#1F3864"), unsafe_allow_html=True)
k3.markdown(kpi_tile("Nettoresultaat", netto, netto_v,
                     "#375623" if netto >= 0 else "#C00000"),       unsafe_allow_html=True)
k4.markdown(kpi_tile("Nettomarge %",   nm,    None,    "#C55A11", is_pct=True), unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ─── GRAFIEKEN ───────────────────────────────────────────────────────────────
g1, g2 = st.columns(2)

CHART_COLORS = {"2024": "#9DC3E6", "2025": "#2E75B6", "2026": "#1F3864"}
CHART_LAYOUT = dict(
    plot_bgcolor="white", paper_bgcolor="white", font_family="Arial",
    margin=dict(t=40, b=20, l=10, r=10), height=320,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, title=""),
    yaxis=dict(gridcolor="#EFEFEF", tickprefix="€ ", zeroline=True, zerolinecolor="#CCCCCC"),
    xaxis=dict(gridcolor="rgba(0,0,0,0)"),
)

# Grafiek 1: Omzet per maand — lijnen per jaar
with g1:
    fig1 = go.Figure()
    for jaar in [2024, 2025, 2026]:
        y_vals = [
            df[(df["Jaar"]==jaar) & (df["Maand"]==m) &
               df["GrootboekCode"].isin(OMZET_RK)]["PLBedrag"].sum()
            for m in range(1, 13)
        ]
        fig1.add_trace(go.Scatter(
            x=MAANDEN_NL, y=y_vals, name=str(jaar), mode="lines+markers",
            line=dict(color=CHART_COLORS[str(jaar)], width=2.5),
            marker=dict(size=6),
            hovertemplate="%{x}: €%{y:,.0f}<extra>" + str(jaar) + "</extra>",
        ))
    fig1.update_layout(**CHART_LAYOUT, title=dict(
        text="Omzet per Maand", font=dict(size=13, color="#1F3864"), x=0))
    st.plotly_chart(fig1, use_container_width=True)

# Grafiek 2: OPEX per jaar — gestapelde balken
with g2:
    cost_cats = [
        ("Marketing",       MARKETING_RK),
        ("Kantoor & Alg.",  KANTOOR_RK),
        ("Ontwikkeling",    ONTWIKKEL_RK),
        ("Reis & Verblijf", REIS_RK),
        ("Afschrijvingen",  AFSCHR_RK),
        ("Overige kosten",  OVERIG_RK),
    ]
    cat_colors = ["#1F3864","#2E75B6","#4472C4","#5B9BD5","#9DC3E6","#D6E4F0"]
    jaren_lbl  = ["2024","2025","2026"]

    fig2 = go.Figure()
    for (cat_name, codes), color in zip(cost_cats, cat_colors):
        vals = [-tot(df, j, codes) for j in [2024, 2025, 2026]]
        vals = [v if v > 0 else 0 for v in vals]
        fig2.add_trace(go.Bar(
            name=cat_name, x=jaren_lbl, y=vals,
            marker_color=color, marker_line_color="white", marker_line_width=1,
            hovertemplate="%{x}: €%{y:,.0f}<extra>" + cat_name + "</extra>",
        ))
    fig2.update_layout(**CHART_LAYOUT, barmode="stack", title=dict(
        text="Operationele Kosten per Jaar", font=dict(size=13, color="#1F3864"), x=0))
    st.plotly_chart(fig2, use_container_width=True)

# ─── RESULTATENREKENING (HTML) ────────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)

def pl_row(label, codes, stijl="", indent=False):
    vals = [tot(df, j, codes) for j in [2024, 2025, 2026]]
    td_lbl = f'<td class="{"pl-ind" if indent else ""}">{label}</td>'
    tds = ""
    for v in vals:
        neg_cls = ' class="pl-neg"' if v < -0.5 else ""
        tds += f'<td style="text-align:right"{neg_cls}>{eur(v)}</td>'
    return f'<tr class="{stijl}">{td_lbl}{tds}</tr>'

def pl_sec_header(label):
    return (f'<tr class="pl-sec"><td colspan="4" style="padding:8px 14px;'
            f'font-size:11px;letter-spacing:.6px">{label}</td></tr>')

html = """
<div style="background:white;border-radius:10px;padding:20px 24px;
            box-shadow:0 2px 8px rgba(0,0,0,.09);overflow-x:auto">
<table class="pl-table">
<thead>
  <tr>
    <th style="text-align:left;width:44%">Resultatenrekening</th>
    <th>2024</th><th>2025</th><th>2026 YTD</th>
  </tr>
</thead>
<tbody>
"""
html += pl_sec_header("OMZET")
html += pl_row("Omzet premium",          [8000])
html += pl_row("Omzet losse producten",   [8010])
html += pl_row("Omzet hostingbijdragen",  [8020])
html += pl_row("TOTAAL OMZET",           OMZET_RK,           stijl="pl-sub")

html += pl_sec_header("KOSTPRIJS VAN DE OMZET")
html += pl_row("Inkopen",                COS_RK)
html += pl_row("BRUTOWINST",             OMZET_RK + COS_RK,  stijl="pl-sub")

html += pl_sec_header("OPERATIONELE KOSTEN")
html += pl_row("Marketing",              MARKETING_RK,        indent=True)
html += pl_row("Kantoor & Algemeen",     KANTOOR_RK,          indent=True)
html += pl_row("Ontwikkeling",           ONTWIKKEL_RK,        indent=True)
html += pl_row("Reis & Verblijf",        REIS_RK,             indent=True)
html += pl_row("Afschrijvingen",         AFSCHR_RK,           indent=True)
html += pl_row("Overige kosten",         OVERIG_RK,           indent=True)
html += pl_row("TOTAAL OPEX",            OPEX_C,              stijl="pl-sub")

html += pl_row("EBIT",                   EBIT_C,              stijl="pl-sub")

html += pl_sec_header("FINANCIEEL")
html += pl_row("Rente spaarrekening",    FINANCIEEL_RK)

html += pl_row("NETTORESULTAAT",         NETTO_C,             stijl="pl-tot")

html += "</tbody></table></div>"
st.markdown(html, unsafe_allow_html=True)

# ─── DETAIL BOEKINGEN ────────────────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
with st.expander("📋 Boekingsdetail"):
    c1, c2 = st.columns(2)
    jaren_f = c1.multiselect("Jaar",      [2024,2025,2026], default=[jaar_keuze])
    cat_f   = c2.multiselect("Categorie", sorted(df["Categorie"].unique()),
                              default=sorted(df["Categorie"].unique()))
    detail = df[df["Jaar"].isin(jaren_f) & df["Categorie"].isin(cat_f) &
                df["GrootboekCode"].isin(PL_CODES)].copy()
    detail["Datum"]    = detail["Datum"].dt.strftime("%d-%m-%Y")
    detail["PLBedrag"] = detail["PLBedrag"].round(2)
    st.dataframe(
        detail[["Datum","Soort","GrootboekCode","RekeningNaam",
                "Categorie","Omschrijving","PLBedrag"]],
        use_container_width=True, height=300)
    st.caption(f"{len(detail):,} boekingen")
