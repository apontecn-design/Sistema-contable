# CONTEM V1.0 — despliegue, respaldo y recuperación

Este procedimiento prepara la liberación. No autoriza modificar `main`, fusionar el PR ni desplegar producción. El punto 2 y la validación real de staging siguen siendo condiciones obligatorias de cierre.

## Antes de cualquier publicación

1. Registrar el commit candidato, la ejecución de CI, el despliegue anterior y los resultados de pruebas. Revisar el PR #1 sin fusionarlo hasta contar con aprobación expresa.
2. Confirmar que staging usa exclusivamente su disco `/var/contem-pruebas`, sin datos ni credenciales productivas. Confirmar las variables efectivas antes de activar cambios.
3. Usar en staging `CONTEM_ENTORNO=staging`, `CONTEM_STAGING_AUTORIZADO=SI`, `CONTEM_STAGING_DB=/var/contem-pruebas/sgci.db`, `SGCI_DATA_DIR=/var/contem-pruebas`, `SGCI_LAB_MODE=0` e identidad administrativa de pruebas. Los secretos se mantienen exclusivamente en Render.
4. Ejecutar `python scripts/validar_entorno_aislado.py` en el entorno de pruebas. El preflight comprueba configuración; no certifica por sí solo la independencia de Supabase ni del disco.
5. Validar credenciales reales y sesiones de pruebas: administrador, usuario activo, inactivo, cambio inicial de contraseña, perfil y excepciones, revocación y acceso a terceros. No retirar la barrera empresarial de empleados antes de completar la auditoría pendiente.
6. Probar en staging el balance/PDF/Excel; solicitudes con adjuntos y clasificación por línea; confirmación y contabilización única; importación/reimportación de cartolas; conciliación y reversos; creación/modificación/anulación de OC y asociación a facturas; nómina y protección de datos.
7. Comprobar persistencia con una marca sintética en staging antes y después de reiniciar/desplegar. Verificar su eliminación solamente en staging al terminar la prueba. No usar producción para pruebas de escritura.

## Respaldo previo

- El administrador puede descargar un respaldo desde CONTEM. El código usa la API `backup` de SQLite, verifica integridad y entrega un único archivo independiente de WAL/SHM; ya no copia directamente un archivo que podría estar en uso.
- Conservar un respaldo consistente anterior a la publicación, protegido y fuera de GitHub. Conservar aparte documentos externos al archivo SQLite, si existen. La copia del propietario usada en pruebas no sustituye un respaldo actual de producción.
- Registrar fecha, responsable, versión y checksum SHA-256 del archivo. No imprimir registros personales ni secretos en bitácoras públicas.
- Ensayar sobre una copia: `python scripts/ensayar_recuperacion.py /ruta/privada/respaldo.db`. Debe aprobar integridad, claves foráneas, esquema y contenido.
- Comparar una copia antes/después de migraciones: `python scripts/comparar_historicos.py /ruta/privada/antes.db /ruta/privada/despues.db`. Se permiten tablas/columnas nuevas, pero no cambios en las columnas y filas originales sin justificación individual.

## Configuración de producción

Tras completar los bloqueantes y recibir autorización, verificar en el servicio correcto:

- `SGCI_DATA_DIR` apunta al disco persistente real; la base histórica continúa llamándose `sgci.db`.
- `SGCI_LAB_MODE=0`; `CONTEM_ENTORNO=production`; no hay variables de staging activas.
- `SGCI_ADMIN_EMAIL` identifica al propietario y existe un método de acceso configurado: Supabase completo o respaldo Argon2 válido. No guardar claves en el código, en el PR ni en el documento.
- Ejecutar `python scripts/verificar_configuracion_produccion.py`. El script no muestra secretos ni cambia el servicio; comprueba también que la carpeta declarada sea un punto de montaje. No sustituye una prueba real de autenticación.
- Registrar que producción despliega automáticamente desde `main`. Una fusión puede publicar cambios: no fusionar como simple trámite de revisión.

## Publicación y comprobación posterior

Publicar solo el commit revisado y autorizado. Registrar el ID del nuevo despliegue y esperar a su estado terminal. Un disparador aceptado no demuestra que la aplicación esté operativa. Los servicios con disco persistente pueden experimentar interrupción durante el despliegue.

Comprobar disponibilidad, inicio de sesión, identidad de empresa, ruta de persistencia y reportes de solo lectura. Comparar los totales aprobados y revisar errores nuevos. No crear asientos de prueba en producción. Conservar evidencia privada de la comprobación y el respaldo anterior.

## Reversión de aplicación

Si hay errores de inicio, autorización, persistencia o integridad, detener la liberación y volver al despliegue previamente registrado, verificando que el código anterior siga siendo compatible con el esquema actual. Las migraciones de esta candidata son aditivas; no borrar las tablas nuevas para revertir el código.

Una reversión de Render no restaura automáticamente los datos del disco ni revierte operaciones contables. Revalidar disponibilidad, acceso y reportes después de la reversión. Revisar también el estado del despliegue automático para evitar que otra actualización publique de nuevo la versión rechazada.

## Recuperación de datos

Restaurar una base real requiere autorización específica del propietario y una ventana sin escrituras. Antes, respaldar también el estado actual y conciliar las operaciones posteriores al respaldo elegido: restaurar un respaldo antiguo puede perder operaciones válidas.

Ensayar la restauración en una carpeta aislada, comprobar integridad, claves foráneas, esquema y registros con las herramientas anteriores, y validar saldos y documentos. Solo entonces preparar el reemplazo controlado de la base del servicio detenido. Conservar ambos archivos y un procedimiento de retorno. Nunca ejecutar restauraciones o pruebas destructivas automáticamente sobre producción.

## Referencias de plataforma verificadas

[Variables y secretos de Render](https://render.com/docs/configure-environment-variables),
[despliegues](https://render.com/docs/deploys),
[reversión de despliegues y persistencia del disco](https://render.com/docs/rollbacks),
[comprobaciones de salud](https://render.com/docs/health-checks).

## Persistencia y recuperación comprobadas en pruebas — 12 de noviembre de 2026

Sobre el código 7d19117ba892760514d2640a129919d0b84aef2a se descargaron dos respaldos privados del servicio de pruebas, antes y después de redesplegar la misma versión. Se compararon 57 tablas en ambos sentidos: esquema, contenido y secuencias de identificadores idénticos; integridad correcta y ninguna infracción de claves foráneas. El reinicio terminó live y la pantalla de acceso funcionó sin excepciones.

Ambos respaldos se restauraron en copias locales aisladas mediante SQLite Backup API; se conservaron esquema y contenido y las verificaciones de integridad y relaciones pasaron. Esto comprueba la persistencia observada y el ensayo local de recuperación de esos respaldos. No se restauró la base activa ni se ejecutó recuperación sobre producción. Los archivos privados permanecen fuera del repositorio. La aceptación de perfiles operativos y flujos pendientes sigue abierta.
