"""Plantilla del Senado (también Colpensiones, DIAN y Cancillería).

Cada página trae el texto entre <!--Inicio documento--> y <!--Fin documento-->:
- artículos:  <p><a class="bookmarkaj" name="42">ARTICULO 42. EPÍGRAFE</a> texto…</p>
              (a veces el ancla no trae clase: <A name="TRANSITORIO 1">)
- niveles:    <p class="centrado"><a class="bookmarkaj" name="Nivel001">TITULO I. </a></p>
              <p class="centrado"><span class="b_aj">DE LOS PRINCIPIOS …</span></p>
              o el ancla vacía en su propio párrafo antes del encabezado (Código Sustantivo).
- cajas:      <div><a class="caja_vja_encabezado…">Concordancias</a></div><table id="TableN">…
- tachado:    <S>…</S> (texto inexequible o derogado)

Las leyes estatutarias traen al final la sentencia de revisión, con el texto del
proyecto (sus "TÍTULO I", "ARTÍCULO 1o." sin anclas). Esos encabezados no son
parte de la jerarquía de la ley y se dejan como párrafos.
"""
from __future__ import annotations

import re
from pathlib import Path

from bs4 import Tag

from .. import jerarquia as jq
from ._html import leer, limpio, sopa, tabla_a_lineas
from .base import CAJA, PARRAFO, Bloque, Resultado

INICIO, FIN = "<!--Inicio documento-->", "<!--Fin documento-->"
# Si una página no trae las marcas, se quitan estos contenedores del <body>.
RELLENO = ("selector_aj", "update_date", "logo_aj", "imprimir")
CAJA_RE = re.compile(r"caja_vja_encabezado")
TABLA_CAJA = re.compile(r"Table\d+$")


def es_plantilla(html: str) -> bool:
    return INICIO in html or 'class="bookmarkaj"' in html


def _contenido(html: str) -> Tag:
    if INICIO in html:
        ini = html.index(INICIO) + len(INICIO)
        fin = html.find(FIN, ini)
        return sopa(html[ini: fin if fin > 0 else None]).body or sopa("<body></body>").body
    s = sopa(html)
    for id_ in RELLENO:
        for el in s.find_all(id=id_):
            el.decompose()
    return s.body or s


def _elementos(el: Tag):
    """Párrafos, tablas y rótulos de caja en orden de documento, sin entrar en ellos."""
    for c in el.children:
        if not isinstance(c, Tag) or c.name in ("script", "style", "select", "form"):
            continue
        if c.name in ("p", "table", "h1", "h2", "h3", "h4", "h5", "h6"):
            yield c
        elif c.name == "div" and c.find("a", class_=CAJA_RE):
            yield c
        else:
            yield from _elementos(c)


class HtmlPlantilla:
    nombre = "html_plantilla"

    def convertir(self, archivos: list[Path], sentencia: bool) -> Resultado:
        res = Resultado()
        b = res.bloques
        rotulo = ""                 # rótulo de la próxima caja
        nombre_pendiente = False    # "TITULO I." espera su nombre en el siguiente <p class="centrado">
        ancla_suelta = False        # <p><A name="Nivel001"></A></p>: el encabezado siguiente está anclado
        sin_ancla: list[int] = []   # índices de encabezados estructurales sin ancla
        ultimo_articulo = -1        # índice del último artículo anclado
        anclas_articulo = set()
        for archivo in archivos:
            for el in _elementos(_contenido(leer(archivo))):
                if el.name == "div":
                    rotulo = limpio(el.find("a", class_=CAJA_RE))
                    continue
                if el.name == "table":
                    if TABLA_CAJA.match(el.get("id", "")):
                        lineas = [limpio(p) for p in el.find_all("p")] or [limpio(el)]
                        lineas = [ln for ln in lineas if ln]
                        if lineas:
                            b.append(Bloque(CAJA, "\n".join(lineas), rotulo))
                    else:
                        b.extend(Bloque(PARRAFO, f) for f in tabla_a_lineas(el))
                    rotulo = ""
                    continue
                if el.find("a", class_="antsig"):  # Anterior | Siguiente
                    continue

                if sentencia:
                    t = limpio(el)
                    if t:
                        sec = jq.seccion_sentencia(t) if len(t) <= 150 else None
                        b.append(Bloque(jq.SECCION_SENTENCIA if sec else PARRAFO, t))
                    continue

                centrado = "centrado" in (el.get("class") or [])
                ancla = next((a for a in el.find_all("a", attrs={"name": True}) if limpio(a)), None)
                if ancla is None and el.find("a", attrs={"name": True}) and not limpio(el):
                    ancla_suelta = True
                    continue
                t_ancla = limpio(ancla) if ancla is not None else ""
                anclado, ancla_suelta = ancla is not None or ancla_suelta, False

                if ancla is not None:
                    ancla.extract()
                    cuerpo = limpio(el)
                    if art := jq.articulo(t_ancla):
                        num, epigrafe = art
                        anclas_articulo.add((archivo.name, ancla.get("name", num)))
                        b.append(Bloque(jq.ARTICULO, jq.titulo_articulo(num, epigrafe), num))
                        ultimo_articulo = len(b) - 1
                        if cuerpo:
                            b.append(Bloque(PARRAFO, cuerpo))
                        nombre_pendiente = False
                        continue
                    if est := jq.estructura(t_ancla):
                        b.append(Bloque(est[0], f"{t_ancla} {cuerpo}".strip()))
                        nombre_pendiente = not est[1] and not cuerpo
                        continue
                    if centrado:
                        b.append(Bloque("subtitulo", f"{t_ancla} {cuerpo}".strip()))
                        nombre_pendiente = False
                        continue
                    t = f"{t_ancla} {cuerpo}".strip()
                else:
                    t = limpio(el)
                if not t:
                    continue

                if centrado and nombre_pendiente:
                    b[-1].texto = f"{b[-1].texto} {t}"
                    nombre_pendiente = False
                elif centrado and (est := jq.estructura(t)):
                    b.append(Bloque(est[0], t))
                    if not anclado:
                        sin_ancla.append(len(b) - 1)
                    nombre_pendiente = not est[1]
                else:
                    b.append(Bloque(PARRAFO, t))
                    nombre_pendiente = False

        # Encabezados sin ancla después del último artículo: texto anexo (sentencia de revisión).
        anexos = [i for i in sin_ancla if i > ultimo_articulo >= 0]
        for i in anexos:
            b[i].tipo = PARRAFO
        res.stats = {"paginas": len(archivos), "articulos_fuente": len(anclas_articulo)}
        if anexos:
            res.stats["encabezados_anexos_como_parrafo"] = len(anexos)
        if not anclas_articulo:
            res.advertencias.append("sin anclas de artículo en la fuente")
        return res
