"""
Schaakopening Essenties — FP&A Dashboard
Structuur identiek aan het Excel dashboard.
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

OMZET_RK      = [8000, 8010, 8020]
COS_RK        = [7000]
MARKETING_RK  = [4510, 4520, 4540, 4590, 4794]
AFSCHR_RK     = [4335, 4340]
ONTWIKKEL_RK  = [4755]
REIS_RK       = [4530, 4600]
KANTOOR_RK    = [4500, 4550, 4555, 4560, 4700, 4720, 4740, 4750, 4760, 4790, 4810]
OVERIG_RK     = [4850, 4860, 4900, 4950]
FINANCIEEL_RK = [9000]
OPEX_C        = MARKETING_RK + KANTOOR_RK + ONTWIKKEL_RK + REIS_RK + AFSCHR_RK + OVERIG_RK
EBIT_C        = OMZET_RK + COS_RK + OPEX_C
NETTO_C       = EBIT_C + FINANCIEEL_RK
PL_CODES      = OMZET_RK + COS_RK + OPEX_C + FINANCIEEL_RK

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

MND = ["Jan","Feb","Mrt","Apr","Mei","Jun","Jul","Aug","Sep","Okt","Nov","Dec"]

# ─── CSS ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background:#F0F2F6; }
[data-testid="stSidebar"] { background:#1F3864 !important; }
[data-testid="stSidebar"] label,[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,[data-testid="stSidebar"] div,
[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 { color:#FFFFFF !important; }
[data-testid="stSidebar"] .stButton>button {
    background:#2E75B6; color:white !important; border:none;
    width:100%; border-radius:6px; font-weight:600;
}
.kpi { background:white; border-radius:10px; padding:18px 20px 14px;
       box-shadow:0 2px 8px rgba(0,0,0,.10); }
.kpi-lbl { font-size:10px; color:#999; text-transform:uppercase;
           letter-spacing:1px; font-weight:700; margin-bottom:6px; }
.kpi-val { font-size:30px; font-weight:800; line-height:1.1; }
.kpi-sub { font-size:11px; font-weight:600; margin-top:6px; min-height:14px; }
.grow-p { color:#375623; } .grow-n { color:#C00000; }

.pl-wrap { background:white; border-radius:10px; padding:18px 20px;
           box-shadow:0 2px 8px rgba(0,0,0,.10); overflow-x:auto; }
table.pl { width:100%; border-collapse:collapse; font-family:Arial,sans-serif;
           font-size:12px; white-space:nowrap; }
table.pl th { background:#1F3864; color:white; padding:8px 10px;
              text-align:right; font-size:10px; letter-spacing:.5px;
              text-transform:uppercase; border:1px solid #2E75B6; }
table.pl th.lbl { text-align:left; min-width:180px; }
table.pl td { padding:6px 10px; border-bottom:1px solid #EEF0F3; text-align:right; }
table.pl td.lbl { text-align:left; }
table.pl td.ind { text-align:left; padding-left:22px; color:#555; }
.sec td { background:#2E75B6 !important; color:white !important;
          font-weight:700; font-size:11px; letter-spacing:.4px;
          border-bottom:none !important; padding:7px 10px; }
.sub td { background:#EEF3FA !important; font-weight:700; }
.tot td { background:#1F3864 !important; color:white !important;
          font-weight:800; font-size:13px; border-bottom:none !important; }
.neg { color:#C00000 !important; }
.tot .neg { color:#FFB3B3 !important; }
</style>
""", unsafe_allow_html=True)

