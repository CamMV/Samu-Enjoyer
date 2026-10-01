"""Ciclo escritor -> juez -> reintento (máximo 2 ciclos), montado por fuera de `LegalAgent`.

Si el juez rechaza el primer borrador, se vuelve a recuperar con la consulta ajustada por su
feedback y se redacta de nuevo con los pasajes nuevos. La pregunta que ve el escritor no cambia:
solo cambia la evidencia.

Configuración por entorno o .env:
    JUDGE_ABSTENER  0 desactiva la abstención forzada cuando el juez declara, en todos los
                    ciclos, que los pasajes no bastan (default 1)
"""
from __future__ import annotations

import os
from typing import Callable, Optional

from src.agent.agent import LegalAgent
from src.agent.schemas import QuestionState
from src.agent.tools.judge_tool import Veredicto, evaluate_with_judge, mock_evaluate_with_judge
from src.agent.tools.writer_tool import _abstencion

JUDGE_ABSTENER = os.environ.get("JUDGE_ABSTENER", "1") != "0"

Juez = Callable[[QuestionState], Veredicto]


def _consulta_ajustada(state: QuestionState, veredicto: Veredicto) -> str:
    extra = veredicto.consulta_sugerida or veredicto.feedback
    return f"{state.pregunta}\n{extra}".strip()


def _anotar(state: QuestionState, veredicto: Veredicto, ciclo: int, consultas: list[str]) -> None:
    state.ciclo_actual = ciclo
    state.queries_generadas = list(consultas)
    state.aprobado_por_juez = veredicto.aprobado
    state.juez_feedback = veredicto.feedback or None
    state.citas_invalidas = list(veredicto.citas_invalidas)


def run_with_judge(agente: LegalAgent, raw_item: dict, juez: Optional[Juez] = None,
                   mock: bool = False) -> tuple[QuestionState, dict]:
    """Ejecuta el agente con revisión del juez. Devuelve (estado final, traza del juez).

    `juez` por defecto es el real (`evaluate_with_judge`), o el simulado si `mock`. La traza es
    para depurar y medir; no va en submissions.jsonl."""
    juez = juez or (mock_evaluate_with_judge if mock else evaluate_with_judge)
    state = agente.run(raw_item)
    consultas = [state.pregunta]
    intentos: list[tuple[QuestionState, Veredicto]] = []
    while True:
        veredicto = juez(state)
        _anotar(state, veredicto, len(intentos) + 1, consultas)
        intentos.append((state, veredicto))
        if veredicto.aprobado is not False or len(intentos) >= state.max_ciclos or agente.retriever is None:
            break
        consulta = _consulta_ajustada(state, veredicto)
        pasajes = agente.retriever(state.model_copy(update={"pregunta": consulta}))[:10]
        if [p.id for p in pasajes] == [p.id for p in state.pasajes_recuperados]:
            break  # misma evidencia: con temperature=0 el escritor repetiría el borrador
        consultas.append(consulta)
        state = agente.run(raw_item, pasajes=pasajes)

    # Sin aprobación se entrega el borrador con menos problemas (en empate, el más reciente).
    state, veredicto = next(((s, v) for s, v in intentos if v.aprobado is not False),
                            min(reversed(intentos), key=lambda sv: sv[1].problemas))
    abstencion_forzada = (JUDGE_ABSTENER and not state.abstencion
                          and all(v.aprobado is False and not v.pasajes_suficientes for _, v in intentos))
    if abstencion_forzada:
        state.borrador_respuesta = _abstencion(state.formato)
        state.abstencion = True
    traza = {
        "id": state.id,
        "formato": state.formato,
        "ciclos": len(intentos),
        "ciclo_elegido": state.ciclo_actual,
        "aprobado": veredicto.aprobado,
        "abstencion_forzada": abstencion_forzada,
        "consultas": consultas,
        "veredictos": [v.model_dump() for _, v in intentos],
    }
    return state, traza
