# -*- coding: utf-8 -*-
"""CONTEM - entrada Streamlit, carga de componentes Python reales.

Compatibilidad: el sistema original utiliza referencias globales cruzadas.
El puente de símbolos conserva temporalmente esas referencias sin exec().
No constituye desacoplamiento completo ni autorización de producción.
"""
import importlib.util
import sys

_COMPONENTES = ['configuracion', 'conexion', 'utilidades', 'contabilidad', 'esquema', 'plan_cuentas', 'reglas_contables', 'contabilidad_asientos', 'compras_rcv', 'compras_iva', 'cuentas_por_cobrar', 'bancos', 'reportes_contables', 'reglas_contables_ui', 'compras_reclasificacion', 'contabilidad_reportes', 'conciliacion_documental', 'ventas_dte', 'tesoreria', 'usuarios', 'empresa', 'interfaz']


def iniciar():
    componentes = []
    simbolos = {}
    for nombre in _COMPONENTES:
        # La interfaz se importa al final, cuando las funciones están enlazadas.
        ruta = f"modulos.{nombre}"
        spec = importlib.util.find_spec(ruta)
        if spec is None or spec.loader is None:
            raise ImportError(f"No se encuentra el módulo {ruta}")
        modulo = importlib.util.module_from_spec(spec)
        # Inyectar dependencias conocidas ANTES de ejecutar la interfaz.
        vars(modulo).update(simbolos)
        sys.modules[ruta] = modulo
        try:
            spec.loader.exec_module(modulo)
        except BaseException:
            sys.modules.pop(ruta, None)
            raise
        componentes.append(modulo)
        # No se sobrescriben los símbolos propios del módulo ni los especiales.
        # Actualizar los módulos anteriores permite resolver referencias cruzadas
        # en tiempo de ejecución, sin ejecutar código fuente dinámicamente.
        # Reconocer definiciones propias sin confundirlas con símbolos inyectados.
        nuevos = {
            clave: valor for clave, valor in vars(modulo).items()
            if not clave.startswith('__')
            and (clave not in simbolos or valor is not simbolos[clave])
        }
        simbolos.update(nuevos)
        for componente in componentes:
            espacio = vars(componente)
            for clave, valor in nuevos.items():
                # Las definiciones anteriores del mismo nombre son reemplazadas
                # como sucedía con el namespace único de la aplicación original.
                espacio[clave] = valor
    return componentes


if __name__ == '__main__':
    iniciar()
