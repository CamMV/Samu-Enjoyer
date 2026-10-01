"""Compara modelos en el papel de juez sobre los mismos borradores, para decidir cuál juzga mejor.

El agente (recuperación + escritor) corre una vez por pregunta y cada juez candidato revisa ese
mismo borrador. En las cerradas se conoce la letra correcta, así que se mide el acuerdo entre el
veredicto y el acierto real. La clave se usa SOLO aquí, para medir al juez; nunca entra en su prompt.

    python -m src.agent.judge_eval --juez gemma4:e4b@http://localhost:11434/v1 --juez Qwen/Qwen3-8B@http://localhost:8000/v1
    python -m src.agent.judge_eval --juez mock --mock --limite 5
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from src.agent.batch_runner import crear_agente
from src.agent.tools import judge_tool

ROOT = Path(__file__).resolve().parents[2]


def _juzgar(spec: str, state):
    """`spec` es MODELO[@BASE_URL]; `mock` usa el juez simulado."""
    if spec == "mock":
        return judge_tool.mock_evaluate_with_judge(state)
    modelo, _, url = spec.partition("@")
    judge_tool.JUDGE_MODEL = modelo
    if url:
        judge_tool.JUDGE_BASE_URL = url
    return judge_tool.evaluate_with_judge(state)


def _pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "0/0"


def evaluar(entrada: Path, jueces: list[str], limite: int | None, mock: bool, salida: Path | None) -> dict:
    items = [json.loads(ln) for ln in entrada.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if limite:
        items = items[:limite]
    agente, modo = crear_agente(mock)
    print(f"== {len(items)} preguntas, retriever {modo}, jueces: {', '.join(jueces)}", flush=True)
    filas = []
    for i, item in enumerate(items, 1):
        state = agente.run(item)
        acierto = None  # solo se conoce en las cerradas no abstenidas
        if state.formato == "multiple_choice" and not state.abstencion and item.get("respuesta_correcta"):
            acierto = (state.borrador_respuesta or {}).get("respuesta_correcta") == item["respuesta_correcta"]
        fila = {"id": state.id, "formato": state.formato, "abstencion": state.abstencion, "acierto": acierto,
                "veredictos": {}}
        for spec in jueces:
            t0 = time.perf_counter()
            v = _juzgar(spec, state)
            fila["veredictos"][spec] = {**v.model_dump(), "latencia_s": round(time.perf_counter() - t0, 2)}
        filas.append(fila)
        print(f"[{i}/{len(items)}] ID: {state.id} acierto={acierto} "
              + " ".join(f"{s}={fila['veredictos'][s]['aprobado']}" for s in jueces), flush=True)
    if salida:
        salida.parent.mkdir(parents=True, exist_ok=True)
        salida.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas), encoding="utf-8")

    resumen = {}
    for spec in jueces:
        vs = [(f, f["veredictos"][spec]) for f in filas if not f["abstencion"]]
        decididos = [(f, v) for f, v in vs if v["aprobado"] is not None]
        cerradas = [(f, v) for f, v in decididos if f["acierto"] is not None]
        erradas = [(f, v) for f, v in cerradas if not f["acierto"]]
        resumen[spec] = {
            "juzgadas": len(vs),
            "sin_veredicto": len(vs) - len(decididos),
            "aprobadas": sum(v["aprobado"] for _, v in decididos),
            "cerradas": len(cerradas),
            "acuerdo_cerradas": sum(v["aprobado"] == f["acierto"] for f, v in cerradas),
            "erradas": len(erradas),
            "erradas_rechazadas": sum(not v["aprobado"] for _, v in erradas),
            "latencia_media_s": round(sum(v["latencia_s"] for _, v in vs) / len(vs), 2) if vs else 0.0,
        }
        r = resumen[spec]
        print(f"\n== {spec}\n"
              f"   sin veredicto (servidor caído o JSON inválido): {_pct(r['sin_veredicto'], r['juzgadas'])}\n"
              f"   aprobadas: {_pct(r['aprobadas'], len(decididos))}\n"
              f"   acuerdo con el acierto real en cerradas: {_pct(r['acuerdo_cerradas'], r['cerradas'])}\n"
              f"   cerradas erradas que el juez rechazó: {_pct(r['erradas_rechazadas'], r['erradas'])}\n"
              f"   latencia media: {r['latencia_media_s']} s")
    return resumen


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entrada", type=Path, default=ROOT / "data" / "sample_50.jsonl")
    ap.add_argument("--juez", action="append", required=True, metavar="MODELO[@BASE_URL]",
                    help="juez candidato; repetir para comparar varios ('mock' = juez simulado)")
    ap.add_argument("--limite", type=int, help="solo los primeros N casos")
    ap.add_argument("--mock", action="store_true", help="pasajes y escritor simulados, sin cargar índices")
    ap.add_argument("--salida", type=Path, help="jsonl con el veredicto de cada juez por pregunta")
    args = ap.parse_args()
    evaluar(args.entrada, args.juez, args.limite, args.mock, args.salida)


if __name__ == "__main__":
    main()
