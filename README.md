# Ticketera de solicitudes

Portal web para supervisores y back office, basado en la aplicación del ZIP original.

- Cada supervisor inicia sesión y ve únicamente sus solicitudes.
- Solicitudes desde la web o desde el correo, con código SOL-0001.
- Estados: Recibida → Enviada a verificar → Respondida.
- Listado y detalle del supervisor se actualizan cada 5 segundos; no es una conexión push instantánea.
- Conversación por ticket. Responder por correo conservando [SOL-0001] añade un mensaje al mismo ticket.
- Avisos en Borradores al registrar solicitudes, cambiar estados o escribir desde la web. Se revisan y envían manualmente desde Outlook; no hay envío automático.
- Historial, filtros y exportación; se conserva el dashboard anterior y la importación de Excel.
- Cola persistente: un error de correo no pierde el ticket. Los envíos ambiguos requieren revisión para evitar duplicados.

**Estado de entrega:** código preparado para servidor. El repositorio de GitHub no publica por sí solo la aplicación. Sin alojamiento y autorización de Microsoft 365 no existe una URL pública operativa ni correo activo.

## Prueba local en Windows

Instala Python 3.12. Ejecuta `instalar.bat` y después `iniciar_plataforma.bat`. Este último inicia el servidor con sesión persistente.
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

En Correo de atención se ve la última revisión y los 100 últimos envíos. `borrador` significa que el aviso está preparado para revisión manual. Para `revisar` o `procesando` tras una interrupción, consulta Borradores y Enviados antes de volver a ponerlo en cola. Revisa también los registros del servidor y eventuales mensajes de no entrega.

