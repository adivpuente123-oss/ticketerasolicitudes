# Publicar con Render Free y Supabase Free

Esta guía no crea cuentas ni contrata servicios. Los secretos se introducen en los paneles privados de cada proveedor. No los envíes por chat ni los subas a GitHub. Conserva la carpeta `db` de tu PC hasta terminar la migración y verificar un respaldo.

## 1. Preparar Supabase

1. Crea una cuenta en https://supabase.com y un proyecto del plan Free. Guarda la contraseña de la base en tu gestor de contraseñas y elige una región próxima a tus usuarios.
2. En **Storage**, crea el bucket `expedientes` con **Public bucket desactivado**. Permite PDF, PNG y JPEG y un tamaño máximo de 10 MB por objeto. No añadas políticas de acceso anónimo: el portal valida la sesión y los permisos y accede desde el servidor.
3. En **Connect**, copia la conexión PostgreSQL del **pooler** compatible con IPv4. El pooler de sesión es adecuado para pocos usuarios; el de transacción también es compatible (el cliente desactiva sentencias preparadas). Usa exactamente el usuario y puerto mostrados, y añade `sslmode=require` a la cadena. Si escribes la contraseña en una URL, sus caracteres especiales deben estar codificados como URL. No uses una conexión directa que solo admita IPv6 desde un alojamiento con salida IPv4.
4. Obtén la URL del proyecto (`https://...supabase.co`) y la clave **legacy `service_role`** del servidor en los ajustes de API Keys. No uses la clave pública `anon`. La clave privilegiada solo va en las variables privadas del servidor.

El portal crea sus tablas en el esquema `ticketera`, separado de `public`, y revoca acceso al esquema a `PUBLIC`. No añadas `ticketera` a los esquemas expuestos de la API de Supabase. El acceso de usuarios se gestiona con las cuentas del portal; no se crean cuentas de Supabase Auth para los supervisores.

## 2. Preparar Render

Después de incorporar esta propuesta a `main`:

1. Crea una cuenta en https://render.com y conecta GitHub autorizando este repositorio.
2. Selecciona **New → Blueprint** y el repositorio `ticketerasolicitudes`.
3. Verifica que se muestre el plan **Free**, sin disco persistente de pago. Si Render ofrece condiciones distintas, detente antes de aceptar cualquier cobro.
4. Introduce estas variables privadas:

| Variable | Valor |
| --- | --- |
| `DATABASE_URL` | Conexión PostgreSQL del pooler, con TLS |
| `SUPABASE_URL` | URL HTTPS del proyecto |
| `SUPABASE_SERVICE_ROLE_KEY` | Clave legacy `service_role` del servidor |
| `SUPABASE_STORAGE_BUCKET` | `expedientes` |
| `EXIGIR_DB_REMOTA` | `1` (incluida en el Blueprint) |
| `PORTAL_CLOUD` | `1` (incluida en el Blueprint) |
| `CORREO_MODO` | `desactivado` inicialmente |

`SETUP_TOKEN` se genera automáticamente. El portal comprueba que el bucket sea privado al arrancar. Si falta la conexión remota, se detiene para evitar guardar datos en el disco efímero.

5. Render instalará las dependencias y ejecutará `servidor.py`. Abre la URL HTTPS que asigne. No ejecutes los `.bat` en el alojamiento. La URL no cambia con cada actualización.
6. **Si vas a migrar tus datos locales, no completes la instalación ni crees el administrador en la web todavía.** El destino debe estar vacío. Si partes de cero, consulta `SETUP_TOKEN` en Render y crea al administrador desde la pantalla de instalación.

## 3. Migrar usuarios, solicitudes y documentos existentes

Hazlo desde la PC que contiene tu base real, con esta versión del repositorio y sus dependencias instaladas. El ejemplo usa PowerShell y la carpeta del proyecto. No pegues claves reales en documentación, capturas ni GitHub.

1. Cierra el portal local y el lector de Outlook para detener nuevas escrituras. No dejes al equipo usando la copia local durante el traslado.
2. En una ventana de PowerShell, introduce los secretos sin mostrarlos:

```powershell
$env:DATABASE_URL = [System.Net.NetworkCredential]::new('', (Read-Host 'Conexión PostgreSQL del pooler con sslmode=require' -AsSecureString)).Password
$env:SUPABASE_URL = Read-Host 'URL HTTPS de Supabase'
$env:SUPABASE_SERVICE_ROLE_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'Clave service_role' -AsSecureString)).Password
$env:SUPABASE_STORAGE_BUCKET = 'expedientes'
.\.venv\Scripts\python.exe src\migrar_supabase.py db\plataforma.db
```

