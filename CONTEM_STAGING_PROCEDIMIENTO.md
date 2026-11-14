# CONTEM V1.0 — procedimiento de staging seguro

**Estado:** preparación técnica; todavía NO se ha desplegado un entorno de staging ni probado autenticación real.

## Requisitos

1. Crear un servicio **separado** de Render, sin montar el disco persistente de producción.
2. Configurar almacenamiento independiente para staging y una copia de base anonimizada. No subir bases ni secretos a GitHub.
3. Establecer `CONTEM_ENTORNO=staging`, `CONTEM_STAGING_AUTORIZADO=SI`, `CONTEM_STAGING_DB=<ruta absoluta del archivo de prueba>`, `SGCI_DATA_DIR=<directorio aislado>` y `SGCI_ADMIN_EMAIL=<correo de prueba>`.
4. Ejecutar `python scripts/validar_entorno_aislado.py` antes del arranque. El preflight comprueba solo variables declaradas: **no demuestra que todas las rutas de escritura del código respeten esas variables**.
5. Revisar explícitamente en el código que la conexión SQLite efectiva apunta al archivo aislado, y verificar que ninguna credencial, webhook o integración apunte a producción.
6. Ejecutar `python -m unittest discover -s tests -v`, arranque Streamlit, login real con cuentas de prueba, denegación de usuarios inactivos, excepciones individuales, aislamiento de RR. HH. y operaciones de prueba.
7. Comparar saldo inicial/final de prueba, confirmar que no hubo escrituras en producción, hacer backup y restauración del entorno aislado.
8. Registrar evidencia y aprobar o rechazar liberación. No fusionar en `main` ni desplegar en producción sin autorización expresa.

## Criterios de rechazo

- Cualquier acceso a `/var/data/sgci.db` o a la base real.
- Fallo de autenticación, autorización de servicio o aislamiento por trabajador.
- Error de reversión contable, descuadre de asientos, pérdida de datos o restauración fallida.
- Evidencia insuficiente sobre las rutas de almacenamiento y las integraciones.

## Límite

GitHub Actions valida pruebas unitarias y sintéticas; no sustituye un servicio Render staging ni sesiones de Supabase reales.
