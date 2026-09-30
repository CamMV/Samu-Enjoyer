"""Tokenización para BM25, idéntica al indexar y al consultar.

- minúsculas y sin tildes (los PDF de la Corte vienen sin ellas; las preguntas, con);
- identificadores jurídicos en un solo token: "C-355" -> "c_355", "240-1" -> "240_1",
  "1.2.1.2.1" -> "1_2_1_2_1" (BM25 sirve justamente para acertar números exactos);
- números sueltos se conservan ("artículo 5" no pierde el 5);
- raíces en español (Snowball);
- las palabras vacías ("de", "no", "sin"…) se conservan: en derecho a veces cambian el
  sentido ("sin perjuicio de", "no podrá"). QUITAR_VACIAS las quita, para comparar.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

import Stemmer

# Sentencias: "C-748 de 2011", "C-748-11", "C-355/06", "T-025 de 2004" -> "c_748 2011", "t_25 2004".
# Número sin ceros a la izquierda y año en 4 cifras, como las normaliza el evaluador oficial.
_SENTENCIA = re.compile(r"\b(su|sc|sl|sp|stc|stl|stp|ac|al|ap|c|t)\s*-\s*0*(\d{1,5})([a-z]?)"
                        r"(?:\s*(?:/|-|\bde\b|\bdel\b)\s*(\d{4}|\d{2})\b)?")
_ID = re.compile(r"(?<=\w)[-.](?=\d)")          # 240-1, 1.2.1.2.1
_TOKEN = re.compile(r"\w+")
_MILES = re.compile(r"(?<=\d)\.(?=\d{3}\b)")      # 1.564 -> 1564 (números con punto de miles)

QUITAR_VACIAS = False  # si cambia, hay que reconstruir el índice BM25
VACIAS = set("""
a al algo algunas algunos ante antes como con contra cual cuales cuando de del desde donde durante
e el ella ellas ellos en entre era es esa esas ese eso esos esta estas este esto estos fue fueron ha
han hasta la las le les lo los mas me mi mientras muy nada ni no nos o otra otras otro otros para pero
poco por porque que quien quienes se sea segun ser si sin sino sobre su sus tambien tanto te tiene
tienen todo todos tu un una uno unos y ya
""".split())


@lru_cache(maxsize=1)
def _stemmer():
    return Stemmer.Stemmer("spanish")


def sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _sentencia(m: re.Match) -> str:
    anio = m[4] or ""
    if len(anio) == 2:
        anio = ("20" if int(anio) < 50 else "19") + anio
    return f" {m[1]}_{m[2]}{m[3]} {anio} "


def tokens(texto: str, raices: bool = True) -> list[str]:
    s = sin_tildes(texto.lower())
    s = _MILES.sub("", s)
    s = _SENTENCIA.sub(_sentencia, s)
    s = _ID.sub("_", s)
    toks = _TOKEN.findall(s)
    if QUITAR_VACIAS:
        toks = [t for t in toks if t not in VACIAS]
    if not raices:
        return toks
    # Los identificadores (con dígitos) no se pasan por el stemmer.
    palabras = [t for t in toks if not any(ch.isdigit() for ch in t)]
    raices = dict(zip(palabras, _stemmer().stemWords(palabras)))
    return [raices.get(t, t) for t in toks]
