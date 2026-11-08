# Ticketera de solicitudes

Portal web para supervisores y back office, basado en la aplicación del ZIP original.

- Cada supervisor inicia sesión y ve únicamente sus solicitudes.
- Solicitudes desde la web o desde el correo, con código SOL-0001.
- Estados: Recibida → Enviada a verificar → Respondida.
- Listado y detalle del supervisor se actualizan cada 5 segundos; no es una conexión push instantánea.
- Conversación por ticket. Responder por correo conservando [SOL-0001] añade un mensaje al mismo ticket.
- Avisos por correo al registrar solicitudes, cambiar estados o escribir desde la web.
- Historial, filtros y exportación; se conserva el dashboard anterior y la importación de Excel.
- Cola persistente: un error de correo no pierde el ticket. Los envíos ambiguos requieren revisión para evitar duplicados.

**Estado de entrega:** código preparado para servidor. El repositorio de GitHub no publica por sí solo la aplicación. Sin alojamiento y autorización de Microsoft 365 no existe una URL pública operativa ni correo activo.

## Prueba local en Windows

Instala Python 3.12. Ejecuta `instalar.bat` y después `iniciar_plataforma.bat`.
Abre http://localhost:8502. Crea el administrador con tu correo `adiv.puente@goexpertis.com` y una contraseña propia. En Usuarios crea las cuentas de los supervisores con sus correos.

No hay usuarios ni contraseñas precargados. No se incluyen datos reales.

## Publicar en Internet

Esta aplicación necesita un servidor de Python con almacenamiento persistente. No funciona como página estática en GitHub Pages. El archivo Dockerfile y compose.yaml permiten desplegarla en un servidor Linux con Docker Compose, sin Outlook de escritorio.

1. Provisiona un servidor y un dominio/subdominio. El coste depende del proveedor; este proyecto no contrata servicios automáticamente.
2. Apunta el DNS del dominio al servidor y habilita los puertos 80 y 443.
3. Clona este repositorio en el servidor. Copia `.env.example` a `.env`.
4. Configura DOMAIN y PORTAL_URL. Genera SETUP_TOKEN con al menos 24 caracteres aleatorios; por ejemplo `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Guarda el resultado en el gestor de secretos del servidor.
5. Deja CORREO_MODO=desactivado hasta completar los permisos de Microsoft 365.
6. Ejecuta `docker compose up -d --build`. Caddy gestiona HTTPS para el dominio configurado.
7. Abre tu dominio, introduce el código de instalación y crea al administrador. Después registra a los supervisores.
8. Configura el correo según la sección siguiente y reinicia con `docker compose up -d --force-recreate portal`.

Ejecuta UNA instancia del portal con su servicio de correo y su disco persistente; SQLite no debe colocarse en una unidad de red ni compartirse entre servidores. El volumen `tickets` guarda la base. No ejecutes `docker compose down -v` con datos que quieras conservar. Haz copias consistentes usando la API de backup de SQLite o deteniendo el servicio antes de copiar el volumen. Conserva también el disco durante actualizaciones.

## Microsoft 365 para servidor (TI)

Buzón: **adiv.puente@goexpertis.com**. No se usa la contraseña del correo.

Un administrador de Microsoft 365 debe:

1. Registrar una aplicación de servidor en Microsoft Entra ID.
2. Autorizar lectura y actualización de mensajes y envío como aplicación (Microsoft Graph: Mail.ReadWrite y Mail.Send, con consentimiento administrativo).
3. Limitar el acceso efectivo de esa aplicación al buzón de atención mediante la política o el control de acceso de Exchange correspondiente. Verificar ese alcance con TI antes de activarla.
4. Crear una credencial de aplicación y cargar MS_TENANT_ID, MS_CLIENT_ID y MS_CLIENT_SECRET directamente como secretos del alojamiento. Nunca en GitHub ni en el chat. Planificar la rotación al caducar.
5. Crear en el buzón la subcarpeta **Solicitudes** de la Bandeja de entrada. Configurar una regla para mover allí las solicitudes y respuestas de supervisores. No dirigir los propios avisos automáticos a esa carpeta.
6. Configurar CORREO_MODO=graph. Opcional: MS_FOLDER_ID para identificar explícitamente otra carpeta.

El servicio revisa esa carpeta cada 15 segundos. Los remitentes deben coincidir con usuarios activos registrados; un supervisor no puede responder en el ticket de otro supervisor. Las respuestas del back office se añaden a la conversación y el estado final se registra desde Gestionar. Los mensajes con destinatarios no registrados se categorizan SIN TICKET; después de registrar al usuario, quita esa categoría para volver a procesarlos.

Los correos se convierten en tickets por su asunto y cuerpo. **Los archivos adjuntos del correo no se importan en esta versión.** Las cadenas de correo se vinculan por [SOL-0001] en el asunto; si se quita la referencia, se tratará como solicitud nueva. El cuerpo completo del correo puede incluir texto citado de respuestas anteriores.

Ejemplo:

```
Asunto: Validar cancelación
Cartera: IBK
Tipo de consulta: Canceló con entidad original
DNI: 12345678
Cuenta: 0001234567
Descripción de la atención requerida.
```

En Correo de atención se ve la última revisión y los 100 últimos envíos. `aceptado_microsoft` significa que Graph aceptó la solicitud, no que el destinatario la recibió. Para `revisar` o `procesando` tras una interrupción, consulta Enviados antes de volver a ponerlo en cola. Revisa también los registros del servidor y eventuales mensajes de no entrega.

Referencias de Microsoft: [autenticación de servidor](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow), [lectura de mensajes](https://learn.microsoft.com/en-us/graph/api/mailfolder-list-messages?view=graph-rest-1.0), [envío](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0).

## Alternativa: Outlook clásico en Windows

Con el mismo directorio y base del portal en un equipo Windows, instala y configura Outlook clásico con la cuenta de atención. Crea la carpeta Solicitudes y su regla; ejecuta `iniciar_correo.bat`. El equipo y Outlook deben permanecer abiertos. Esta alternativa no funciona con el nuevo Outlook y no debe ejecutarse a la vez que el servicio Graph sobre el mismo buzón. `src/leer_outlook.py` se conserva por compatibilidad; usa el nuevo servicio para el flujo bidireccional.

## Datos y mantenimiento

`db/plataforma.db` contiene usuarios, solicitudes, historial, mensajes y cola. No subirla a GitHub. Las contraseñas se guardan con PBKDF2 y sal aleatoria. Crea el administrador antes de habilitar acceso a los supervisores. En producción conserva SETUP_TOKEN en el servidor; no lo incluyas en enlaces públicos. Las exportaciones y los mensajes pueden contener información del negocio: compártelos según las reglas de tu organización.

Para migrar una base de la versión anterior: haz un backup y utiliza el mismo RUTA_DB; al arrancar se crean las tablas adicionales sin borrar las existentes.

## Verificación

```
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m compileall -q app src servidor.py
```

Las pruebas usan datos ficticios y adaptadores simulados. No sustituyen la prueba de entrega real con un buzón autorizado. Docker/HTTPS requieren validación en el servidor elegido.

## Interfaz corporativa
El portal incluye acceso con fotografía arquitectónica propia, navegación con etiquetas e iconos vectoriales, tarjetas adaptables, estados legibles y controles visibles. El tema se define en app/portal.css y .streamlit/config.toml. Los recursos visuales se guardan en app/assets; no dependen de páginas externas.

