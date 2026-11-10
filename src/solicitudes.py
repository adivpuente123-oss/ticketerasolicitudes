"""Reglas de las solicitudes web y de recopilación de datos del expediente."""
import re
import db
from archivos import validar_adjuntos
from config import CARTERAS, TIPOS_CONSULTA, TIPO_TRANSACCION


class SolicitudDuplicada(ValueError):
    pass


def registrar_solicitud(actor_id, supervisor_id, *, asunto, cartera, tipo, documento='', cuenta='', descripcion='',
                        nombre_cliente='', numero_expediente='', juzgado='', materia='', datos_incompletos=False,
                        adjuntos=None, forzar=False):
    actor = db.usuario_por_id(actor_id)
    supervisor = db.usuario_por_id(supervisor_id) if supervisor_id else None
    if not actor or not actor['activo']:
        raise PermissionError('Tu sesión ya no tiene acceso.')
    if actor['rol'] != 'backoffice' and supervisor_id != actor_id:
        raise PermissionError('Solo puedes registrar tus propias solicitudes.')
    if not supervisor or not supervisor['activo'] or supervisor['rol'] != 'supervisor':
        raise ValueError('Selecciona un supervisor activo para esta solicitud.')
    if cartera not in CARTERAS or tipo not in TIPOS_CONSULTA:
        raise ValueError('Selecciona una cartera y un tipo válidos.')
    asunto, documento, cuenta, descripcion = asunto.strip(), documento.strip(), cuenta.strip(), descripcion.strip()
    legales = {k: v.strip() for k, v in {'nombre_cliente': nombre_cliente, 'numero_expediente': numero_expediente,
                                       'juzgado': juzgado, 'materia': materia}.items()}
    if not asunto or len(asunto) > 160:
        raise ValueError('Escribe un asunto de hasta 160 caracteres.')
    if len(descripcion) > 5000 or len(cuenta) > 30 or any(len(v) > 200 for v in legales.values()):
        raise ValueError("Revisa la longitud de la descripción y los datos de la solicitud.")
    if not descripcion:
        raise ValueError('Describe la atención que necesitas.')
    archivos = validar_adjuntos(adjuntos or [])
    transaccion = tipo == TIPO_TRANSACCION
    if transaccion:
        if documento and not re.fullmatch(r'\d{8}', documento):
            raise ValueError('El DNI debe tener 8 dígitos, o quedar vacío si adjuntas el expediente por datos incompletos.')
        if datos_incompletos:
            if not archivos:
                raise ValueError('Adjunta al menos un documento del expediente cuando falte información.')
        elif not documento or not all(legales.values()):
            raise ValueError('Completa DNI, nombre, número de expediente, juzgado y materia, o indica que faltan datos y adjunta el expediente.')
    else:
        datos_incompletos = False
        legales = dict.fromkeys(legales, '')
        if not documento or not cuenta:
            raise ValueError('El documento y la cuenta son obligatorios.')
        if not re.fullmatch(r'[0-9A-Za-z]{6,15}', documento):
            raise ValueError('El documento debe tener entre 6 y 15 letras o números.')
    if transaccion and documento and legales["numero_expediente"]:
        with db.conexion() as con:
            repetidas = [r["codigo"] for r in con.execute("SELECT codigo FROM tickets WHERE documento=? AND numero_expediente=? AND tipo_consulta=? AND estado<>'Respondida'", (documento, legales["numero_expediente"], TIPO_TRANSACCION))]
    else:
        repetidas = db.abiertas_por_documento(documento, cuenta) if documento else []
    if repetidas and not forzar:
        raise SolicitudDuplicada(('Ya hay solicitudes abiertas para ese DNI y expediente: ' if transaccion else 'Ya hay solicitudes abiertas para ese documento y cuenta: ') + ', '.join(repetidas) + '. Revisa el ticket o confirma que necesitas registrar otra solicitud.')
    return db.crear_ticket(supervisor_id, cartera, tipo, documento, cuenta, descripcion, origen='web',
                           usuario_id=actor_id, asunto=asunto, datos_incompletos=int(datos_incompletos),
                           adjuntos=adjuntos or [], **legales)
