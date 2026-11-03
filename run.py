"""Punto de entrada: python run.py (sirve con waitress en 127.0.0.1 por defecto)."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from consulta_np.config import ErrorConfiguracion


def cargar_env(ruta: Path) -> None:
    """Carga un archivo .env simple (CLAVE=valor) sin sobrescribir variables ya definidas."""
    if not ruta.is_file():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"'))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cargar_env(Path(__file__).with_name(".env"))
    from consulta_np import create_app

    try:
        app = create_app()
    except ErrorConfiguracion as error:
        print(f"Configuracion invalida: {error}", file=sys.stderr)
        return 2
    from waitress import serve

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    timeout = int(os.environ.get("TIEMPO_MAXIMO_SEGUNDOS", "600")) + 60
    serve(app, host=host, port=port, threads=4, channel_timeout=timeout)
    return 0


if __name__ == "__main__":
    sys.exit(main())