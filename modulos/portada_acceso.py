"""Portada CONTEM: presentación sin consultas, credenciales ni cambios de sesión."""

MARCA = '''<div class="contem-portada-marca"><svg viewBox="0 0 48 48" aria-hidden="true"><defs><linearGradient id="contem-login-logo" x2="1" y2="1"><stop stop-color="#c4f943"/><stop offset="1" stop-color="#23c57a"/></linearGradient></defs><path d="M36 11 A17 17 0 1 0 36 37" fill="none" stroke="url(#contem-login-logo)" stroke-width="10" stroke-linecap="round"/><circle cx="37" cy="11" r="5" fill="#b7f64b"/></svg><div>CONTEM<span>Sistema Contable y Empresarial</span></div><small>Tu gestión. Una visión más clara.</small></div>'''

ILUSTRACION = '''<svg class="contem-finanzas-visual" viewBox="0 0 620 365" role="img" aria-label="Ilustración de un panel financiero con gráficos y documentos contables">
<defs><linearGradient id="cg-area" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#37c78c" stop-opacity=".32"/><stop offset="1" stop-color="#37c78c" stop-opacity=".01"/></linearGradient><filter id="cg-sombra" x="-30%" y="-30%" width="170%" height="180%"><feDropShadow dx="0" dy="16" stdDeviation="15" flood-color="#002f23" flood-opacity=".3"/></filter></defs>
<circle cx="515" cy="100" r="93" fill="none" stroke="#9fe3b5" stroke-opacity=".15"/><circle cx="515" cy="100" r="118" fill="none" stroke="#9fe3b5" stroke-opacity=".1"/>
<g transform="translate(56 42) rotate(-3 250 145)" filter="url(#cg-sombra)"><rect width="492" height="276" rx="19" fill="#f7fcf8"/>
<rect width="492" height="40" rx="19" fill="#e8f3ec"/><path d="M0 22h492v18H0z" fill="#e8f3ec"/><circle cx="21" cy="20" r="4" fill="#2f926a"/><circle cx="35" cy="20" r="4" fill="#8eb8a0"/><circle cx="49" cy="20" r="4" fill="#b8d4c1"/><text x="77" y="24" fill="#345e4a" font-family="sans-serif" font-size="10" font-weight="700" letter-spacing="1">VISIÓN FINANCIERA</text>
<rect x="19" y="58" width="80" height="199" rx="10" fill="#0b6548"/><rect x="31" y="75" width="42" height="5" rx="2" fill="#c4f943"/><rect x="31" y="100" width="55" height="18" rx="5" fill="#268363"/><path d="M39 108h35M34 134h44M34 154h38M34 174h44" stroke="#a7cfbc" stroke-width="3" stroke-linecap="round"/><rect x="32" y="220" width="32" height="4" rx="2" fill="#97c5ae"/>
<text x="119" y="76" fill="#154d36" font-family="sans-serif" font-size="13" font-weight="700">Todo conectado.</text><text x="119" y="93" fill="#7b9686" font-family="sans-serif" font-size="9">Contabilidad · Tesorería · Gestión</text>
<g fill="#edf5ef"><rect x="119" y="107" width="107" height="42" rx="7"/><rect x="236" y="107" width="107" height="42" rx="7"/><rect x="353" y="107" width="119" height="42" rx="7"/></g>
<g fill="#678a75" font-family="sans-serif" font-size="8"><text x="130" y="122">CONTABILIDAD</text><text x="247" y="122">TESORERÍA</text><text x="364" y="122">DOCUMENTOS</text></g><g stroke="#1e7b55" stroke-width="4" stroke-linecap="round"><path d="M131 136h49M248 136h41M365 136h58"/></g>
<rect x="119" y="159" width="224" height="98" rx="8" fill="white" stroke="#e0ece3"/><path d="M134 180h192M134 202h192M134 224h192M134 243h192" stroke="#eef3ef"/><path d="M134 237L165 227L195 232L225 202L257 209L288 184L327 173V244H134Z" fill="url(#cg-area)"/><path d="M134 237L165 227L195 232L225 202L257 209L288 184L327 173" fill="none" stroke="#1d9868" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><circle cx="327" cy="173" r="4" fill="#b9ef51" stroke="#1d9868" stroke-width="2"/>
<rect x="353" y="159" width="119" height="98" rx="8" fill="white" stroke="#e0ece3"/><circle cx="412" cy="205" r="28" fill="none" stroke="#eaf2ec" stroke-width="12"/><circle cx="412" cy="205" r="28" fill="none" stroke="#1f9567" stroke-width="12" stroke-dasharray="105 176" transform="rotate(-90 412 205)"/><circle cx="412" cy="205" r="28" fill="none" stroke="#bbeb55" stroke-width="12" stroke-dasharray="40 176" stroke-dashoffset="-108" transform="rotate(-90 412 205)"/>
</g>
<g transform="translate(427 229) rotate(7)" filter="url(#cg-sombra)"><rect width="141" height="100" rx="13" fill="#eaffb5"/><rect x="14" y="15" width="25" height="28" rx="5" fill="#136a49"/><path d="M21 24h11M21 29h8M21 34h10" stroke="#d8ff9c" stroke-width="2" stroke-linecap="round"/><text x="14" y="65" font-family="sans-serif" font-size="12" font-weight="700" fill="#1c583a">Cada detalle cuenta.</text><path d="M14 79h92" stroke="#9cb977" stroke-width="3" stroke-linecap="round"/></g>
<g transform="translate(15 208)"><rect width="44" height="44" rx="13" fill="#bcf34f"/><path d="M13 23l6 6 13-14" fill="none" stroke="#07583d" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></g>
</svg>'''