Referencias de Microsoft: [autenticación de servidor](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow), [lectura de mensajes](https://learn.microsoft.com/en-us/graph/api/mailfolder-list-messages?view=graph-rest-1.0), [envío](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0).

## Alternativa: Outlook clásico en Windows

Con el mismo directorio y base del portal en un equipo Windows, instala y configura Outlook clásico con la cuenta de atención. Crea la carpeta Solicitudes y su regla; ejecuta `iniciar_correo.bat`. El equipo y Outlook deben permanecer abiertos. Esta alternativa no funciona con el nuevo Outlook y no debe ejecutarse a la vez que el servicio Graph sobre el mismo buzón. `src/leer_outlook.py` se conserva por compatibilidad; usa el nuevo servicio para el flujo bidireccional.

## Revisión manual de correo

Los servicios Outlook y Graph guardan los avisos en **Borradores** del buzón de atención; nunca los envían automáticamente. El estado `borrador` en Correo de atención solo confirma su preparación. Abre Outlook, revisa destinatario y texto, y pulsa Enviar cuando corresponda. El portal no detecta después ese envío manual.

La confirmación es: «Tu solicitud SOL-0001 fue recibida. La revisaremos pronto.» En Outlook clásico se prepara con Responder sobre la solicitud original, conservando el hilo y el código en el asunto. Conserva el original en Solicitudes hasta que se genere el borrador. Los avisos al equipo y las solicitudes web se preparan como mensajes nuevos. Graph prepara mensajes nuevos con el código del ticket.

Los avisos pendientes anteriores también pasarán a Borradores. Si ocurre un error, revisa Borradores antes de reencolar para evitar duplicados. Detén el lector anterior antes de actualizar y reinícialo después: un proceso antiguo seguirá usando el comportamiento anterior.

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


## Gestión de usuarios

En Usuarios, selecciona una cuenta en «Crear o editar usuario» para modificar nombre, correo, rol o estado. Para cambiar su contraseña, escribe la nueva (mínimo 8 caracteres) y repítela; deja ambos campos vacíos para conservarla. Pulsa Guardar usuario.

Back office puede borrar solicitudes desde el botón Borrar de cada solicitud en el listado y confirmar en el listado. Se eliminan también sus mensajes, historial y avisos de correo de la plataforma.

Al eliminar un usuario, elige si deseas borrar también todas sus solicitudes. Con Sí y la confirmación se borran la cuenta, sus solicitudes y sus registros asociados en una sola operación. Con No, se elimina la cuenta y se conservan las solicitudes sin usuario asociado. No puedes eliminar tu propia cuenta. Los correos y borradores que ya existen en Outlook no se eliminan; se conserva únicamente una huella del identificador del correo para evitar que el lector vuelva a importar las solicitudes borradas.

## Notificaciones en el portal

El centro de notificaciones muestra un contador de avisos no leídos y permite abrir el ticket o marcar todos como leídos. Los avisos quedan guardados por usuario y se actualizan cada 5 segundos mientras el portal está abierto. Al llegar actividad nueva aparece un aviso emergente. No son notificaciones del navegador con la aplicación cerrada.

Se generan avisos por nuevas solicitudes, mensajes de conversación (web o correo) y cambios del ticket. El autor no recibe su propio aviso; back office recibe actividad de todas las solicitudes y cada supervisor solo la de sus tickets. Se generan a partir de la actualización, sin avisos retroactivos. Al borrar una solicitud o usuario se eliminan sus notificaciones asociadas.

El listado usa tarjetas blancas con borde definido y sombra sobre un fondo más oscuro para distinguir cada solicitud. La campana muestra una insignia roja con los avisos pendientes (99+ a partir de cien); el texto accesible conserva el número exacto. La actividad nueva genera un aviso flotante verde de mayor duración, sin marcarla como leída automáticamente.

La pestaña Solicitudes presenta el listado sin el banner de Centro de atención. La campana es un icono sin marco rectangular, con contador rojo de pendientes. El menú solo muestra avisos sin leer: al pulsar Ver ticket o Marcar todas como leídas desaparecen de ese menú y no se muestra un historial de leídos.

## Vista compacta de solicitudes

El panel muestra tres indicadores: Pendientes (solicitudes aún no respondidas), Aprobadas (respondidas con conclusión PROCEDENTE) y Rechazadas (respondidas con conclusión IMPROCEDENTE). Una solicitud respondida sin conclusión no cuenta como aprobada ni rechazada.

Gestión de solicitudes reúne buscador, filtro por estado, filtros adicionales y exportación CSV del resultado filtrado. Las filas muestran ticket, supervisor, cartera, consulta y estado con color; el icono del ojo abre el detalle y la papelera conserva la confirmación de borrado. Se mantiene la campana, los permisos y los avisos. En móviles la tabla permite desplazamiento horizontal.

## Sesión persistente y datos de usuarios

Los usuarios, correos y hashes de contraseña se guardan en `db/plataforma.db` (o `RUTA_DB`). Ya persisten al recargar y reiniciar. Conserva esa carpeta al actualizar; Docker utiliza el volumen persistente `tickets`. La contraseña original no se almacena ni se puede consultar: se reemplaza por una nueva desde Usuarios.

Inicia con `iniciar_plataforma.bat`, `iniciar_plataforma_red.bat` o `python servidor.py`. El servidor mantiene una cookie HttpOnly, SameSite=Lax, durante 12 horas y guarda solo la huella del token en la base de datos. Recargar, cerrar y abrir el navegador o reiniciar el portal conserva el acceso durante ese plazo. Cerrar sesión revoca el token. Cambiar correo, contraseña, rol o desactivar un usuario revoca sus sesiones. Eliminarlo también elimina sus sesiones.

Después de actualizar esta versión, detén el portal anterior, ejecuta `instalar.bat` (o `python -m pip install -r requirements.txt`) e inicia el portal de nuevo. El primer acceso requiere ingresar una vez. No uses directamente `streamlit run app/plataforma.py` para el portal: ese comando omite el servidor de cookies y conserva únicamente el acceso temporal para desarrollo.

El puerto público es `PORT` (8502 por defecto); Streamlit queda en 127.0.0.1 en `PORT_INTERNO` (por defecto PORT + 1), que debe estar libre. En local el portal escucha solo en localhost; `iniciar_plataforma_red.bat` permite la red local. En alojamiento, `PORTAL_CLOUD=1` activa cookies Secure y requiere HTTPS, como el Caddy de Docker Compose. Mantén una sola instancia con su base persistente.

### Administrar desde la terminal

Es viable modificar la misma base desde un script, sin editar ni subir contraseñas al código. La herramienta local utiliza la misma `RUTA_DB` que el portal:

```bash
python src/administrar_usuarios.py listar
python src/administrar_usuarios.py editar 3 --correo nuevo@ejemplo.com
python src/administrar_usuarios.py editar 3 --cambiar-clave
```

El último comando pide la contraseña dos veces de forma oculta; no la escribas como argumento ni en archivos Python. También admite `--nombre`, `--rol`, `--activar` y `--desactivar`. Necesita acceso al archivo de base de datos del servidor: usa solo la terminal de administración autorizada. Los cambios aparecen en la aplicación al actualizarla. Para despliegues Docker ejecuta la herramienta dentro del contenedor del portal para usar el mismo volumen. No edites `clave_hash` a mano ni guardes usuarios reales como constantes en GitHub.
