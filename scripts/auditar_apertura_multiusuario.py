"""Auditoría estática conservadora para apertura de navegación multiusuario.

No habilita empleados. Detecta pantallas con lectura de datos sensibles
y puntos de escritura que requieren revisión de permisos por operación.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "modulos" / "interfaz.py"
SENSITIVE = ("nomina_trabajadores", "nomina_liquidaciones", "sgci_usuarios",
             "sgci_perfil_permisos", "sgci_usuario_permisos_detalle")
MUTATIONS = ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ")


def inspect():
    source = SOURCE.read_text(encoding="utf-8")
    lines = source.splitlines()
    ast.parse(source)
    sections = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(("if menu ==", "elif menu ==")):
            sections.append((index, stripped))
    results = []
    for i, (start, label) in enumerate(sections):
        end = sections[i+1][0] if i+1 < len(sections) else len(lines)
        segment = "\n".join(lines[start:end])
        sensitive = [t for t in SENSITIVE if t in segment]
        writes = [t.strip() for t in MUTATIONS if t in segment.upper()]
        guards = segment.count("sgci_exigir_permiso(")
        results.append({"section":label,"line":start+1,"sensitive_tables":sensitive,
                        "sql_mutation_keywords":writes,"permission_checks":guards})
    return results


if __name__ == "__main__":
    import json
    print(json.dumps(inspect(), ensure_ascii=False, indent=2))
