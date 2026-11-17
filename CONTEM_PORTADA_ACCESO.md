# CONTEM — nueva portada de acceso

Portada de dos paneles con identidad esmeralda/lima, logotipo vectorial compatible con la marca y una ilustración original de panel financiero, gráficos y documentos. El formulario conserva los campos, claves y validaciones de acceso, recuperación de contraseña y respaldo administrativo. Se simplifican los textos visibles de infraestructura sin modificar autenticación ni solicitudes al proveedor.

La presentación se aplica exclusivamente cuando no hay sesión válida. En pantallas pequeñas se compacta la introducción para priorizar el formulario. No se consultan datos de negocio ni se incluyen recursos externos o cifras reales en la ilustración. No cambia la navegación del sistema autenticado.

Validación local: 689 pruebas existentes correctas. AppTest recorrió las tres opciones de acceso sin excepciones, confirmó que no hay navegación sin autenticación y rechazó el formulario vacío. Son pruebas de comportamiento, no una comprobación visual en todos los navegadores. Vista previa HTML demostrativa disponible localmente, con campos deshabilitados, creada con la misma ilustración y estilos; el formulario real sigue siendo nativo de Streamlit.

Archivos del cambio: modulos/portada_acceso.py (nuevo), modulos/configuracion.py, tests/test_login_cerrado.py y este documento. El ajuste de la prueba adapta el doble de columnas a la nueva distribución. Sin cambios contables, de permisos, base de datos o configuración de Render. Pendiente aprobación visual y publicación. Producción conserva la portada anterior.
