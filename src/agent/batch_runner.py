"""Ejecutor por lotes del LegalAgent: lee preguntas, escribe submissions.jsonl y lo valida.

    python -m src.agent.batch_runner --entrada data/sample_50.jsonl --salida entregables/submissions.jsonl
    python -m src.agent.batch_runner --limite 3 --mock --salida test_submissions.jsonl
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from src.agent.agent import LegalAgent, consulta_de, get_real_retriever, mock_retriever

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = (Path("C:/Users/choco/Documents/COURSES/HackathonAI/schema/submission.schema.json"),
           ROOT.parent / "HackathonAI" / "schema" / "submission.schema.json",
           ROOT / "schema" / "submission.schema.json")
FORMATOS = ("multiple_choice", "semi_open", "open_ended")
_VACIO = {
    "multiple_choice": {"respuesta_correcta": None, "justificacion": "", "descarte_opciones": {}},
    "semi_open": {"respuesta": "", "palabras_clave": [], "referencia_legal": ""},
    "open_ended": {"marco_normativo": "", "analisis": "", "jurisprudencia": "", "conclusion": ""},
}


def _existe(ruta: Path) -> bool:
    try:  # una ruta inaccesible lanza OSError en Windows en vez de devolver False
        return ruta.is_file()
    except OSError:
        return False


def registro_abstencion(item: dict, formato: str | None = None) -> dict:
    """Registro válido según el esquema para un item que no se pudo procesar."""
    formato = formato if formato in FORMATOS else item.get("formato")
    if formato not in FORMATOS:
        formato = "multiple_choice" if isinstance(item.get("opciones"), dict) else "open_ended"
    return {"id": item.get("id"), "formato": formato, "abstencion": True, "pasajes_recuperados": [],
            **_VACIO[formato]}


def crear_agente(mock: bool) -> tuple[LegalAgent, str]:
    if not mock:
        try:
            hook = get_real_retriever()
            return LegalAgent(lambda s: hook(consulta_de({"pregunta": s.pregunta, "opciones": s.opciones}))), "real"
        except Exception as e:  # índices ausentes, dependencias RAG o modelos no disponibles
            print(f"Retriever real no disponible ({type(e).__name__}: {e}); se usa mock_retriever", flush=True)
    return LegalAgent(mock_retriever, forzar_mock_escritor=mock), "mock"


def ejecutar(entrada: Path, salida: Path, limite: int | None, mock: bool) -> int:
    items = [json.loads(ln) for ln in entrada.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if limite:
        items = items[:limite]
    agente, modo = crear_agente(mock)
    salida.parent.mkdir(parents=True, exist_ok=True)
    total, errores = len(items), 0
    print(f"== {total} preguntas, retriever {modo} -> {salida}", flush=True)
    with salida.open("w", encoding="utf-8") as f:
        for i, item in enumerate(items, 1):
            t0 = time.perf_counter()
            try:
                registro = LegalAgent.to_submission(agente.run(item))
            except Exception as e:  # el lote nunca se detiene
                errores += 1
                print(f"   ERROR en id={item.get('id')}: {type(e).__name__}: {e}", flush=True)
                registro = registro_abstencion(item)
            dt = time.perf_counter() - t0
            registro.setdefault("latencia_ms", round(dt * 1000))
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
            f.flush()
            print(f"[{i}/{total}] ID: {registro['id']} Formato: {registro['formato']} Tiempo: {dt:.2f}s"
                  f"{' (abstención)' if registro['abstencion'] else ''}", flush=True)
    print(f"== listo: {total - errores} ok, {errores} con error", flush=True)
    return validar(salida)


def validar(salida: Path) -> int:
    """Valida cada línea contra el esquema oficial. Devuelve el número de líneas inválidas."""
    ruta = next((s for s in SCHEMAS if _existe(s)), None)
    if ruta is None:
        print("== validación omitida: no se encontró submission.schema.json")
        return 0
    esquema = json.loads(ruta.read_text(encoding="utf-8"))
    try:
        import jsonschema
        validador = jsonschema.Draft202012Validator(esquema)
        fallos = lambda r: [e.message for e in validador.iter_errors(r)]  # noqa: E731
        motor = "jsonschema"
    except ImportError:
        obligatorios = esquema["required"]
        fallos = lambda r: [f"falta '{k}'" for k in obligatorios if k not in r]  # noqa: E731
        motor = "campos obligatorios (jsonschema no instalado)"
    malas = 0
    for n, linea in enumerate(salida.read_text(encoding="utf-8").splitlines(), 1):
        for msg in fallos(json.loads(linea)):
            malas += 1
            print(f"   línea {n}: {msg}")
    print(f"== validación [{motor}] con {ruta}: "
          f"{'todo conforme' if not malas else f'{malas} problemas'}")
    return malas


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entrada", type=Path, default=ROOT / "data" / "sample_50.jsonl")
    ap.add_argument("--salida", type=Path, default=ROOT / "entregables" / "submissions.jsonl")
    ap.add_argument("--limite", type=int, help="solo los primeros N casos")
    ap.add_argument("--mock", action="store_true", help="pasajes simulados, sin cargar índices")
    args = ap.parse_args()
    ejecutar(args.entrada, args.salida, args.limite, args.mock)


if __name__ == "__main__":
    main()