HERO = '''<section class="contem-portada-hero"><div class="contem-portada-eyebrow"><span></span> CONTABILIDAD CON VISIÓN DE FUTURO</div><h1>Claridad para<br>cada <em>decisión.</em></h1><p>Conecta tus números, organiza tu gestión<br class="contem-salto-desktop"> y enfócate en lo que viene.</p>''' + ILUSTRACION + '''<div class="contem-portada-pie"><span>01 / UNA VISIÓN INTEGRAL</span><span>Contabilidad · Finanzas · Personas</span></div></section>'''

CSS = '''
<style>
[data-testid="stAppViewContainer"],.stApp {background:#f3f7f4!important;}
[data-testid="stSidebar"],[data-testid="stDecoration"] {display:none;}
[data-testid="stHeader"] {background:transparent;}
[data-testid="stMainBlockContainer"],[data-testid="stAppViewBlockContainer"] {max-width:1400px;padding:2.3rem 3rem 2rem;}
.contem-portada-marca {display:flex;align-items:center;gap:12px;margin:0 0 30px;color:#07583f;}
.contem-portada-marca svg {width:43px;height:43px;flex-shrink:0;}
.contem-portada-marca>div {font:800 25px/1.05 sans-serif;letter-spacing:.045em;}
.contem-portada-marca span {display:block;font:400 10px/1.8 sans-serif;letter-spacing:.015em;color:#6d8579;margin-top:3px;}
.contem-portada-marca small {margin-left:auto;font-size:12px;color:#6b8276;letter-spacing:.02em;}
[data-testid="stColumn"]:has(.contem-portada-hero) {background:radial-gradient(ellipse at 100% 0%,#24825b 0%,transparent 52%),linear-gradient(145deg,#064b38,#086347);border-radius:28px;overflow:hidden;}
[data-testid="stHorizontalBlock"]:has(.contem-portada-hero) {align-items:stretch!important;}
.contem-portada-hero {padding:39px 35px 24px;position:relative;color:#fff;}
.contem-portada-eyebrow {font-size:10px;letter-spacing:.16em;font-weight:650;color:#d3ebd9;display:flex;align-items:center;gap:9px;}
.contem-portada-eyebrow span {width:7px;height:7px;background:#c4f943;border-radius:100%;}
.contem-portada-hero h1 {font-size:clamp(39px,4.4vw,64px);font-weight:750;line-height:1.07;letter-spacing:-.055em!important;color:#fff!important;margin:24px 0 18px!important;padding:0!important;}
.contem-portada-hero h1 em {font-style:normal;color:#c4f474;}
.contem-portada-hero p {font-size:15px;line-height:1.65;color:#cee4d8;margin:0!important;}
.contem-finanzas-visual {display:block;width:100%;height:auto;max-height:320px;margin:15px 0 3px;}
.contem-portada-pie {display:flex;justify-content:space-between;gap:12px;padding-top:14px;border-top:1px solid #ffffff24;font-size:9px;color:#c6e1d1;letter-spacing:.07em;}
[data-testid="stColumn"]:has(.contem-acceso-heading) {background:#fff;border:1px solid #dfebe2;border-radius:28px;padding:42px 34px 30px;box-shadow:0 12px 40px #16482b06;}
.contem-acceso-heading {padding:9px 0 22px;}
.contem-acceso-heading small {font-size:10px;font-weight:700;letter-spacing:.17em;color:#4c7c60;}
.contem-acceso-heading h2 {font-size:31px;line-height:1.2;letter-spacing:-.04em;color:#173f2c;margin:12px 0 12px;padding:0;}
.contem-acceso-heading p {color:#728379;font-size:14px;line-height:1.65;margin:0;}
[data-testid="stForm"] {border:none;padding:4px 0 0;}
[data-testid="stTextInput"] label p {color:#345744;font-size:12px;font-weight:600;}
[data-testid="stTextInput"] input {min-height:48px;background:#f7faf8;color:#214e35;}
[data-testid="stTextInput"]>div>div {border-radius:12px;border-color:#dbe5de;background:#f7faf8;}
[data-testid="stTextInput"]>div>div:focus-within {border-color:#198057;box-shadow:0 0 0 3px #15865312;}
[data-testid="stFormSubmitButton"] button {min-height:49px;background:#0b704d!important;border-color:#0b704d!important;color:#fff!important;border-radius:12px;font-weight:650;box-shadow:0 7px 16px #0b704d18;}
[data-testid="stFormSubmitButton"] button:hover {background:#07583d!important;}
[data-testid="stRadio"] [role="radiogroup"] {gap:8px;flex-wrap:wrap;padding:0 0 10px;}
[data-testid="stRadio"] label {border:1px solid #e0e9e2;border-radius:9px;padding:7px 9px;margin:0;font-size:11px;}
[data-testid="stRadio"] label p {font-size:11px;color:#577363;}
[data-testid="stRadio"] label:has(input:checked) {background:#eaf5ed;border-color:#b5d4bf;}
[data-testid="stRadio"] label:has(input:checked) p {color:#075c3e;font-weight:600;}
[data-testid="stRadioOption"][data-selected="true"]>div>div:first-child {background-color:#0b704d!important;border-color:#0b704d!important;}
.contem-acceso-footer {border-top:1px solid #edf1ee;margin-top:24px;padding-top:18px;display:flex;align-items:center;gap:8px;color:#829186;font-size:11px;line-height:1.5;}
.contem-acceso-footer svg {width:15px;height:18px;flex-shrink:0;color:#39805b;}
.contem-portada-footer {text-align:center;color:#849589;font-size:10px;letter-spacing:.025em;margin-top:23px;}
@media(max-width:900px) {[data-testid="stMainBlockContainer"],[data-testid="stAppViewBlockContainer"]{padding:1.5rem 1.3rem;}.contem-portada-hero{padding:30px 24px 20px;}[data-testid="stColumn"]:has(.contem-acceso-heading){padding:28px 23px;}.contem-portada-marca small{display:none;}.contem-portada-pie{font-size:8px;}}
@media(max-width:640px) {.contem-finanzas-visual{display:none;}.contem-portada-hero h1{font-size:36px;}.contem-portada-hero{padding:24px 25px;}.contem-portada-hero p{font-size:13px;}.contem-portada-marca{margin-bottom:20px;}.contem-acceso-heading h2{font-size:28px;}.contem-portada-pie{display:none;}[data-testid="stColumn"]:has(.contem-acceso-heading){padding:23px;}.contem-acceso-heading{padding-top:0;padding-bottom:12px;}}
@media(prefers-reduced-motion:reduce) {*{transition:none!important;}}
</style>
'''

ENCABEZADO_ACCESO = '''<div class="contem-acceso-heading"><small>BIENVENIDO A CONTEM</small><h2>Accede a tu espacio.</h2><p>Tu información y herramientas de gestión,<br>en un solo lugar.</p></div>'''
PIE_ACCESO = '''<div class="contem-acceso-footer"><svg viewBox="0 0 20 24" fill="none" aria-hidden="true"><rect x="3" y="10" width="14" height="11" rx="3" stroke="currentColor" stroke-width="1.6"/><path d="M6 10V7a4 4 0 018 0v3" stroke="currentColor" stroke-width="1.6"/></svg><span>Acceso personal · Permisos según tu perfil.</span></div>'''


def preparar_portada_acceso(st):
    st.markdown(CSS,unsafe_allow_html=True)
    st.markdown(MARCA,unsafe_allow_html=True)
    izquierda,derecha=st.columns([1.25,1],gap='large')
    with izquierda:
        st.markdown(HERO,unsafe_allow_html=True)
    return derecha
