"""Aplicacion web para consulta masiva de numeros de parte (Excel -> XLSX)."""
from __future__ import annotations

import hmac
import logging
import secrets
import threading
import time
from datetime import datetime, timedelta
from typing import Callable
from urllib.parse import urlparse

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from .config import Configuracion, cargar_configuracion, es_loopback
from .excel import MIME_XLSX, NOMBRE_LAYOUT, ErrorEntrada, generar_layout, leer_numeros_excel
from .salida import PREFIJO_NOMBRE_RESULTADOS, construir_filas, generar_xlsx
from .tdx import ClienteTdx, ConfigApi, ErrorApi

LOGGER = logging.getLogger(__name__)
MAX_INTENTOS_LOGIN = 5
VENTANA_LOGIN_SEGUNDOS = 15 * 60


class _LimitadorLogin:
    def __init__(self) -> None:
        self._fallos: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def bloqueado(self, clave: str) -> bool:
        with self._lock:
            ahora = time.monotonic()
            recientes = [t for t in self._fallos.get(clave, []) if ahora - t < VENTANA_LOGIN_SEGUNDOS]
            self._fallos[clave] = recientes
            return len(recientes) >= MAX_INTENTOS_LOGIN

    def fallo(self, clave: str) -> None:
        with self._lock:
            self._fallos.setdefault(clave, []).append(time.monotonic())

    def limpiar(self, clave: str) -> None:
        with self._lock:
            self._fallos.pop(clave, None)


