"""Configuracion desde variables de entorno. Falla cerrado si falta algo obligatorio."""
from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from typing import Mapping

from .excel import LimitesEntrada
from .tdx import ConfigApi

LOGIN_URL_PREDETERMINADA = "https://auth.dicexapis.com/v1/login/access_token"
CONSULTA_URL_PREDETERMINADA = "https://tdx4.dicexapis.com/jit/numeros_parte/masivo"
OBLIGATORIAS = ("APP_SECRET_KEY", "TDX_USERNAME", "TDX_PASSWORD", "TDX_CLI_ID")
HOST_PREDETERMINADO = "127.0.0.1"
_VERDADEROS = {"1", "true", "yes", "si", "on"}
_FALSOS = {"0", "false", "no", "off"}


class ErrorConfiguracion(RuntimeError):
    pass


@dataclass(frozen=True)
class Configuracion:
    secret_key: str
    access_password: str
    requiere_login: bool
    host: str
    trust_proxy: bool
    cookie_secure: bool
    api: ConfigApi
    limites: LimitesEntrada
    max_upload_bytes: int
    max_consultas_simultaneas: int


def _entero(env: Mapping[str, str], nombre: str, defecto: int, minimo: int, maximo: int) -> int:
    crudo = env.get(nombre, "").strip()
    if not crudo:
        return defecto
    try:
        valor = int(crudo)
    except ValueError:
        raise ErrorConfiguracion(f"{nombre} debe ser un entero.") from None
    if not minimo <= valor <= maximo:
        raise ErrorConfiguracion(f"{nombre} debe estar entre {minimo} y {maximo}.")
    return valor


def _booleano(env: Mapping[str, str], nombre: str, defecto: bool) -> bool:
    crudo = env.get(nombre, "").strip().lower()
    if not crudo:
        return defecto
    if crudo in _VERDADEROS:
        return True
    if crudo in _FALSOS:
        return False
    raise ErrorConfiguracion(f"{nombre} debe ser true o false.")


def es_loopback(direccion: str | None) -> bool:
    """True solo para localhost o direcciones IP de loopback (127.0.0.0/8, ::1)."""
    if not direccion:
        return False
    direccion = direccion.strip().strip("[]")
    if direccion.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(direccion).is_loopback
    except ValueError:
        return False


def cargar_configuracion(env: Mapping[str, str] | None = None) -> Configuracion:
    env = os.environ if env is None else env
    requiere_login = _booleano(env, "APP_REQUIRE_LOGIN", True)
    host = env.get("HOST", "").strip() or HOST_PREDETERMINADO
    trust_proxy = _booleano(env, "APP_TRUST_PROXY", False)
    if trust_proxy and not es_loopback(host):
        raise ErrorConfiguracion(
            "APP_TRUST_PROXY=true solo se permite con HOST de loopback y un proxy local de confianza."
        )
    if not requiere_login and not es_loopback(host):
        raise ErrorConfiguracion(
            "APP_REQUIRE_LOGIN=false solo se permite con HOST de loopback (127.0.0.1, ::1 o localhost)."
        )
    obligatorias = OBLIGATORIAS + (("APP_ACCESS_PASSWORD",) if requiere_login else ())
    faltantes = [n for n in obligatorias if not env.get(n, "").strip()]
    if faltantes:
        raise ErrorConfiguracion("Faltan variables de entorno obligatorias: " + ", ".join(faltantes))
    secret_key = env["APP_SECRET_KEY"].strip()
    if len(secret_key) < 32:
        raise ErrorConfiguracion("APP_SECRET_KEY debe tener al menos 32 caracteres.")
    password = env["APP_ACCESS_PASSWORD"] if requiere_login else ""
    if requiere_login and len(password) < 12:
        raise ErrorConfiguracion("APP_ACCESS_PASSWORD debe tener al menos 12 caracteres.")
    login_url = env.get("TDX_LOGIN_URL", "").strip() or LOGIN_URL_PREDETERMINADA
    consulta_url = env.get("TDX_QUERY_URL", "").strip() or CONSULTA_URL_PREDETERMINADA
    for nombre, url in (("TDX_LOGIN_URL", login_url), ("TDX_QUERY_URL", consulta_url)):
        if not url.startswith("https://"):
            raise ErrorConfiguracion(f"{nombre} debe usar https://.")

    max_upload_mb = _entero(env, "MAX_UPLOAD_MB", 10, 1, 50)
    api = ConfigApi(
        login_url=login_url,
        consulta_url=consulta_url,
        usuario=env["TDX_USERNAME"].strip(),
        contrasena=env["TDX_PASSWORD"],
        cli_id=env["TDX_CLI_ID"].strip(),
        presupuesto_segundos=_entero(env, "TIEMPO_MAXIMO_SEGUNDOS", 600, 30, 3600),
    )
    return Configuracion(
        secret_key=secret_key,
        access_password=password,
        requiere_login=requiere_login,
        host=host,
        trust_proxy=trust_proxy,
        cookie_secure=env.get("APP_COOKIE_SECURE", "true").strip().lower() not in {"0", "false", "no"},
        api=api,
        limites=LimitesEntrada(max_filas_np=_entero(env, "MAX_FILAS_NP", 50_000, 1, 200_000)),
        max_upload_bytes=max_upload_mb * 1024 * 1024,
        max_consultas_simultaneas=_entero(env, "MAX_CONSULTAS_SIMULTANEAS", 2, 1, 10),
    )