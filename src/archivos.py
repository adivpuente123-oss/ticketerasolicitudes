"""Validación de adjuntos de expedientes, sin depender de rutas del navegador."""
import re

MAX_ARCHIVOS = 5
MAX_POR_ARCHIVO = 10 * 1024 * 1024
MAX_TOTAL = 30 * 1024 * 1024
FORMATOS = {'.pdf': ('application/pdf', b'%PDF-'), '.png': ('image/png', b'\x89PNG\r\n\x1a\n'),
            '.jpg': ('image/jpeg', b'\xff\xd8\xff'), '.jpeg': ('image/jpeg', b'\xff\xd8\xff')}


def validar_adjuntos(archivos):
    if len(archivos) > MAX_ARCHIVOS:
        raise ValueError('Puedes adjuntar hasta 5 archivos por solicitud.')
    preparados, total = [], 0
    for archivo in archivos:
        nombre = re.sub(r'[\x00-\x1f\x7f]', '', str(archivo['nombre']).replace('\\', '/').split('/')[-1]).strip()
        if not nombre or len(nombre) > 160:
            raise ValueError('El nombre de uno de los archivos no es válido (máximo 160 caracteres).')
        extension = '.' + nombre.rsplit('.', 1)[-1].lower()
        datos = archivo['datos']
        if not isinstance(datos, bytes) or not datos:
            raise ValueError(f'El archivo {nombre} está vacío.')
        if len(datos) > MAX_POR_ARCHIVO:
            raise ValueError(f'{nombre} supera el máximo de 10 MB.')
        if extension not in FORMATOS or not datos.startswith(FORMATOS[extension][1]):
            raise ValueError(f'{nombre}: adjunta un PDF, PNG o JPG válido.')
        total += len(datos)
        if total > MAX_TOTAL:
            raise ValueError('Los archivos no deben superar 30 MB en total.')
        preparados.append({'nombre': nombre, 'datos': datos, 'tipo_mime': FORMATOS[extension][0], 'tamano': len(datos)})
    return preparados
