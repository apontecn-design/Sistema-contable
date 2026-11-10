# CONTEM V1.0 — criterios de liberación

**Estado:** candidato en revisión, NO apto todavía para fusionar en `main` ni desplegar en Render.

## Verificaciones automatizadas

- [x] Sintaxis Python de componentes, aplicación y pruebas (GitHub Actions).
- [x] Pruebas de permisos de perfil, excepciones individuales y usuarios inactivos.
- [x] Barreras de acciones críticas en pantallas de Compras, Ventas, Bancos y Contabilidad.
- [x] Pruebas de autorización dentro de la función de contabilización de Tesorería.
- [x] Arranque Streamlit sin sesión y sin acceso autenticado.
- [ ] Confirmar ejecución verde del commit final de esta rama.

## Bloqueantes para producción

- [ ] Probar flujos de extremo a extremo: compras/ventas RCV, pago parcial, reversos, conciliación, cierre y reapertura.
- [ ] Probar doble contabilización y reintentos de pago con SQLite transaccional.
- [ ] Auditar TODAS las funciones que mutan datos; las barreras de pantalla no sustituyen la autorización en la capa de servicio.
- [ ] Confirmar permisos de cada empleado fuera de RR. HH. y restricciones «Solo mis datos» dentro de RR. HH.
- [ ] Eliminar el puente de ejecución secuencial y dependencias globales entre módulos.
- [ ] Probar migración sobre copia reciente de la base real, comprobar integridad y conciliación de saldos antes/después.
- [ ] Realizar prueba de despliegue en entorno aislado, con plan de reversión verificado.

## Protección de datos

- No añadir `.db`, respaldos, credenciales ni comprobantes bancarios al repositorio.
- Mantener `main` y Render sin cambios hasta completar la lista y recibir autorización expresa de despliegue.
- Mantener respaldo de producción externo a GitHub.

**Importante:** una ejecución verde de CI demuestra solo lo cubierto por las pruebas. No acredita la integridad contable completa ni la seguridad integral del producto.
