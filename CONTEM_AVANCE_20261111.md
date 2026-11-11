# CONTEM V1.0 — avance técnico del 11 de noviembre de 2026

Estado: punto 2 en desarrollo. Esta entrega NO declara terminados los 11 puntos ni habilita la navegación general de empleados.

## Base revisada y alcance

Trabajo iniciado desde `282a991ae3b75775d5a7ea4d4e8e136c034f7ff5`, rama `contem-v1-integracion`, PR #1 abierto como borrador. Se consultaron el repositorio, el PR y la configuración de servicios Render. No se consultaron conversaciones anteriores de ChatGPT.

Se conserva la interfaz aprobada, Python, Streamlit, SQLite, módulos y el puente de compatibilidad. No se modifica `main` ni se despliega producción.

## Cambios

- Autorización interna por submódulo y acción en 21 operaciones bancarias. Incluye importaciones, eliminaciones, conciliaciones, contabilizaciones y reversos; estos últimos exigen `anular`.
- Las consultas individuales de liquidaciones filtran trabajadores autorizados en SQL. Los identificadores inexistentes y ajenos reciben la misma respuesta para cuentas de alcance limitado.
- La segunda consulta del PDF vincula la liquidación con el trabajador previamente autorizado.
- En entornos `staging` o `test`, la aplicación valida el aislamiento antes de abrir SQLite y utiliza realmente `CONTEM_STAGING_DB`. La ruta histórica de producción no cambia.
- Corrección de rutas SQLite de solo lectura y cierre explícito de conexiones en herramientas de respaldo, recuperación y pruebas de Windows.

## Evidencia local

- 263 pruebas automatizadas correctas, sin omisiones, usando una copia privada del respaldo proporcionado por el propietario.
- 147 casos nuevos de autorización bancaria: sin permiso, perfil, excepción individual, denegación individual, usuario inactivo, permiso histórico insuficiente y submódulo incorrecto. Los casos permitidos se detienen al conceder autorización; no certifican el flujo contable completo de las 21 operaciones.
- Ocho pruebas del comparador de históricos: detecta modificaciones aunque el número de registros no cambie, borrados, pérdida de tablas/columnas y preservación de archivos.
- Nuevas comprobaciones de filtrado SQL y selección efectiva de la ruta aislada.
- Arranque real con Streamlit AppTest: login sin credenciales y navegación administrativa de prueba por los nueve módulos principales sin excepciones. La sesión administrativa se preparó en el entorno local; no fue un login real en Supabase.
- Integridad SQLite correcta y sin infracciones de claves foráneas en el respaldo.
- Auditoría disponible: sin sobreaplicaciones ni referencias huérfanas de pagos/documentos.
- Nueve períodos de nómina revisados con asientos cuadrados y liquidaciones contabilizadas.
- Ensayo de migración de permisos idempotente y ensayo de respaldo/restauración correctos.
- Comparación de todas las columnas originales de las 57 tablas de negocio antes y después de la navegación y migraciones: sin cambios en el contenido original. Se excluye la tabla interna `sqlite_sequence`.
- Cuatro cartolas conciliadas sin asiento directo: una de tipo `ASIENTOS_EXISTENTES` y tres `CHEQUE_PROTESTADO`. Requieren revisar sus vínculos; este hallazgo no demuestra por sí solo un error.
- Bases, documentos privados y credenciales permanecen fuera del repositorio.

## Pendientes y criterios de cierre

1. Interfaz: conservar la aprobación del propietario; sin rediseño.
2. Usuarios: completar autorización de todas las consultas y escrituras restantes, incluida lógica embebida en pantallas; probar sesiones reales de Supabase, revocación, cambio inicial de clave y aislamiento. Mantener la barrera general de empleados.
3. Balance de ocho columnas: pendiente de implementación/verificación específica; el informe actual no acredita ese requisito.
4. Tesorería: pendiente del flujo completo, adjuntos Excel, navegación, confirmación y pruebas de éxito/reintento.
5. Bancos: nuevas barreras verificadas; faltan flujos completos autorizados, importación/reimportación, reversos y trazabilidad de cartolas.
6. Compras/OC: pendiente de regresión funcional completa, impresión y vínculos con compras.
7. Nómina: se conserva el flujo existente; auditoría histórica correcta, pero faltan flujos integrales de acceso y operación.
8. Históricos: comparación local correcta con el respaldo recibido; repetir ante nuevos cambios y antes de liberar.
9. Identidad: pendiente de revisión de referencias visibles SGCI; preservar identificadores técnicos.
10. Integrales: suite y navegación local correctas; faltan flujos completos y validación de staging con autenticación real.
11. Producción: recuperación local ensayada; completar respaldo operativo, reversión, configuración, persistencia y lista final de despliegue.

Render pruebas: servicio `srv-dbpmvecipgvc73fv1jsg`, rama de integración, disco independiente `/var/contem-pruebas`, despliegue automático desactivado. Producción: rama `main`, disco `/var/data`, despliegue automático activo. Estos datos describen la configuración consultada; no certifican variables secretas, rutas efectivas del servicio en ejecución ni autenticación real. No desplegar pruebas hasta verificar aislamiento y configuración; producción requiere autorización expresa.
