"""Administración local de la misma base de usuarios, sin guardar claves en código."""
import argparse
import getpass
import re
import db


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="accion", required=True)
    sub.add_parser("listar")
    editar = sub.add_parser("editar")
    editar.add_argument("id", type=int)
    editar.add_argument("--nombre")
    editar.add_argument("--correo")
    editar.add_argument("--rol", choices=["supervisor", "backoffice"])
    estado = editar.add_mutually_exclusive_group()
    estado.add_argument("--activar", action="store_true")
    estado.add_argument("--desactivar", action="store_true")
    editar.add_argument("--cambiar-clave", action="store_true", help="Pedir nueva contraseña de forma oculta")
    args = parser.parse_args()
    db.iniciar()
    if args.accion == "listar":
        for _, u in db.usuarios_df().iterrows():
            print(f"{u['id']} | {u['nombre']} | {u['correo'] or '-'} | {u['rol']} | {'Activo' if u['activo'] else 'Inactivo'}")
        return
    u = db.usuario_por_id(args.id)
    if not u:
        parser.error("El usuario no existe.")
    nombre = args.nombre.strip() if args.nombre is not None else u["nombre"]
    correo = args.correo.strip() if args.correo is not None else u["correo"]
    if not nombre or (correo and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo)):
        parser.error("Nombre o correo inválido.")
    clave = None
    if args.cambiar_clave:
        clave = getpass.getpass("Nueva contraseña: ")
        repetida = getpass.getpass("Repite la contraseña: ")
        if len(clave) < 8 or clave != repetida:
            parser.error("La contraseña debe tener al menos 8 caracteres y coincidir.")
    activo = False if args.desactivar else True if args.activar else bool(u["activo"])
    rol = args.rol or u["rol"]
    if u["rol"] == "backoffice" and (not activo or rol != "backoffice"):
        with db.conexion() as con:
            otros = con.execute("SELECT count(*) FROM usuarios WHERE id<>? AND rol='backoffice' AND activo=1 AND clave_hash IS NOT NULL", (args.id,)).fetchone()[0]
        if not otros:
            parser.error("Conserva al menos un administrador activo.")
    try:
        db.actualizar_usuario(args.id, nombre, correo, rol, activo, clave)
    except Exception as exc:
        parser.error(f"No se pudo guardar el usuario ({type(exc).__name__}).")
    print("Usuario actualizado en la base de datos del portal.")


if __name__ == "__main__":
    main()
