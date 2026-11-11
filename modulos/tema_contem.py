"""Tema visual CONTEM V1.0. Solo presentación; no toca datos ni permisos."""
import streamlit as st


def aplicar_tema_contem():
    st.markdown("""
    <style>
    :root { --contem:#137b53; --contem-dark:#075b40; --contem-soft:#e8f5ed; }
    .stApp { background:#f5f8f6; }
    [data-testid="stSidebar"] { background:linear-gradient(180deg,#064c37 0%,#0c6247 100%); }
    [data-testid="stSidebar"] * { color:#f1fff6; }
    [data-testid="stSidebar"] [role="radiogroup"] > label { color:#cce7d8; }
    [data-testid="stSidebar"] [role="radiogroup"] label div[data-testid="stMarkdownContainer"] p {
        font-size:14px; font-weight:550;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
        background:linear-gradient(90deg,#14986b,#27b581);
        box-shadow:0 3px 10px rgba(0,0,0,.13);
    }
    [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p {color:white;}
    [data-testid="stMainBlockContainer"] { padding-top:2.1rem; }
    [data-testid="stMetric"] [data-testid="stMetricValue"] {font-weight:760;}
    [data-testid="stMetric"] { min-height:112px; }
    [data-testid="stSidebar"] [data-testid="stSidebarContent"] {padding-top:1.3rem;}
    [data-testid="stSidebar"] [role="radiogroup"] label {
        border-radius:10px; padding:8px 10px; margin:2px 0;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label:hover {
        background:rgba(255,255,255,.12);
    }
    [data-testid="stSidebar"] [aria-checked="true"],
    [data-testid="stSidebar"] label:has(input:checked) {
        background:rgba(181,243,207,.2);
    }
    [data-testid="stSidebar"] button {
        border:1px solid rgba(255,255,255,.25);
        background:rgba(255,255,255,.08);
    }
    [data-testid="stMetric"] {
        background:white; border:1px solid #dcebe2;
        border-radius:16px; padding:17px 19px;
        box-shadow:0 4px 18px rgba(6,75,50,.045);
    }
    [data-testid="stMetricLabel"] { color:#587064; }
    [data-testid="stMetricValue"] { color:#125c42; }
    div.stButton > button[kind="primary"],div.stDownloadButton > button[kind="primary"] {
        background:#147e55; border-color:#147e55; color:white;
    }
    div.stButton > button[kind="primary"]:hover { background:#09603f; }
    [data-testid="stDataFrame"], [data-testid="stVerticalBlockBorderWrapper"] {
        border-radius:14px;
    }
    h1,h2,h3 { color:#143f31; letter-spacing:-.025em; }
    .contem-brand {
        display:flex; align-items:center; gap:11px; margin:4px 0 15px;
    }
    .contem-topbar-title {
        font-size:15px;font-weight:750;color:#115d42;
        border-bottom:1px solid #dcebe2;padding:0 0 10px;margin:-8px 0 6px;
    }
    .contem-topbar-title span {color:#7b9187;font-weight:450;}
    [data-testid="stSidebar"] [role="radiogroup"] label [data-testid="stWidgetLabel"] {display:none;}
    [data-testid="stSidebar"] [role="radiogroup"] label input[type="radio"] {
        position:absolute;opacity:0;width:1px;height:1px;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label [data-baseweb="radio"] > div:first-child {
        display:none;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label {
        cursor:pointer;min-height:39px;display:flex;align-items:center;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label:focus-within {
        outline:2px solid #c4f943;outline-offset:1px;
    }
    .contem-brand-icon {background:transparent!important;width:50px!important;height:50px!important;}
    .contem-hero {
        background:radial-gradient(circle at 83% 14%,rgba(191,245,77,.33),transparent 26%),
        linear-gradient(110deg,#075c40 0%,#0c8a5e 66%,#38b46b 100%)!important;
    }
    [data-testid="stSelectbox"] > div {border-radius:10px;}
    [data-testid="stTextInput"] input:disabled {background:#eef7f0;color:#285744;opacity:1;}
    [data-testid="stMainBlockContainer"] {max-width:1500px;}
    .contem-brand-icon {
        width:42px;height:42px;display:grid;place-items:center;
        border-radius:12px;background:#c5f0d4;color:#075338;
        font-size:27px;font-weight:800;line-height:1;
    }
    .contem-brand-name { font-size:26px;font-weight:800;letter-spacing:.03em;color:#fff; }
    .contem-brand-sub { font-size:11px;color:#bce3ce; }
    .contem-hero {
        background:linear-gradient(110deg,#08704c,#21966a);
        color:white;border-radius:18px;padding:23px 28px;margin-bottom:18px;
        box-shadow:0 8px 28px rgba(7,94,61,.12);
    }
    .contem-hero {display:flex;justify-content:space-between;align-items:center;gap:18px;}
    .contem-hero-periodo {
        flex:0 0 auto;min-width:160px;padding:13px 17px;
        border:1px solid rgba(255,255,255,.35);border-radius:13px;
        background:rgba(255,255,255,.12);color:#eafff3;font-size:12px;
    }
    .contem-hero-periodo strong {font-size:19px;color:white;}
    @media(max-width:800px) {
        .contem-hero {flex-direction:column;align-items:flex-start;}
        .contem-hero-periodo {width:100%;}
    }
    .contem-hero h2 { color:white;margin:0 0 7px;font-size:25px; }
    .contem-hero p { margin:0;color:#e3fff0;font-size:14px; }
    @media(max-width:800px) {
        .contem-hero {padding:18px;}
        .contem-hero h2 {font-size:21px;}
    }
    </style>
    """, unsafe_allow_html=True)