# ─── DATA ────────────────────────────────────────────────────────────────────
def _zget(obj, key):
    try: return obj[key]
    except: return None

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
                    "MutatieNr": ZeepSkip,
                    "MutatieNrVan": nr_van if nr_van > 0 else ZeepSkip,
                    "MutatieNrTm": ZeepSkip, "Factuurnummer": ZeepSkip,
                    "DatumVan": datetime(DATUM_VAN.year, DATUM_VAN.month, DATUM_VAN.day),
                    "DatumTm":  datetime(DATUM_TOT.year, DATUM_TOT.month, DATUM_TOT.day),
                }
            )
            mutaties = (r["Mutaties"]["cMutatieList"]
                        if r["Mutaties"] and r["Mutaties"]["cMutatieList"] else [])
            for m in mutaties:
                regels = (m["MutatieRegels"]["cMutatieListRegel"]
                          if m["MutatieRegels"] and m["MutatieRegels"]["cMutatieListRegel"] else [])
                tg_codes = set()
                for rg in regels:
                    try: tg_codes.add(int(str(rg["TegenrekeningCode"] or "").strip()))
                    except: pass
                for rg in regels:
                    try:    gb = int(str(rg["TegenrekeningCode"] or "").strip())
                    except: gb = None
                    rows.append({
                        "Soort": str(_zget(m,"Soort") or ""),
                        "Datum": _zget(m,"Datum"),
                        "Omschrijving": str(_zget(m,"Omschrijving") or ""),
                        "GrootboekCode": gb,
                        "BedragExclBTW": float(_zget(rg,"BedragExclBTW") or 0),
                        "Kant": "T",
                    })
                try:    rek = int(str(_zget(m,"Rekening") or "").strip())
                except: rek = None
                if rek in PL_CODES and rek not in tg_codes:
                    som = sum(float(_zget(rg,"BedragExclBTW") or 0) for rg in regels)
                    rows.append({
                        "Soort": str(_zget(m,"Soort") or ""),
                        "Datum": _zget(m,"Datum"),
                        "Omschrijving": str(_zget(m,"Omschrijving") or ""),
                        "GrootboekCode": rek,
                        "BedragExclBTW": -som,
                        "Kant": "R",
                    })
            if len(mutaties) < 500: break
            nr_van = max(m["MutatieNr"] for m in mutaties) + 1
    finally:
        try: client.service.CloseSession(SessionID=sid)
        except: pass

    df = pd.DataFrame(rows)
    df["Datum"] = pd.to_datetime(df["Datum"])
    df["Jaar"]  = df["Datum"].dt.year.astype(int)
    df["Maand"] = df["Datum"].dt.month.astype(int)

    NEGATE = {"GeldUitgegeven","FactuurOntvangen"}
    df["PLBedrag"] = df["BedragExclBTW"]
    mask = (df["Kant"] == "T") & df["Soort"].isin(NEGATE)
    df.loc[mask,"PLBedrag"] = -df.loc[mask,"BedragExclBTW"]
    return df

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def som(df, jaar, codes, maand=None):
    s = df[df["GrootboekCode"].isin(codes) & (df["Jaar"] == int(jaar))]
    if maand: s = s[s["Maand"] == int(maand)]
    return s["PLBedrag"].sum()

def eur(v):
    if v is None or (isinstance(v, float) and pd.isna(v)): return "—"
    if abs(v) < 0.50: return "—"
    s = "-" if v < 0 else ""
    return f"{s}€ {abs(v):,.0f}".replace(",", ".")

def pct(v):
    return f"{v*100:.1f}%" if v is not None else "—"

def groei_span(v, vp):
    if not vp: return "&nbsp;"
    g = (v - vp) / abs(vp)
    a, c = ("▲","grow-p") if g >= 0 else ("▼","grow-n")
    return f'<span class="{c}">{a} {abs(g)*100:.1f}%</span>'

# ─── SIDEBAR ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ♟️ Filters")
    st.markdown("---")
    jaar = st.selectbox("Jaar", [2026, 2025, 2024], index=0)
    vgl_opties = [j for j in [2025, 2024] if j != jaar]
    vgl_raw = st.selectbox("Vergelijk met", ["— geen vergelijking"] + [str(j) for j in vgl_opties])
    vgl = None if vgl_raw.startswith("—") else int(vgl_raw)
    st.markdown("---")
    if st.button("🔄 Vernieuwen"):
        st.cache_data.clear(); st.rerun()
    st.caption(f"Vernieuwd: {datetime.now().strftime('%d %b %Y %H:%M')}")
    st.caption("Cache: 1 uur")

# ─── DATA ────────────────────────────────────────────────────────────────────
try:
    df = load_data()
except Exception as e:
    st.error(f"❌ Verbindingsfout: {e}"); st.stop()

# ─── HEADER ──────────────────────────────────────────────────────────────────
st.markdown(
    f"<div style='background:#1F3864;color:white;padding:14px 22px;border-radius:10px;"
    f"margin-bottom:18px;display:flex;justify-content:space-between;align-items:center'>"
    f"<div><span style='font-size:20px;font-weight:800'>♟️ &nbsp;Schaakopening Essenties</span>"
    f"<span style='font-size:12px;color:#9DC3E6;margin-left:16px'>Executive Financial Dashboard</span></div>"
    f"<div style='font-size:11px;color:#9DC3E6'>{jaar}"
    f"{(' vs ' + str(vgl)) if vgl else ''} &nbsp;|&nbsp; "
    f"{datetime.now().strftime('%d %b %Y')}</div></div>",
    unsafe_allow_html=True)

