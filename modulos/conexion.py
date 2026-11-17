# CONTEM: componente extraído del app.py original; ejecución secuencial compartida.
def conectar():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ============================================================
# FUNCIONES GENERALES
# ============================================================

