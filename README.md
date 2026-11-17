# CONTEM V1.0 — rama de integración

El código de laboratorio se distribuye en `modulos/` con 22 componentes funcionales.
El punto de entrada Streamlit es `app.py`.

**Atención:** la separación por archivos usa todavía un puente de compatibilidad entre símbolos globales del monolito. No es una independencia completa de módulos ni demuestra por sí sola que todas las funciones operan correctamente.

## Seguridad

- `sgci_rrhh_autorizacion.py`: permisos efectivos y alcance de fichas laborales.
- `sgci_rrhh_seguridad.py`: consultas de solo lectura con filtrado en SQL.
- `sgci_rrhh_guardia_68b.py` y `sgci_rrhh_guardia_68c.py`: validación de sesión y descargas.
- Pantallas de simulación visibles **solo** con `SGCI_LAB_MODE=1`. En producción, no habilitar esta variable.
- La navegación administrativa para empleados sigue bloqueada hasta validar autorizaciones por operación.

## Base de datos

La conexión sigue usando `SGCI_DATA_DIR=/var/data` y `sgci.db`.
Este paquete no contiene bases de datos ni credenciales.
**Nunca aplicar migraciones ni pruebas destructivas sobre la base de producción.**

## Verificación disponible

`python -m compileall -q .` y `python -m unittest discover -s tests -v`.
Con copia local de laboratorio: `CONTEM_TEST_DB=/ruta/copia.db python -m unittest discover -s tests -v`.
En este entorno no se dispone del paquete Streamlit ni de conexión a PyPI, por lo que no se puede certificar el arranque en un servidor real.

## Despliegue

No fusionar con `main` ni activar Render hasta completar los flujos funcionales con cuentas reales de prueba y una copia de la base SQLite de producción.
