"""Construccion del CSV de salida (mismo orden de columnas que el proceso original, sin UNSPSC)."""
from __future__ import annotations

import csv
import io
import re
from typing import Any

from .excel import texto

COLUMNAS_SALIDA = [
    "numeroParteEnviado", "encontrado", "numeroParte", "numeroParteInterno",
    "fraccion", "descripcionFactura", "descripcionPedimento", "pais",
    "unidadMedida", "marca", "modelo", "tipoMercancia", "sustentoNormativo",
    "igiTasa", "observaciones",
]
VALORES_ENCONTRADO = {"1", "true", "si", "s\u00ed"}
OBSERVACION_NO_ENCONTRADO = "La API no devolvio un registro para este numero."
PREFIJOS_FORMULA = ("=", "\x40", "\t", "\r")
APOSTROFO = "\x27"
_NUMERO_CON_SIGNO = re.compile(r"^[+-][0-9]+([.,][0-9]+)?$")


def construir_filas(numeros: list[str], respuestas: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int, int]:
    mapa: dict[str, dict[str, Any]] = {}
    for respuesta in respuestas:
        numero = texto(respuesta.get("numeroParteEnviado") or respuesta.get("numeroParte"))
        if numero:
            mapa[numero.casefold()] = respuesta

    filas: list[dict[str, Any]] = []
    encontrados = 0
    for numero in numeros:
        resultado = dict(mapa.get(numero.casefold(), {}))
        resultado.setdefault("numeroParteEnviado", numero)
        if texto(resultado.get("encontrado", 0)).casefold() in VALORES_ENCONTRADO:
            encontrados += 1
        else:
            resultado["encontrado"] = 0
            resultado.setdefault("observaciones", OBSERVACION_NO_ENCONTRADO)
        filas.append(resultado)
    return filas, encontrados, len(filas) - encontrados


def neutralizar_formula(valor: Any) -> str:
    """Evita que Excel interprete una celda como formula sin alterar valores normales."""
    if valor is None:
        return ""
    cadena = str(valor)
    if not cadena:
        return cadena
    if cadena.startswith(PREFIJOS_FORMULA) or (
        cadena[0] in "+-" and not _NUMERO_CON_SIGNO.match(cadena)
    ):
        return APOSTROFO + cadena
    return cadena


def generar_csv(filas: list[dict[str, Any]]) -> bytes:
    buffer = io.StringIO(newline="")
    escritor = csv.DictWriter(buffer, fieldnames=COLUMNAS_SALIDA, extrasaction="ignore")
    escritor.writeheader()
    for fila in filas:
        escritor.writerow({col: neutralizar_formula(fila.get(col)) for col in COLUMNAS_SALIDA})
    return buffer.getvalue().encode("utf-8-sig")