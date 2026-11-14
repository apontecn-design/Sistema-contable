# CONTEM: componente extraído del app.py original; ejecución secuencial compartida.
"""
SGCI - Sistema de Gestión Contable Integral
Versión actualizada con:
- Corrección de multplicador de signo (-1) aplicado en resúmenes y montos para Notas de Crédito (Compras y Ventas)
- Tratamiento contable completo por Tipo de Documento SII
- Separación de Facturas Exentas de Ventas (Tipo 34 y 41 -> Cuenta Ventas Exentas)
- Protección de acceso mediante contraseña y respaldo de base de datos
"""

import io
import os
import re
import sqlite3
import zipfile
import xml.etree.ElementTree as ET
import html
from datetime import datetime, date, timedelta
from hashlib import sha256
from decimal import Decimal, ROUND_HALF_UP

import pandas as pd
import streamlit as st


# ============================================================
# CONFIGURACIÓN Y SEGURIDAD (AUTENTICACIÓN)
# ============================================================

DATA_DIR = os.getenv("SGCI_DATA_DIR", ".")
DB_FILE = os.path.join(DATA_DIR, "sgci.db")
if os.getenv('CONTEM_ENTORNO', '').strip().lower() in ('staging', 'test'):
    from scripts.validar_entorno_aislado import validar as _validar_aislamiento
    _aislamiento = _validar_aislamiento()
    if not _aislamiento['aprobado']:
        raise RuntimeError('Entorno de pruebas inseguro: ' + '; '.join(_aislamiento['errores']))
    DB_FILE = os.path.abspath(os.path.expanduser(os.environ['CONTEM_STAGING_DB']))
os.makedirs(DATA_DIR, exist_ok=True)

