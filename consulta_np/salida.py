"""Construccion del XLSX de salida (mismo orden de columnas que el proceso original, sin UNSPSC)."""
from __future__ import annotations

import io
import re
from typing import Any

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from .excel import texto

COLUMNAS_SALIDA = [
    "numeroParteEnviado", "encontrado", "numeroParte", "numeroParteInterno",
    "fraccion", "descripcionFactura", "descripcionPedimento", "pais",
    "unidadMedida", "marca", "modelo", "tipoMercancia", "sustentoNormativo",
    "igiTasa", "observaciones",
]
VALORES_ENCONTRADO = {"1", "true", "si", "s\u00ed"}
OBSERVACION_NO_ENCONTRADO = "La API no devolvio un registro para este numero."
HOJA_RESULTADOS = "RESULTADOS"
PREFIJO_NOMBRE_RESULTADOS = "consulta_np_"
MAX_CARACTERES_CELDA = 32_767
MARCA_TRUNCADO = "...[truncado]"
CARACTER_REEMPLAZO = "\ufffd"
PREFIJOS_FORMULA = ("=", "\x40", "\t", "\r")
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


def parece_formula(cadena: str) -> bool:
    """True si Excel podria interpretar el texto como formula al editar la celda."""
    if not cadena:
        return False
    return cadena.startswith(PREFIJOS_FORMULA) or (
        cadena[0] in "+-" and not _NUMERO_CON_SIGNO.match(cadena)
    )


def valor_celda(valor: Any) -> str:
    """Texto de la celda con la misma serializacion que el CSV anterior (str), apto para XLSX."""
    if valor is None:
        return ""
    cadena = ILLEGAL_CHARACTERS_RE.sub(CARACTER_REEMPLAZO, str(valor))
    if len(cadena) > MAX_CARACTERES_CELDA:
        cadena = cadena[: MAX_CARACTERES_CELDA - len(MARCA_TRUNCADO)] + MARCA_TRUNCADO
    return cadena


def _celda_texto(hoja, valor: Any) -> WriteOnlyCell | None:
    cadena = valor_celda(valor)
    if not cadena:
        return None
    celda = WriteOnlyCell(hoja, value=cadena)
    # Tipo string explicito: openpyxl no lo guarda como formula aunque empiece con "=".
    celda.data_type = "s"
    if parece_formula(cadena):
        celda.quotePrefix = True
    return celda


def generar_xlsx(filas: list[dict[str, Any]]) -> bytes:
    libro = Workbook(write_only=True)
    hoja = libro.create_sheet(HOJA_RESULTADOS)
    for posicion in range(1, len(COLUMNAS_SALIDA) + 1):
        columna = hoja.column_dimensions[get_column_letter(posicion)]
        columna.width = 22
        columna.number_format = "@"
    hoja.freeze_panes = "A2"
    negrita = Font(bold=True)
    encabezado = []
    for nombre in COLUMNAS_SALIDA:
        celda = WriteOnlyCell(hoja, value=nombre)
        celda.font = negrita
        encabezado.append(celda)
    hoja.append(encabezado)
    for fila in filas:
        hoja.append([_celda_texto(hoja, fila.get(col)) for col in COLUMNAS_SALIDA])
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()
