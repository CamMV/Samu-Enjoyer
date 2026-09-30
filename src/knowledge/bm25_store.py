"""Índice BM25 (bm25s) sobre corpus/chunks.

  python -m src.knowledge.bm25_store                                 # todo el corpus -> corpus/indices/bm25_todo
  python -m src.knowledge.bm25_store --seleccion normas_fichas       # subcorpus del banco de pruebas

Requiere RAM proporcional al corpus (~1,5 M chunks: ~30-40 GB al construir). Se carga
con mmap, así que en el portátil consultar no exige tenerlo entero en memoria.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import bm25s
import numpy as np
from bm25s.tokenization import Tokenized

from .chunk_store import INDICES, leer_chunks
from .tokenization import tokens


def construir(seleccion: str, salida: Path, limite: int | None = None, raices: bool = True):
    salida.mkdir(parents=True, exist_ok=True)
    vocab: dict[str, int] = {}
    ids, docs = [], []
    t0 = time.time()
    for i, c in enumerate(leer_chunks(seleccion, limite), 1):
        ids.append(c["chunk_id"])
        docs.append([vocab.setdefault(t, len(vocab)) for t in tokens(c["texto"], raices)])
        if i % 200_000 == 0:
            print(f"   {i} chunks tokenizados, vocabulario {len(vocab)}, {time.time() - t0:.0f} s", flush=True)
    print(f"== {len(ids)} chunks, vocabulario {len(vocab)}; indexando", flush=True)
    bm = bm25s.BM25(k1=1.2, b=0.75)
    bm.index(Tokenized(ids=docs, vocab=vocab), show_progress=True)
    bm.save(str(salida))
    (salida / "ids.json").write_text(json.dumps(ids), encoding="utf-8")
    (salida / "info.json").write_text(json.dumps({"seleccion": seleccion, "n": len(ids), "vocab": len(vocab),
                                                  "raices": raices, "segundos": round(time.time() - t0)}),
                                      encoding="utf-8")
    print(f"== listo en {time.time() - t0:.0f} s -> {salida}")


class IndiceBM25:
    def __init__(self, ruta: Path):
        self.bm = bm25s.BM25.load(str(ruta), mmap=True, load_vocab=True, show_progress=False)
        self.ids = json.loads((ruta / "ids.json").read_text(encoding="utf-8"))
        self.vocab = self.bm.vocab_dict
        # La consulta se tokeniza igual que se construyó el índice.
        self.raices = json.loads((ruta / "info.json").read_text(encoding="utf-8")).get("raices", True)

    def buscar(self, consulta: str, k: int = 100) -> list[tuple[str, float]]:
        q = [self.vocab[t] for t in tokens(consulta, self.raices) if t in self.vocab]
        if not q:
            return []
        docs, scores = self.bm.retrieve(Tokenized(ids=[q], vocab=self.vocab), k=min(k, len(self.ids)),
                                        show_progress=False, n_threads=1)
        pares = [(self.ids[int(d)], float(s)) for d, s in zip(docs[0], scores[0]) if s > 0]
        # Orden estable: puntaje redondeado y chunk_id (igual en cualquier máquina).
        return sorted(pares, key=lambda p: (-round(p[1], 5), p[0]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seleccion", default="todo", choices=["todo", "normas_fichas"])
    ap.add_argument("--limite", type=int, help="solo los primeros N chunks (prueba)")
    ap.add_argument("--sin-raices", action="store_true", help="sin stemming (para comparar en el banco de pruebas)")
    ap.add_argument("--salida", type=Path)
    args = ap.parse_args()
    nombre = f"bm25_{args.seleccion}" + ("_sin_raices" if args.sin_raices else "")
    construir(args.seleccion, args.salida or INDICES / nombre, args.limite, raices=not args.sin_raices)


if __name__ == "__main__":
    np.random.seed(0)
    main()