Si tu base está en otra ruta (`RUTA_DB`), sustituye el último argumento. Python no carga `.env` automáticamente. Las variables solo afectan esta ventana; al terminar, ciérrala. No introduzcas estas credenciales en el código.

La herramienta genera una copia consistente de SQLite, aplica las migraciones a esa copia y conserva IDs, códigos, usuarios, hashes de contraseña, solicitudes, documentos, conversaciones, notas, historial y notificaciones. No modifica el origen. Si el destino tiene registros, cancela sin sobrescribirlos. Los archivos pasan al bucket privado con nombres aleatorios. Las sesiones anteriores no se migran: cada usuario inicia sesión de nuevo con su contraseña habitual.

Las entradas de correo pendientes o procesándose pasan a `revisar` para no generar borradores duplicados tras el traslado. El correo permanece desactivado en Render hasta que se autorice y compruebe Microsoft Graph. No se trasladan archivos Excel externos ni configuraciones secretas de correo: no forman parte de la base de tickets.

3. Abre la URL de Render e inicia sesión con una cuenta existente. Comprueba los conteos, conversaciones, notas y varias descargas. Prueba con otro navegador. Los supervisores deben ver solo sus propias solicitudes.
4. Mantén el archivo original y realiza un respaldo completo con el apartado siguiente. Solo entonces retira la copia local del uso diario.

Si la migración falla, no borres la base original ni vuelvas a crear datos manualmente en el destino. Los registros de la operación se revierten y los archivos subidos se intentan retirar. Un corte de proceso puede dejar objetos reservados: su limpieza se reintenta después de 24 horas con el portal activo. Corrige la conexión o configuración antes de repetir.

## 4. Respaldar y recuperar

Los planes gratuitos no sustituyen una política de copias. Con las mismas variables privadas configuradas en PowerShell:

```powershell
.\.venv\Scripts\python.exe src\respaldar_supabase.py C:\Respaldos\ticketera-2026-11-16.db
```

Elige una carpeta existente fuera del repositorio y un nombre distinto para cada copia. El comando no sobrescribe archivos existentes. Exporta los registros y descarga los documentos a una única SQLite que puede abrirse en modo local o restaurarse en un **nuevo destino PostgreSQL vacío** con `migrar_supabase.py`. No incluye sesiones activas; se requiere nuevo inicio de sesión.

Durante el respaldo se bloquean las escrituras para mantener registros y documentos consistentes: ejecútalo en un momento sin uso. Comprueba que puedes abrir la copia y descargar un adjunto antes de confiar en ella. Protege el archivo: contiene datos privados y hashes de contraseña. Guarda otra copia fuera de tu PC (por ejemplo, en un almacenamiento privado de tu organización). La ejecución es manual; no se ha contratado ni programado un servicio automático de copias.

## 5. Límites y operación

- Render Free puede suspender la web por inactividad y tardar en responder al reactivarse. Supabase Free puede pausar proyectos inactivos. Consulta los límites y condiciones vigentes; no se promete disponibilidad continua ni gratuidad ilimitada.
- No uses este despliegue gratuito como garantía de lectura de correo 24/7. El lector funciona solo mientras el servicio está ejecutándose; no se configura tráfico artificial para evitar suspensiones.
- No borres el proyecto de Supabase ni su bucket. Cambiar de navegador, actualizar Render o borrar tu copia local no elimina los datos remotos, pero borrar el proyecto remoto sí puede hacerlo.
- El borrado de una solicitud elimina sus registros y encola el borrado de sus objetos. El servidor reintenta las eliminaciones cada minuto mientras está activo; si está suspendido o Storage falla, quedan pendientes.
- Cada subida registra una reserva durable antes de cargar el objeto. El éxito confirma su referencia en la transacción del ticket; si la operación se corta, la reserva permite limpiar el objeto a partir de 24 horas. Mantén el portal en una sola instancia para esta primera versión.
- Los cambios nuevos se despliegan desde `main` tras las comprobaciones de GitHub. Solo recarga la misma URL después del despliegue. Actualizar el código no sustituye ni reinicializa los registros remotos.

Referencias: [Render Free](https://render.com/docs/free), [Blueprint](https://render.com/docs/blueprint-spec), [conexiones PostgreSQL de Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres), [buckets privados](https://supabase.com/docs/guides/storage/buckets/fundamentals), [planes de Supabase](https://supabase.com/pricing).