# ─── KPI TILES ───────────────────────────────────────────────────────────────
omzet = som(df, jaar, OMZET_RK)
ebit  = som(df, jaar, EBIT_C)
netto = som(df, jaar, NETTO_C)
nm    = netto / omzet if omzet else None
omzet_v = som(df, vgl, OMZET_RK) if vgl else None
ebit_v  = som(df, vgl, EBIT_C)   if vgl else None
netto_v = som(df, vgl, NETTO_C)  if vgl else None

def tile(label, v, vp, accent, is_pct=False):
    val = pct(v) if is_pct else eur(v)
    col = "#C00000" if (v is not None and v < 0) else "#1F3864"
    sub = groei_span(v, vp) if vp is not None else "&nbsp;"
    return (f'<div class="kpi" style="border-top:5px solid {accent}">'
            f'<div class="kpi-lbl">{label}</div>'
            f'<div class="kpi-val" style="color:{col}">{val}</div>'
            f'<div class="kpi-sub">{sub}</div></div>')

c1,c2,c3,c4 = st.columns(4)
c1.markdown(tile("Omzet",          omzet, omzet_v, "#2E75B6"),               unsafe_allow_html=True)
c2.markdown(tile("EBIT",           ebit,  ebit_v,  "#1F3864"),               unsafe_allow_html=True)
c3.markdown(tile("Nettoresultaat", netto, netto_v,
                 "#375623" if (netto or 0)>=0 else "#C00000"),                unsafe_allow_html=True)
c4.markdown(tile("Nettomarge %",   nm,    None,    "#C55A11", is_pct=True),  unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ─── GRAFIEKEN ───────────────────────────────────────────────────────────────
g1, g2 = st.columns(2)
CLR = {2024:"#9DC3E6", 2025:"#2E75B6", 2026:"#1F3864"}
BASE_LAYOUT = dict(
    plot_bgcolor="white", paper_bgcolor="white", font_family="Arial",
    margin=dict(t=36,b=20,l=10,r=10), height=300,
    yaxis=dict(gridcolor="#EFEFEF", tickprefix="€ ", zeroline=True,
               zerolinecolor="#CCCCCC", zerolinewidth=1),
    xaxis=dict(gridcolor="rgba(0,0,0,0)"),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, title=""),
)

# Grafiek 1: Omzet per maand — geselecteerd jaar als balken, vergelijking als lijn
with g1:
    fig1 = go.Figure()
    y_main = [som(df, jaar, OMZET_RK, m) for m in range(1,13)]
    fig1.add_trace(go.Bar(
        x=MND, y=y_main, name=str(jaar),
        marker_color=CLR.get(jaar,"#2E75B6"),
        hovertemplate="%{x}: €%{y:,.0f}<extra>" + str(jaar) + "</extra>",
    ))
    if vgl:
        y_vgl = [som(df, vgl, OMZET_RK, m) for m in range(1,13)]
        fig1.add_trace(go.Scatter(
            x=MND, y=y_vgl, name=str(vgl), mode="lines+markers",
            line=dict(color=CLR.get(vgl,"#9DC3E6"), width=2, dash="dot"),
            marker=dict(size=5),
            hovertemplate="%{x}: €%{y:,.0f}<extra>" + str(vgl) + "</extra>",
        ))
    fig1.update_layout(**BASE_LAYOUT, title=dict(
        text=f"Omzet per Maand — {jaar}" + (f" vs {vgl}" if vgl else ""),
        font=dict(size=12, color="#1F3864"), x=0))
    st.plotly_chart(fig1, use_container_width=True)

# Grafiek 2: Operationele kosten per categorie — geselecteerd jaar (+ vergelijking indien actief)
with g2:
    cost_cats = [
        ("Marketing",      MARKETING_RK),
        ("Kantoor & Alg.", KANTOOR_RK),
        ("Ontwikkeling",   ONTWIKKEL_RK),
        ("Reis & Verblijf",REIS_RK),
        ("Afschrijvingen", AFSCHR_RK),
        ("Overige kosten", OVERIG_RK),
    ]
    cat_clr = ["#1F3864","#2E75B6","#4472C4","#5B9BD5","#9DC3E6","#D6E4F0"]
    jaren_show = [jaar] + ([vgl] if vgl else [])

    fig2 = go.Figure()
    for (cat_name, codes), color in zip(cost_cats, cat_clr):
        vals = [-som(df, j, codes) for j in jaren_show]
        vals = [v if v > 0 else 0 for v in vals]
        fig2.add_trace(go.Bar(
            name=cat_name, x=[str(j) for j in jaren_show], y=vals,
            marker_color=color, marker_line_color="white", marker_line_width=1,
            hovertemplate="%{x}: €%{y:,.0f}<extra>" + cat_name + "</extra>",
        ))
    fig2.update_layout(**BASE_LAYOUT, barmode="stack", title=dict(
        text=f"Operationele Kosten — {jaar}" + (f" vs {vgl}" if vgl else ""),
        font=dict(size=12, color="#1F3864"), x=0))
    st.plotly_chart(fig2, use_container_width=True)

