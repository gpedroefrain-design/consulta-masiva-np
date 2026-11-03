from __future__ import annotations

import io
import json
import re
from typing import Any

import pytest
import requests
from openpyxl import Workbook

from consulta_np.config import cargar_configuracion

PASSWORD = "clave-de-prueba-123"
ENV_FICTICIO = {
    "APP_SECRET_KEY": "x" * 40,
    "APP_ACCESS_PASSWORD": PASSWORD,
    "APP_COOKIE_SECURE": "false",
    "TDX_USERNAME": "usuario-ficticio",
    "TDX_PASSWORD": "contrasena-ficticia",
    "TDX_CLI_ID": "cliente-ficticio",
    "TDX_LOGIN_URL": "https://login.invalid/token",
    "TDX_QUERY_URL": "https://consulta.invalid/masivo",
}


def respuesta(status: int = 200, cuerpo: Any = None, texto: str | None = None) -> requests.Response:
    r = requests.Response()
    r.status_code = status
    r._content = (texto if texto is not None else json.dumps(cuerpo)).encode()
    r.headers["Content-Type"] = "application/json"
    r.url = "https://consulta.invalid/"
    return r


class SesionFalsa:
    """Sustituye requests.Session: nunca hace llamadas de red."""

    def __init__(self, login=None, consultas=None):
        self.login = list(login or [respuesta(200, {"data": {"access_token": "tok-1"}})])
        self.consultas = list(consultas or [])
        self.llamadas: list[dict[str, Any]] = []

    def post(self, url, **kwargs):
        self.llamadas.append({"url": url, **kwargs})
        cola = self.login if "login" in url else self.consultas
        item = cola.pop(0) if len(cola) > 1 else cola[0]
        if isinstance(item, Exception):
            raise item
        if callable(item):
            return item(kwargs)
        return item

    def de(self, tipo: str):
        return [c for c in self.llamadas if tipo in c["url"]]


def eco_encontrados(kwargs):
    """Simula la API: devuelve encontrado=1 para NP que empiezan con A, 0 para el resto."""
    numeros = kwargs["json"]["numeros"]
    return respuesta(200, {"data": [
        {"numeroParteEnviado": n, "encontrado": 1 if n.upper().startswith("A") else 0,
         "numeroParte": n, "fraccion": "12345678", "UNSPSC": "99999999", "extra": "x"}
        for n in numeros
    ]})


def xlsx(filas, hoja: str | None = None, extra_hoja: bool = False) -> bytes:
    libro = Workbook()
    ws = libro.active
    if extra_hoja:
        ws.title = "OTRA"
        ws.append(["NP"])
        ws.append(["NO-USAR"])
        ws = libro.create_sheet("CONSULTA")
    elif hoja:
        ws.title = hoja
    for fila in filas:
        ws.append(fila)
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def env():
    return dict(ENV_FICTICIO)


@pytest.fixture
def config(env):
    return cargar_configuracion(env)


def extraer_csrf(html: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)