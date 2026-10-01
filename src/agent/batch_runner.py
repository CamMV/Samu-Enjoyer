"""Ejecutor por lotes del LegalAgent: lee preguntas, escribe submissions.jsonl y lo valida.

    python -m src.agent.batch_runner --entrada data/sample_50.jsonl --salida entregables/submissions.jsonl
    python -m src.agent.batch_runner --limite 3 --mock --salida test_submissions.jsonl
    python -m src.agent.batch_runner --juez --formato multiple_choice --salida cerradas.jsonl   # solo las cerradas
    python -m src.agent.batch_runner --juez      # con LLM as judge (máx. 2 ciclos); traza en <salida>.juez.jsonl
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import time
from pathlib import Path

from src.agent.agent import LegalAgent, get_real_retriever, mock_retriever
from src.agent.graph import run_with_judge

ROOT = Path(__file__).resolve().parents[2]
# Se usa el primero que exista: el enlace docs_reto/ del repo (CLAUDE.md), la copia en schema/ o la
# carpeta del reto junto al repo.
SCHEMAS = (ROOT / "docs_reto" / "schema" / "submission.schema.json",
           ROOT / "schema" / "submission.schema.json",
           ROOT.parent / "HackathonAI" / "schema" / "submission.schema.json",
           Path("C:/Users/choco/Documents/COURSES/HackathonAI/schema/submission.schema.json"))
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
    """Con `mock`, pasajes y escritor simulados. Sin `mock`, la recuperación real o un error: una
    corrida real nunca cae en pasajes simulados (el LLM respondería sobre texto inventado)."""
    if mock:
        return LegalAgent(mock_retriever, forzar_mock_escritor=True), "mock"
    try:
        hook = get_real_retriever()
    except Exception as e:  # índices ausentes, dependencias RAG o modelos no disponibles
        raise SystemExit(f"Recuperación real no disponible ({type(e).__name__}: {e}). Descomprimir el índice "
                         f"en corpus/ (CLAUDE.md, sección 6) o correr con --mock para probar sin índices.") from e
    # El subagente de citas solo SUPRIME las citas fuera de los pasajes. Agregar el pasaje de una cita
    # que el LLM escribió sin haberlo leído (CITAS_AGREGAR_PASAJES=1) queda apagado: la afirmación no
    # se redactó con ese texto, y los pasajes dejarían de depender solo de la búsqueda determinista
    # (en la verificación en vivo, otro LLM/CPU puede citar distinto y cambiar los pasajes).
    agregar = os.environ.get("CITAS_AGREGAR_PASAJES", "0") == "1"
    return LegalAgent(lambda s: hook({"pregunta": s.pregunta, "opciones": s.opciones}),
                      buscador_citas=hook.buscar_cita if agregar else None), "real"


def ejecutar(entrada: Path, salida: Path, limite: int | None, mock: bool, juez: bool = False,
             formato: str | None = None) -> int:
    # Solo saltos de línea reales: splitlines() también corta en \x85 o \u2028, que aparecen en textos
    # legales dentro de un JSON y partirían un registro (igual que lee el evaluador oficial).
    items = [json.loads(ln) for ln in entrada.read_text(encoding="utf-8").split("\n") if ln.strip()]
    if limite:
        items = items[:limite]
    if formato:  # p. ej. solo las cerradas, para medir un cambio rápido
        items = [it for it in items if it.get("formato") == formato]
    salida.parent.mkdir(parents=True, exist_ok=True)
    with _candado(salida):
        return _ejecutar(items, salida, mock, juez)


@contextlib.contextmanager
def _candado(salida: Path):
    """Impide que dos corridas escriban el mismo archivo a la vez (sus líneas se entremezclan y el
    evaluador oficial no puede leerlo). Si una corrida murió sin limpiar, borrar el .lock a mano."""
    lock = salida.with_name(salida.name + ".lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit(f"Otra corrida está escribiendo {salida} ({lock} existe). Si no hay ninguna "
                         f"corriendo, borrar {lock} y volver a lanzar.") from None
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)


def _ejecutar(items: list[dict], salida: Path, mock: bool, juez: bool) -> int:
    agente, modo = crear_agente(mock)
    total, errores = len(items), 0
    print(f"== {total} preguntas, retriever {modo}{', con juez' if juez else ''} -> {salida}", flush=True)
    # La traza del juez va aparte: submissions.jsonl solo lleva lo que admite el esquema.
    ruta_traza = salida.with_name(salida.name + ".juez.jsonl")
    with salida.open("w", encoding="utf-8") as f, \
            (ruta_traza.open("w", encoding="utf-8") if juez else contextlib.nullcontext()) as f_traza:
        for i, item in enumerate(items, 1):
            t0 = time.perf_counter()
            try:
                if juez:
                    estado, traza = run_with_judge(agente, item, mock=mock)
                    f_traza.write(json.dumps(traza, ensure_ascii=False) + "\n")
                    f_traza.flush()
                else:
                    estado = agente.run(item)
                registro = LegalAgent.to_submission(estado)
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
    for n, linea in enumerate((ln for ln in salida.read_text(encoding="utf-8").split("\n") if ln.strip()), 1):
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
    ap.add_argument("--formato", choices=FORMATOS, help="solo las preguntas de ese formato")
    ap.add_argument("--mock", action="store_true", help="pasajes simulados, sin cargar índices")
    ap.add_argument("--juez", action="store_true", help="revisa cada borrador con el LLM as judge (máx. 2 ciclos)")
    args = ap.parse_args()
    ejecutar(args.entrada, args.salida, args.limite, args.mock, args.juez, args.formato)


if __name__ == "__main__":
    main()
