"""Genera el ZIP de despliegue para Elastic Beanstalk usando una LISTA BLANCA de archivos.

Uso: python empaquetar_eb.py [destino.zip]   (defecto: dist/consulta-np-eb.zip)

Solo empaqueta el codigo necesario (nunca .env, .venv, .git, pruebas ni datos), con los archivos
en la raiz del ZIP y rutas con "/". Empaqueta el directorio de trabajo actual (incluye cambios sin
commit): revise el manifiesto impreso antes de subirlo. No se conecta a AWS.
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path
from typing import BinaryIO

RAIZ = Path(__file__).resolve().parent
INCLUIR = ("Procfile", "run.py", "requirements.txt", "consulta_np", ".ebextensions", ".platform")
OBLIGATORIOS = ("Procfile", "run.py", "requirements.txt", "consulta_np/__init__.py")
_IGNORAR = re.compile(r"(^|/)__pycache__/|\.py[cod]$")
_PROHIBIDOS = re.compile(
    r"(^|/)\.env($|[./])|(^|/)\.venv/|(^|/)\.git/|\.(pem|key|pfx|p12|zip|xlsx|xls|xlsm|csv|log)$",
    re.IGNORECASE,
)


class ErrorPaquete(RuntimeError):
    pass


def validar_ruta(relativa: str) -> None:
    if _PROHIBIDOS.search(relativa):
        raise ErrorPaquete(f"Archivo no permitido en el paquete: {relativa}")


def listar_archivos(raiz: Path = RAIZ) -> list[str]:
    """Rutas relativas (con "/") que iran en el ZIP. Falla si encuentra algo prohibido."""
    archivos: list[str] = []
    for entrada in INCLUIR:
        ruta = raiz / entrada
        if ruta.is_symlink():
            raise ErrorPaquete(f"No se permiten enlaces simbolicos: {entrada}")
        if ruta.is_file():
            candidatos = [ruta]
        elif ruta.is_dir():
            candidatos = sorted(p for p in ruta.rglob("*") if p.is_file() or p.is_symlink())
        else:
            raise ErrorPaquete(f"Falta {entrada} en {raiz}")
        for archivo in candidatos:
            relativa = archivo.relative_to(raiz).as_posix()
            if _IGNORAR.search(relativa):
                continue
            if archivo.is_symlink():
                raise ErrorPaquete(f"No se permiten enlaces simbolicos: {relativa}")
            validar_ruta(relativa)
            archivos.append(relativa)
    faltantes = [o for o in OBLIGATORIOS if o not in archivos]
    if faltantes:
        raise ErrorPaquete("Faltan archivos obligatorios: " + ", ".join(faltantes))
    return archivos


def crear_zip(destino: str | Path | BinaryIO, raiz: Path = RAIZ) -> list[str]:
    archivos = listar_archivos(raiz)
    with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_DEFLATED) as paquete:
        for relativa in archivos:
            paquete.write(raiz / relativa, relativa)
    return archivos


def main(argv: list[str]) -> int:
    destino = Path(argv[0]) if argv else RAIZ / "dist" / "consulta-np-eb.zip"
    destino = destino.resolve()
    if destino.suffix.lower() != ".zip":
        print("El destino debe terminar en .zip", file=sys.stderr)
        return 2
    for entrada in INCLUIR:
        if destino.is_relative_to(RAIZ / entrada):
            print(f"El destino no puede estar dentro de {entrada}", file=sys.stderr)
            return 2
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        archivos = crear_zip(destino)
    except ErrorPaquete as error:
        destino.unlink(missing_ok=True)
        print(f"Paquete NO generado: {error}", file=sys.stderr)
        return 1
    print("Manifiesto del paquete:")
    for relativa in archivos:
        print(f"  {relativa}")
    print(f"{len(archivos)} archivos -> {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
