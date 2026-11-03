"""Lectura y validacion del Excel de entrada (en memoria, sin archivos temporales)."""
from __future__ import annotations

import io
import unicodedata
import zipfile
from dataclasses import dataclass
from typing import Any

from openpyxl import load_workbook

COLUMNAS_ACEPTADAS = ("numero_parte", "numeroparte", "np")
HOJA_PREFERIDA = "CONSULTA"
LONGITUD_MAXIMA_NP = 100


class ErrorEntrada(ValueError):
    """Error del archivo de entrada; el mensaje es seguro para mostrarse al usuario."""


@dataclass(frozen=True)
class LimitesEntrada:
    max_filas_np: int = 50_000
    max_descomprimido_bytes: int = 200 * 1024 * 1024
    max_entradas_zip: int = 2_000
    max_ratio_compresion: int = 200


@dataclass
class ResultadoLectura:
    numeros: list[str]
    filas_con_np: int
    duplicados: int


def texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()


def validar_zip_xlsx(contenido: bytes, limites: LimitesEntrada) -> None:
    if contenido[:2] != b"PK":
        raise ErrorEntrada("El archivo no es un XLSX valido (firma ZIP ausente).")
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as archivo_zip:
            entradas = archivo_zip.infolist()
            if len(entradas) > limites.max_entradas_zip:
                raise ErrorEntrada("El XLSX contiene demasiadas entradas internas.")
            nombres = {entrada.filename for entrada in entradas}
            if "xl/workbook.xml" not in nombres:
                raise ErrorEntrada("El archivo no es un libro XLSX (falta xl/workbook.xml).")
            total = 0
            for entrada in entradas:
                total += entrada.file_size
                if total > limites.max_descomprimido_bytes:
                    raise ErrorEntrada("El contenido descomprimido del XLSX excede el limite permitido.")
                if entrada.compress_size and entrada.file_size / entrada.compress_size > limites.max_ratio_compresion:
                    raise ErrorEntrada("El XLSX tiene una compresion anormal y fue rechazado.")
            if archivo_zip.testzip() is not None:
                raise ErrorEntrada("El XLSX esta danado.")
    except zipfile.BadZipFile as error:
        raise ErrorEntrada("El archivo no es un XLSX valido o esta danado.") from error


def encontrar_columna(encabezado: tuple[Any, ...]) -> int:
    mapa: dict[str, int] = {}
    for posicion, valor in enumerate(encabezado):
        mapa.setdefault(texto(valor).casefold(), posicion)
    for nombre in COLUMNAS_ACEPTADAS:
        if nombre in mapa:
            return mapa[nombre]
    raise ErrorEntrada(
        "No existe la columna NUMERO_PARTE, NUMEROPARTE o NP en la primera fila."
    )


def _np_invalido(numero: str) -> str | None:
    if len(numero) > LONGITUD_MAXIMA_NP:
        return f"excede {LONGITUD_MAXIMA_NP} caracteres"
    if any(unicodedata.category(c).startswith("C") for c in numero):
        return "contiene caracteres de control"
    return None


def leer_numeros_excel(contenido: bytes, limites: LimitesEntrada | None = None) -> ResultadoLectura:
    limites = limites or LimitesEntrada()
    validar_zip_xlsx(contenido, limites)
    try:
        libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    except Exception as error:  # openpyxl lanza tipos variados ante XLSX corruptos
        raise ErrorEntrada("No se pudo abrir el archivo como XLSX.") from error

    try:
        hoja = libro[HOJA_PREFERIDA] if HOJA_PREFERIDA in libro.sheetnames else libro.active
        if hoja is None:
            raise ErrorEntrada("El libro no tiene hojas legibles.")
        filas = hoja.iter_rows(values_only=True)
        try:
            encabezado = next(filas)
        except StopIteration:
            raise ErrorEntrada("El archivo Excel esta vacio.") from None
        if encabezado is None:
            raise ErrorEntrada("El archivo Excel esta vacio.")
        columna = encontrar_columna(tuple(encabezado))

        numeros: list[str] = []
        vistos: set[str] = set()
        filas_con_np = 0
        errores: list[str] = []
        for numero_fila, fila in enumerate(filas, start=2):
            if not fila or columna >= len(fila):
                continue
            numero = texto(fila[columna])
            if not numero:
                continue
            filas_con_np += 1
            if filas_con_np > limites.max_filas_np:
                raise ErrorEntrada(
                    f"El archivo excede el limite de {limites.max_filas_np:,} filas con NP."
                )
            motivo = _np_invalido(numero)
            if motivo:
                if len(errores) < 5:
                    errores.append(f"fila {numero_fila}: {motivo}")
                continue
            clave = numero.casefold()
            if clave not in vistos:
                vistos.add(clave)
                numeros.append(numero)
        if errores:
            raise ErrorEntrada("Numeros de parte invalidos: " + "; ".join(errores) + ".")
    except ErrorEntrada:
        raise
    except Exception as error:
        raise ErrorEntrada("No se pudo leer el contenido del XLSX.") from error
    finally:
        libro.close()

    if not numeros:
        raise ErrorEntrada("El archivo no contiene numeros de parte para consultar.")
    return ResultadoLectura(numeros, filas_con_np, filas_con_np - len(numeros))