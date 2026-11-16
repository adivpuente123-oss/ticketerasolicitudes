"""Objetos privados de Supabase. La clave de servicio solo se usa en el servidor."""
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


class ErrorAlmacenamiento(RuntimeError):
    pass


def configuracion():
    url = os.getenv('SUPABASE_URL', '').rstrip('/')
    clave = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
    bucket = os.getenv('SUPABASE_STORAGE_BUCKET', 'expedientes')
    if urlparse(url).scheme != 'https' or not urlparse(url).netloc or not clave or not re.fullmatch(r'[a-z0-9-]+', bucket):
        raise ErrorAlmacenamiento('Configura SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY y un bucket privado válido.')
    return url, clave, bucket


def peticion(metodo, ruta, datos=None, tipo='application/json', permitir_404=False):
    url, clave, _ = configuracion()
    req = Request(url + '/storage/v1/' + ruta, data=datos, method=metodo,
                  headers={'Authorization': 'Bearer ' + clave, 'apikey': clave, 'Content-Type': tipo})
    try:
        with urlopen(req, timeout=45) as respuesta:
            return respuesta.read()
    except HTTPError as exc:
        if permitir_404 and exc.code == 404:
            return b''
        raise ErrorAlmacenamiento(f'Supabase Storage no pudo completar la operación (HTTP {exc.code}).') from None
    except (URLError, TimeoutError):
        raise ErrorAlmacenamiento('No se pudo conectar con Supabase Storage. Inténtalo nuevamente.') from None


def comprobar():
    _, _, bucket = configuracion()
    datos = json.loads(peticion('GET', 'bucket/' + bucket))
    if datos.get('public') is not False:
        raise ErrorAlmacenamiento('El bucket de expedientes debe ser privado.')


def subir(clave, datos, tipo):
    _, _, bucket = configuracion()
    peticion('POST', 'object/' + bucket + '/' + quote(clave, safe='/'), datos, tipo)


def descargar(clave):
    _, _, bucket = configuracion()
    return peticion('GET', 'object/authenticated/' + bucket + '/' + quote(clave, safe='/'))


def borrar(clave):
    _, _, bucket = configuracion()
    peticion('DELETE', 'object/' + bucket, json.dumps({'prefixes': [clave]}).encode(), permitir_404=True)