def create_app(
    config: Configuracion | None = None,
    cliente_factory: Callable[[ConfigApi], ClienteTdx] = ClienteTdx,
) -> Flask:
    config = config or cargar_configuracion()
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=config.secret_key,
        MAX_CONTENT_LENGTH=config.max_upload_bytes,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=config.cookie_secure,
        SESSION_COOKIE_NAME="consulta_np_sesion",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        PROPAGATE_EXCEPTIONS=False,
        CONSULTA_HOST=config.host,
    )
    if config.trust_proxy:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
    semaforo = threading.BoundedSemaphore(config.max_consultas_simultaneas)
    limitador = _LimitadorLogin()
    max_mb = config.max_upload_bytes // (1024 * 1024)

    def quiere_json() -> bool:
        return request.headers.get("X-Requested-With") == "fetch"

    def token_csrf() -> str:
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        return session["csrf"]

    def csrf_valido() -> bool:
        origen = request.headers.get("Origin")
        if origen and urlparse(origen).netloc != request.host:
            return False
        enviado = request.form.get("csrf_token", "") or request.headers.get("X-CSRF-Token", "")
        esperado = session.get("csrf", "")
        return bool(esperado) and hmac.compare_digest(enviado.encode(), esperado.encode())

    def autenticado() -> bool:
        if not config.requiere_login:
            return True
        return session.get("autenticado") is True

    def pagina(error: str | None = None, estado: int = 200, aviso: str | None = None) -> Response:
        html = render_template(
            "index.html",
            autenticado=autenticado(),
            requiere_login=config.requiere_login,
            csrf_token=token_csrf(),
            error=error,
            aviso=aviso,
            max_mb=max_mb,
            max_filas=config.limites.max_filas_np,
            max_segundos=int(config.api.presupuesto_segundos),
        )
        return Response(html, status=estado, mimetype="text/html")

    def fallo(mensaje: str, estado: int) -> Response:
        if quiere_json():
            respuesta = jsonify(error=mensaje)
            respuesta.status_code = estado
            return respuesta
        return pagina(error=mensaje, estado=estado)

    if not config.requiere_login:
        LOGGER.warning("APP_REQUIRE_LOGIN=false: acceso sin contrasena, solo desde loopback (%s).", config.host)

        @app.before_request
        def solo_loopback():
            # remote_addr es el par TCP real (no se confia en X-Forwarded-For).
            if not es_loopback(request.remote_addr):
                return fallo("Acceso permitido solo desde este equipo.", 403)
            return None

    @app.after_request
    def cabeceras(respuesta: Response) -> Response:
        respuesta.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        respuesta.headers["X-Content-Type-Options"] = "nosniff"
        respuesta.headers["X-Frame-Options"] = "DENY"
        respuesta.headers["Referrer-Policy"] = "no-referrer"
        respuesta.headers["Cache-Control"] = "no-store"
        return respuesta

    @app.get("/")
    def inicio() -> Response:
        return pagina()

    @app.get("/salud")
    def salud() -> Response:
        return Response("ok", mimetype="text/plain")

    @app.get("/layout")
    def descargar_layout():
        if not autenticado():
            return fallo("Debe iniciar sesion.", 401)
        respuesta = Response(generar_layout(), mimetype=MIME_XLSX)
        respuesta.headers["Content-Disposition"] = f'attachment; filename="{NOMBRE_LAYOUT}"'
        return respuesta

    @app.post("/login")
    def login():
        if not config.requiere_login:
            abort(404)
        if not csrf_valido():
            return fallo("La sesion del formulario expiro. Recargue la pagina e intente de nuevo.", 400)
        clave = request.remote_addr or "desconocido"
        if limitador.bloqueado(clave):
            return fallo("Demasiados intentos fallidos. Espere unos minutos.", 429)
        enviada = request.form.get("password", "")
        if not hmac.compare_digest(enviada.encode(), config.access_password.encode()):
            limitador.fallo(clave)
            LOGGER.warning("Intento de acceso fallido.")
            return fallo("Contrasena incorrecta.", 401)
        limitador.limpiar(clave)
        session.clear()
        session.permanent = True
        session["autenticado"] = True
        session["csrf"] = secrets.token_urlsafe(32)
        return redirect(url_for("inicio"), code=303)

    @app.post("/logout")
    def logout():
        if not config.requiere_login:
            abort(404)
        if csrf_valido():
            session.clear()
        return redirect(url_for("inicio"), code=303)

    @app.post("/consultar")
    def consultar():
        if not autenticado():
            return fallo("Debe iniciar sesion.", 401)
        if not csrf_valido():
            return fallo("La sesion del formulario expiro. Recargue la pagina e intente de nuevo.", 400)
        archivo = request.files.get("archivo")
        if archivo is None or not archivo.filename:
            return fallo("Seleccione un archivo .xlsx.", 400)
        if not archivo.filename.lower().endswith(".xlsx"):
            return fallo("Solo se aceptan archivos .xlsx.", 400)
        contenido = archivo.read(config.max_upload_bytes + 1)
        if len(contenido) > config.max_upload_bytes:
            return fallo(f"El archivo excede el limite de {max_mb} MB.", 413)

        if not semaforo.acquire(blocking=False):
            return fallo("Hay demasiadas consultas en curso. Intente de nuevo en unos minutos.", 503)
        try:
            lectura = leer_numeros_excel(contenido, config.limites)
            del contenido
            cliente = cliente_factory(config.api)
            respuestas = cliente.consultar(lectura.numeros)
            filas, encontrados, no_encontrados = construir_filas(lectura.numeros, respuestas)
            datos = generar_xlsx(filas)
        except ErrorEntrada as error:
            return fallo(str(error), 400)
        except ErrorApi as error:
            LOGGER.warning("Fallo de API: %s", error)
            return fallo(f"No se pudo completar la consulta: {error}", 502)
        finally:
            semaforo.release()

        LOGGER.info(
            "Consulta completada: %s NP unicos, %s encontrados, %s no encontrados.",
            len(filas), encontrados, no_encontrados,
        )
        nombre = PREFIJO_NOMBRE_RESULTADOS + datetime.now().strftime("%Y%m%d_%H%M%S") + ".xlsx"
        respuesta = Response(datos, mimetype=MIME_XLSX)
        respuesta.headers["Content-Disposition"] = f'attachment; filename="{nombre}"'
        respuesta.headers["X-Total-NP"] = str(len(filas))
        respuesta.headers["X-Encontrados"] = str(encontrados)
        respuesta.headers["X-No-Encontrados"] = str(no_encontrados)
        return respuesta

    @app.errorhandler(RequestEntityTooLarge)
    def demasiado_grande(_error):
        return fallo(f"El archivo excede el limite de {max_mb} MB.", 413)

    @app.errorhandler(HTTPException)
    def error_http(error: HTTPException):
        return fallo(error.description or "Solicitud no valida.", error.code or 400)

    @app.errorhandler(Exception)
    def error_interno(error: Exception):
        LOGGER.error("Error interno no controlado: %s", type(error).__name__)
        return fallo("Ocurrio un error interno. Intente de nuevo o contacte al administrador.", 500)

    return app