st.set_page_config(
    page_title="CONTEM - Sistema Contable",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Identidad visual SGCI: verde sobrio, superficies claras y navegación compacta.
st.markdown("""
<style>
:root {--olive:#2E694D;--olive-deep:#1F382B;--olive-mid:#78866B;--sage:#B7C2A7;--cream:#F7F9F7;--gold:#D1B57A;--border:#E1E6DA;}
[data-testid="stAppViewContainer"] {background:var(--cream);color:#303D2A;}
[data-testid="stSidebar"] {background:linear-gradient(175deg,#264D36,#192E24);border-right:1px solid #3E654A;}
[data-testid="stSidebar"] * {color:#F7F8F2!important;}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {color:#F7F8F2!important;}
/* Botones de respaldo y salida: texto legible en estado normal, hover y foco. */
[data-testid="stSidebar"] [data-testid="stDownloadButton"] button,
[data-testid="stSidebar"] [data-testid="stButton"] button {background:#F3F4EE!important;color:#303D2A!important;border:1px solid #B7C2A7!important;}
[data-testid="stSidebar"] [data-testid="stDownloadButton"] button *,
[data-testid="stSidebar"] [data-testid="stButton"] button * {color:#303D2A!important;}
[data-testid="stSidebar"] [data-testid="stDownloadButton"] button:hover,
[data-testid="stSidebar"] [data-testid="stButton"] button:hover {background:#DCE6D2!important;color:#24301F!important;}
[data-testid="stSidebar"] [data-testid="stDownloadButton"] button:hover *,
[data-testid="stSidebar"] [data-testid="stButton"] button:hover * {color:#24301F!important;}
[data-testid="stSidebar"] div[role="radiogroup"] label {border-radius:11px;padding:.42rem .5rem;transition:background .15s;}
[data-testid="stSidebar"] div[role="radiogroup"] label:hover {background:#426F4D;}
[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {background:#477958;box-shadow:inset 3px 0 #D1B57A;}
/* Menú principal: mayor legibilidad sin afectar controles internos. */
[data-testid="stSidebar"] div[role="radiogroup"] label p {font-size:16px!important;font-weight:650!important;line-height:1.35!important;}
[data-testid="stSidebar"] div[role="radiogroup"] label {padding:.48rem .5rem;}
.stButton>button,.stDownloadButton>button {border-radius:11px;border:1px solid #C8D2C1;transition:all .15s;}
.stButton>button[kind="primary"],.stFormSubmitButton>button[kind="primary"] {background:#2E694D!important;color:white!important;border-color:#46543A!important;}
.stButton>button[kind="primary"]:hover,.stFormSubmitButton>button[kind="primary"]:hover {background:#24543C!important;}
[data-testid="stMetric"] {background:#FFFFFF;border:1px solid var(--border);border-radius:16px;padding:16px;box-shadow:0 3px 14px rgba(48,61,42,.045);}
[data-testid="stMetricValue"] {color:#2E694D;}
[data-testid="stVerticalBlockBorderWrapper"]>div[data-testid="stVerticalBlock"] {border-radius:12px;}
[data-testid="stDataFrame"], [data-testid="stTable"] {border-radius:13px;overflow:hidden;}
[data-baseweb="tab-list"] {gap:.4rem;border-bottom:1px solid #D8DFD1;}
button[data-baseweb="tab"] {border-radius:11px 11px 0 0;}
h1,h2,h3 {letter-spacing:-.025em;color:#35432D;}
/* SGCI Modelo 1: superficies claras, tarjetas de indicadores y paneles de trabajo. */
[data-testid="stHeader"] {background:#FFFFFFE8;}
[data-testid="stAppViewBlockContainer"] {max-width:1560px;padding-top:1.3rem;}
[data-testid="stMetric"] {box-shadow:0 5px 18px rgba(35,67,43,.055);border-radius:17px;}
[data-testid="stMetricLabel"] {font-weight:600;color:#59695D;}
[data-testid="stMetricValue"] {font-size:1.65rem;font-weight:750;}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2 {letter-spacing:.04em;}
[data-testid="stDataFrame"] {border:1px solid #E1E9E1;}
.stAlert {border-radius:12px;}

hr {border-color:#DDE4D7!important;}
</style>
""", unsafe_allow_html=True)

def sgci_exito(mensaje, *args, **kwargs):
    """Confirma una acción exitosa y conserva el mensaje tras st.rerun()."""
    st.session_state['_sgci_ultimo_exito'] = str(mensaje)
    return st.success(mensaje, *args, **kwargs)

# La contraseña real nunca se almacena en este archivo ni en GitHub.
# Configurar SGCI_PASSWORD_HASH en Render > Environment con el hash Argon2.
def verificar_clave_sgci(clave_ingresada):
    hash_configurado = os.environ.get("SGCI_PASSWORD_HASH", "").strip()
    if not hash_configurado or not hash_configurado.startswith("$argon2"):
        return False
    try:
        from argon2 import PasswordHasher
        from argon2.exceptions import VerificationError, InvalidHashError
        return PasswordHasher().verify(hash_configurado, clave_ingresada)
    except (VerificationError, InvalidHashError, ValueError, TypeError):
        return False


# Supabase Auth mediante HTTPS; no requiere librerías adicionales.
# La clave publicable se utiliza únicamente para endpoints de autenticación de usuario.
import json
import urllib.request
import urllib.error
import time


def sgci_supabase_config():
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = (os.getenv("SUPABASE_ANON_KEY", "") or os.getenv("SUPABASE_PUBLISHABLE_KEY", "")).strip()
    if not url.startswith("https://") or not key:
        return None
    return url, key


def sgci_auth_request(ruta, datos, access_token=None):
    config = sgci_supabase_config()
    if not config:
        raise ValueError("Supabase no está configurado en Render.")
    url, key = config
    headers = {"apikey": key, "Content-Type": "application/json", "Accept": "application/json"}
    if access_token:
        headers["Authorization"] = "Bearer " + access_token
    peticion = urllib.request.Request(
        url + "/auth/v1/" + ruta,
        data=json.dumps(datos).encode("utf-8"),
        headers=headers,
        method="POST" if ruta != "user" else "PUT",
    )
    try:
        with urllib.request.urlopen(peticion, timeout=15) as respuesta:
            contenido = respuesta.read().decode("utf-8")
            return json.loads(contenido) if contenido else {}
    except urllib.error.HTTPError as error:
        # No mostrar respuestas técnicas del proveedor ni datos sensibles al usuario.
        if error.code in (400, 401, 403, 422):
            raise ValueError("No fue posible completar la operación. Revisa los datos y vuelve a intentar.") from None
        if error.code == 429:
            raise ValueError("Demasiados intentos. Espera unos minutos antes de continuar.") from None
        raise ValueError("Servicio de autenticación temporalmente no disponible.") from None
    except (urllib.error.URLError, TimeoutError):
        raise ValueError("No se pudo conectar con el servicio de autenticación.") from None


def sgci_guardar_sesion(respuesta):
    token = respuesta.get("access_token")
    refresh = respuesta.get("refresh_token")
    if not token or not refresh:
        raise ValueError("No se recibió una sesión válida de Supabase.")
    st.session_state["sgci_sb_access"] = token
    st.session_state["sgci_sb_refresh"] = refresh
    st.session_state["sgci_sb_expira"] = time.time() + int(respuesta.get("expires_in", 3600))
    st.session_state["sgci_sb_email"] = respuesta.get("user", {}).get("email", "")
    st.session_state["sgci_auth_tipo"] = "supabase"
    st.session_state["authenticated"] = True


def sgci_sesion_valida():
    if not st.session_state.get("authenticated"):
        return False
    if st.session_state.get("sgci_auth_tipo") != "supabase":
        return st.session_state.get("sgci_auth_tipo") == "argon2"
    if time.time() < st.session_state.get("sgci_sb_expira", 0) - 60:
        return True
    refresh = st.session_state.get("sgci_sb_refresh")
    if not refresh:
        return False
    try:
        respuesta = sgci_auth_request("token?grant_type=refresh_token", {"refresh_token": refresh})
        sgci_guardar_sesion(respuesta)
        return True
    except ValueError:
        return False


def sgci_cerrar_sesion():
    # Invalidar el token en el servidor cuando sea posible; limpiar siempre la sesión local.
    token = st.session_state.get("sgci_sb_access")
    if token and sgci_supabase_config():
        try:
            url, key = sgci_supabase_config()
            req = urllib.request.Request(url + "/auth/v1/logout", data=b"{}", headers={
                "apikey": key, "Authorization": "Bearer " + token,
                "Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=5).close()
        except Exception:
            pass
    for nombre in ("sgci_sb_access", "sgci_sb_refresh", "sgci_sb_expira", "sgci_sb_email", "sgci_auth_tipo"):
        st.session_state.pop(nombre, None)
    st.session_state["authenticated"] = False


if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not sgci_sesion_valida():
    sgci_cerrar_sesion()
    st.markdown("<br><br>", unsafe_allow_html=True)
    _, col2, _ = st.columns([1, 2, 1])
    with col2:
        st.title("🔐 Acceso Restringido - CONTEM")
        supabase_disponible = bool(sgci_supabase_config())
        opciones = (["Correo y contraseña", "Recuperar contraseña", "Acceso de respaldo (Argon2)"]
                    if supabase_disponible else ["Acceso de respaldo (Argon2)"])
        modo = st.radio("Método de acceso", opciones, horizontal=False)
        if modo == "Correo y contraseña":
            with st.form("sgci_supabase_login"):
                correo = st.text_input("Correo electrónico").strip().lower()
                clave = st.text_input("Contraseña", type="password")
                enviar = st.form_submit_button("Ingresar a CONTEM", type="primary", use_container_width=True)
            if enviar:
                if not correo or not clave:
                    st.error("Ingresa tu correo y contraseña.")
                else:
                    try:
                        respuesta = sgci_auth_request("token?grant_type=password", {"email": correo, "password": clave})
                        sgci_guardar_sesion(respuesta)
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))
        elif modo == "Recuperar contraseña":
            st.info("Solicita un código de recuperación al correo registrado en Supabase.")
            with st.form("sgci_recuperacion_solicitud"):
                correo = st.text_input("Correo registrado", key="sgci_recuperar_correo").strip().lower()
                solicitar = st.form_submit_button("Enviar código")
            if solicitar:
                if not correo:
                    st.error("Ingresa tu correo.")
                else:
                    try:
                        sgci_auth_request("recover", {"email": correo})
                        st.success("Si el correo está registrado, recibirás instrucciones de recuperación.")
                    except ValueError as error:
                        st.error(str(error))
            st.caption("La plantilla 'Reset password' de Supabase debe incluir {{ .Token }} para mostrar el código de seis dígitos.")
            with st.form("sgci_recuperacion_confirmacion"):
                correo_codigo = st.text_input("Correo electrónico", key="sgci_codigo_correo").strip().lower()
                codigo = st.text_input("Código recibido por correo")
                nueva = st.text_input("Nueva contraseña", type="password")
                confirmar = st.text_input("Repetir nueva contraseña", type="password")
                cambiar = st.form_submit_button("Cambiar contraseña", type="primary")
            if cambiar:
                if not correo_codigo or not codigo or not nueva:
                    st.error("Completa todos los campos.")
                elif len(nueva) < 8:
                    st.error("La nueva contraseña debe tener al menos ocho caracteres.")
                elif nueva != confirmar:
                    st.error("Las contraseñas no coinciden.")
                else:
                    try:
                        verificacion = sgci_auth_request("verify", {"email": correo_codigo, "token": codigo.strip(), "type": "recovery"})
                        token_recuperacion = verificacion.get("access_token")
                        if not token_recuperacion:
                            raise ValueError("El código no pudo validarse. Solicita uno nuevo.")
                        sgci_auth_request("user", {"password": nueva}, access_token=token_recuperacion)
                        st.success("Contraseña actualizada. Selecciona 'Correo y contraseña' para ingresar.")
                    except ValueError as error:
                        st.error(str(error))
        else:
            if not os.environ.get("SGCI_PASSWORD_HASH", "").strip().startswith("$argon2"):
                st.error("El acceso de respaldo no está configurado en Render.")
            else:
                st.info("Acceso temporal de respaldo para el administrador.")
                with st.form("sgci_login_form", clear_on_submit=False):
                    pwd = st.text_input("Contraseña de respaldo", type="password")
                    ingresar = st.form_submit_button("Ingresar al Sistema", type="primary", use_container_width=True)
                if ingresar:
                    if verificar_clave_sgci(pwd):
                        st.session_state["authenticated"] = True
                        st.session_state["sgci_auth_tipo"] = "argon2"
                        st.rerun()
                    else:
                        st.error("Contraseña incorrecta.")
    st.stop()


# Mostrar el resultado de la acción anterior aunque Streamlit haya recargado la página.
_mensaje_guardado=st.session_state.pop('_sgci_ultimo_exito',None)
if _mensaje_guardado:
    st.success('✅ ' + _mensaje_guardado)

# ============================================================
# CONEXIÓN
# ============================================================

