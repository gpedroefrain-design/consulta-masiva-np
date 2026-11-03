"""Cliente servidor-a-servidor para la API de consulta masiva de numeros de parte."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

import requests

from .excel import texto

LOGGER = logging.getLogger(__name__)

CLAVES_RESULTADOS = ("data", "results", "resultados", "resultado", "items", "numeros", "response")
STATUS_REINTENTABLES = {429, 500, 502, 503, 504}


class ErrorApi(RuntimeError):
    """Fallo de la API; el mensaje es seguro para el usuario (sin tokens ni credenciales)."""


class RespuestaInesperada(ErrorApi):
    pass


@dataclass(frozen=True)
class ConfigApi:
    login_url: str
    consulta_url: str
    usuario: str
    contrasena: str
    cli_id: str
    tamano_lote: int = 5000
    timeout_segundos: float = 180
    reintentos: int = 3
    pausa_base_reintento: float = 5
    presupuesto_segundos: float = 600


def _mensaje_error(contenido: dict[str, Any]) -> str:
    return texto(contenido.get("message") or contenido.get("mensaje") or contenido.get("error"))


def extraer_resultados(contenido: Any) -> list[dict[str, Any]] | None:
    """Devuelve la lista de resultados o None si la forma no es reconocible."""
    if isinstance(contenido, list):
        if all(isinstance(x, dict) for x in contenido):
            return list(contenido)
        return None
    if isinstance(contenido, dict):
        hubo_vacio = False
        for clave in CLAVES_RESULTADOS:
            if clave in contenido:
                filas = extraer_resultados(contenido[clave])
                if filas:
                    return filas
                if filas == []:
                    hubo_vacio = True
        return [] if hubo_vacio else None
    return None


def _a_mostrar(error: Exception) -> str:
    if isinstance(error, ErrorApi):
        return str(error)
    if isinstance(error, requests.Timeout):
        return "tiempo de espera agotado"
    if isinstance(error, requests.ConnectionError):
        return "no fue posible conectar con la API"
    if isinstance(error, requests.HTTPError) and error.response is not None:
        return f"HTTP {error.response.status_code}"
    return type(error).__name__


class ClienteTdx:
    def __init__(
        self,
        config: ConfigApi,
        sesion: requests.Session | None = None,
        reloj: Callable[[], float] = time.monotonic,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.sesion = sesion or requests.Session()
        self._reloj = reloj
        self._dormir = dormir
        self._token: str | None = None
        self._limite = reloj() + config.presupuesto_segundos

    def _timeout(self) -> float:
        restante = self._limite - self._reloj()
        if restante <= 1:
            raise ErrorApi("Se agoto el tiempo maximo de la consulta. Divida el archivo en partes mas pequenas.")
        return min(self.config.timeout_segundos, restante)

    def obtener_token(self) -> str:
        try:
            respuesta = self.sesion.post(
                self.config.login_url,
                data={"username": self.config.usuario, "password": self.config.contrasena},
                timeout=self._timeout(),
            )
        except requests.RequestException as error:
            raise ErrorApi(f"Fallo el inicio de sesion en la API: {_a_mostrar(error)}.") from None
        if respuesta.status_code in (401, 403):
            raise ErrorApi("La API rechazo las credenciales configuradas en el servidor.")
        if respuesta.status_code >= 400:
            raise ErrorApi(f"Fallo el inicio de sesion en la API (HTTP {respuesta.status_code}).")
        try:
            token = respuesta.json()["data"]["access_token"]
        except (ValueError, KeyError, TypeError):
            raise ErrorApi("El inicio de sesion no devolvio data.access_token.") from None
        if not token:
            raise ErrorApi("La API devolvio un token vacio.")
        self._token = str(token)
        return self._token

    def consultar_lote(self, numeros: list[str]) -> list[dict[str, Any]]:
        ultimo_error: Exception | None = None
        for intento in range(1, self.config.reintentos + 1):
            if self._token is None:
                self.obtener_token()
            try:
                respuesta = self.sesion.post(
                    self.config.consulta_url,
                    headers={
                        "Authorization": "Bearer " + str(self._token),
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    json={"cli_id": self.config.cli_id, "numeros": numeros},
                    timeout=self._timeout(),
                )
                if respuesta.status_code == 401:
                    LOGGER.info("Token rechazado (401); se renovara.")
                    self._token = None
                    ultimo_error = ErrorApi("la API rechazo el token (401)")
                    continue
                if respuesta.status_code >= 400:
                    if respuesta.status_code not in STATUS_REINTENTABLES:
                        raise ErrorApi(f"La API respondio HTTP {respuesta.status_code}.")
                    respuesta.raise_for_status()
                try:
                    contenido = respuesta.json()
                except ValueError:
                    raise RespuestaInesperada("La API devolvio una respuesta que no es JSON.") from None
                resultados = extraer_resultados(contenido)
                if isinstance(contenido, dict) and not resultados:
                    mensaje = _mensaje_error(contenido)
                    if mensaje:
                        raise ErrorApi(f"La API devolvio un error: {mensaje[:300]}")
                if resultados is None:
                    raise RespuestaInesperada("La API devolvio una respuesta con forma inesperada.")
                return resultados
            except ErrorApi:
                raise
            except requests.RequestException as error:
                ultimo_error = error
                LOGGER.warning("Intento %s/%s fallo: %s", intento, self.config.reintentos, _a_mostrar(error))
            if intento < self.config.reintentos:
                espera = self.config.pausa_base_reintento * intento
                if self._reloj() + espera >= self._limite:
                    break
                self._dormir(espera)
        detalle = _a_mostrar(ultimo_error) if ultimo_error else "sin detalle"
        raise ErrorApi(f"El lote fallo despues de {self.config.reintentos} intentos: {detalle}.")

    def consultar(self, numeros: list[str]) -> list[dict[str, Any]]:
        respuestas: list[dict[str, Any]] = []
        tamano = self.config.tamano_lote
        for inicio in range(0, len(numeros), tamano):
            respuestas.extend(self.consultar_lote(numeros[inicio:inicio + tamano]))
        return respuestas