# ─── RESULTATENREKENING (maandelijks, HTML) ───────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)

jaren_toon = [jaar] + ([vgl] if vgl else [])

def build_pl_table(df, jaren):
    j1 = jaren[0]
    j2 = jaren[1] if len(jaren) > 1 else None
    toon_vgl = j2 is not None

    # header
    th_lbl = '<th class="lbl">Resultatenrekening</th>'
    th_mnd = "".join(f'<th>{m}</th>' for m in MND)
    th_tot = f'<th style="background:#2E75B6">Totaal {j1}</th>'
    th_vgl = (f'<th style="background:#4A4A4A">Totaal {j2}</th>'
              f'<th style="background:#4A4A4A">YoY%</th>') if toon_vgl else ""
    header = f'<tr>{th_lbl}{th_mnd}{th_tot}{th_vgl}</tr>'

    def row(label, codes, stijl="", lbl_class="lbl"):
        vals_m = [som(df, j1, codes, m) for m in range(1,13)]
        totaal = sum(vals_m)
        tds_m  = "".join(
            f'<td class="{"neg" if v<-0.5 else ""}">{eur(v) if abs(v)>0.5 else "—"}</td>'
            for v in vals_m)
        neg_t  = "neg" if totaal < -0.5 else ""
        td_tot = f'<td class="{neg_t}" style="font-weight:700">{eur(totaal)}</td>'
        if toon_vgl:
            tot2   = som(df, j2, codes)
            neg_v  = "neg" if tot2 < -0.5 else ""
            g = ((totaal-tot2)/abs(tot2)*100) if tot2 else None
            g_str = (f'<span class="{"grow-p" if g>=0 else "grow-n"}">'
                     f'{"▲" if g>=0 else "▼"}{abs(g):.1f}%</span>') if g is not None else "—"
            td_vgl = (f'<td class="{neg_v}">{eur(tot2)}</td>'
                      f'<td style="text-align:center">{g_str}</td>')
        else:
            td_vgl = ""
        return f'<tr class="{stijl}"><td class="{lbl_class}">{label}</td>{tds_m}{td_tot}{td_vgl}</tr>'

    def sec(label):
        colspan = 14 + (2 if toon_vgl else 0)
        return (f'<tr class="sec"><td colspan="{colspan}" '
                f'style="padding:7px 10px;font-size:11px;letter-spacing:.5px">'
                f'{label}</td></tr>')

    rows = header
    rows += sec("OMZET")
    rows += row("Omzet premium",          [8000], lbl_class="ind")
    rows += row("Omzet losse producten",   [8010], lbl_class="ind")
    rows += row("Omzet hostingbijdragen",  [8020], lbl_class="ind")
    rows += row("TOTAAL OMZET",           OMZET_RK, stijl="sub")

    rows += sec("OPERATIONELE KOSTEN")
    rows += row("Marketing",              MARKETING_RK,  lbl_class="ind")
    rows += row("Kantoor & Algemeen",     KANTOOR_RK,    lbl_class="ind")
    rows += row("Ontwikkeling",           ONTWIKKEL_RK,  lbl_class="ind")
    rows += row("Reis & Verblijf",        REIS_RK,       lbl_class="ind")
    rows += row("Afschrijvingen",         AFSCHR_RK,     lbl_class="ind")
    rows += row("Overige kosten",         OVERIG_RK,     lbl_class="ind")
    rows += row("TOTAAL OPEX",            OPEX_C,        stijl="sub")

    rows += row("EBIT",                   EBIT_C,        stijl="sub")

    rows += sec("FINANCIEEL")
    rows += row("Rente spaarrekening",    FINANCIEEL_RK, lbl_class="ind")

    rows += row("NETTORESULTAAT",         NETTO_C,       stijl="tot")

    return f'<div class="pl-wrap"><table class="pl"><thead>{header}</thead><tbody>{rows}</tbody></table></div>'

st.markdown(build_pl_table(df, jaren_toon), unsafe_allow_html=True)

# ─── DETAIL ─────────────────────────────────────
