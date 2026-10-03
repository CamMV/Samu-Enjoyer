#!/usr/bin/env bash
# Comando único de reproducción — Samu-Enjoyer, Hackathon IA Week 2026.
#
#   bash run.sh                 # las 50 preguntas de muestra + evaluador oficial (sin RAGAS)
#   bash run.sh --split test    # las 992 preguntas del test (logs/submissions_test.jsonl)
#   bash run.sh --limite 3      # solo las primeras N preguntas (prueba rápida)
#
# Hace, en orden y solo lo que falte:
#   1. instala las dependencias de Python (requirements.txt);
#   2. descarga y descomprime el corpus y el índice (CORPUS_URL) si no está corpus/;
#   3. descarga el GGUF de Qwen3-8B (Q4_K_M) si no está en modelos/;
#   4. arranca llama-server con la configuración de la entrega (T=0, -np 1), si no hay uno corriendo;
#   5. genera las respuestas con el agente y, en la muestra, las evalúa con scripts/evaluate.py.
#
# Variables opcionales (también se pueden poner en .env):
#   CORPUS_URL     enlace del zip del corpus e índice (por defecto, el de la sección "Corpus e índice")
#   GGUF           ruta del GGUF (por defecto modelos/Qwen3-8B-Q4_K_M.gguf)
#   LLAMA_SERVER   ejecutable de llama.cpp (por defecto, llama-server del PATH)
#   LLM_PORT       puerto del LLM (por defecto 8010; el 8000 es del back de la interfaz)
#   NGL            capas del LLM en GPU (por defecto 99 = todas; 0 = solo CPU)
#   SIN_PIP=1      no correr pip install
#
# No modifica submissions.jsonl: la corrida del test se escribe en logs/submissions_test.jsonl.

set -euo pipefail
cd "$(dirname "$0")"

# ------------------------------------------------------------------ argumentos
SPLIT=sample
LIMITE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --split)  SPLIT="$2"; shift 2 ;;
    --limite) LIMITE="$2"; shift 2 ;;
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    *) echo "Argumento desconocido: $1 (ver bash run.sh --help)" >&2; exit 2 ;;
  esac
done
case "$SPLIT" in
  sample) ENTRADA=data/sample_50.jsonl; SALIDA=logs/submissions_sample.jsonl ;;
  test)   ENTRADA=data/test_992.jsonl;  SALIDA=logs/submissions_test.jsonl ;;
  *) echo "--split debe ser sample o test" >&2; exit 2 ;;
esac

# .env (si existe) para CORPUS_URL, GGUF, LLAMA_SERVER, RAG_DEVICE_DENSO, etc.
if [[ -f .env ]]; then set -a; source .env; set +a; fi

CORPUS_URL="${CORPUS_URL:-PENDIENTE}"   # reemplazar PENDIENTE por el enlace público del zip
GGUF="${GGUF:-modelos/Qwen3-8B-Q4_K_M.gguf}"
LLAMA_SERVER="${LLAMA_SERVER:-llama-server}"
LLM_PORT="${LLM_PORT:-8010}"
NGL="${NGL:-99}"
export LLM_BASE_URL="http://127.0.0.1:${LLM_PORT}/v1"
PY="${PYTHON:-python3}"

paso() { echo; echo "== $*"; }
mkdir -p logs modelos

# ------------------------------------------------------------------ 1. dependencias
if [[ "${SIN_PIP:-0}" != "1" ]]; then
  paso "1/5 Dependencias de Python"
  "$PY" -m pip install -q -r requirements.txt
else
  paso "1/5 Dependencias de Python: omitido (SIN_PIP=1)"
fi

# ------------------------------------------------------------------ 2. corpus e índice
paso "2/5 Corpus e índice"
faltan_indices() {
  [[ ! -f corpus/chunks/chunks.sqlite ]] && return 0
  for d in bm25_todo bm25_normas qwen3-emb-0.6b_todo qwen3-emb-0.6b_normas; do
    [[ -d "corpus/indices/$d" ]] || return 0
  done
  return 1
}
if faltan_indices; then
  if [[ "$CORPUS_URL" == "PENDIENTE" ]]; then
    echo "Falta corpus/ y no hay CORPUS_URL. Descargar samu_enjoyer_corpus_indice.zip (README," >&2
    echo "sección 'Corpus e índice') y descomprimirlo en la raíz, o correr: CORPUS_URL=<enlace> bash run.sh" >&2
    exit 1
  fi
  ZIP=modelos/samu_enjoyer_corpus_indice.zip
  if [[ ! -f "$ZIP" ]]; then
    if [[ "$CORPUS_URL" == *drive.google.com* ]]; then
      "$PY" -m pip install -q gdown
      "$PY" -m gdown --fuzzy "$CORPUS_URL" -O "$ZIP"
    else
      curl -L --fail -o "$ZIP" "$CORPUS_URL"
    fi
  fi
  "$PY" -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall('.')" "$ZIP"
  faltan_indices && { echo "El zip no dejó corpus/chunks y corpus/indices completos." >&2; exit 1; }
  "$PY" -m src.knowledge.verify_indices || true
else
  echo "corpus/ ya está: chunks.sqlite y los 4 índices"
fi

# ------------------------------------------------------------------ 3. modelo del LLM
paso "3/5 Qwen3-8B (GGUF Q4_K_M)"
if [[ ! -f "$GGUF" ]]; then
  "$PY" -c "from huggingface_hub import hf_hub_download as d; d('Qwen/Qwen3-8B-GGUF', 'Qwen3-8B-Q4_K_M.gguf', local_dir='modelos')"
  GGUF=modelos/Qwen3-8B-Q4_K_M.gguf
fi
echo "$GGUF"

# ------------------------------------------------------------------ 4. servidor del LLM
paso "4/5 llama-server en el puerto $LLM_PORT"
LLM_PID=""
detener_llm() { [[ -n "$LLM_PID" ]] && kill "$LLM_PID" 2>/dev/null || true; }
trap detener_llm EXIT

if curl -sf "http://127.0.0.1:${LLM_PORT}/health" >/dev/null; then
  echo "Ya hay un llama-server en el puerto $LLM_PORT: se usa ese (debe tener la configuración de abajo)."
else
  if ! command -v "$LLAMA_SERVER" >/dev/null; then
    echo "No se encontró llama-server. Instalar llama.cpp con CUDA o indicar la ruta: LLAMA_SERVER=<ruta> bash run.sh" >&2
    exit 1
  fi
  # Configuración de la entrega: contexto 32k, una petición a la vez, temperatura 0, semilla fija.
  "$LLAMA_SERVER" -m "$GGUF" --host 127.0.0.1 --port "$LLM_PORT" -c 32768 -np 1 \
      --jinja --temp 0 --top-k 1 --seed 42 -ngl "$NGL" > logs/llama_server.log 2>&1 &
  LLM_PID=$!
  echo -n "esperando a que cargue el modelo"
  for _ in $(seq 1 300); do
    curl -sf "http://127.0.0.1:${LLM_PORT}/health" >/dev/null && break
    kill -0 "$LLM_PID" 2>/dev/null || { echo; echo "llama-server terminó; ver logs/llama_server.log" >&2; exit 1; }
    echo -n "."; sleep 2
  done
  echo
  curl -sf "http://127.0.0.1:${LLM_PORT}/health" >/dev/null || { echo "llama-server no respondió en 10 min" >&2; exit 1; }
fi

# ------------------------------------------------------------------ 5. respuestas y evaluación
paso "5/5 Agente sobre $ENTRADA -> $SALIDA"
rm -f "$SALIDA"
"$PY" -m src.agent.batch_runner --entrada "$ENTRADA" --salida "$SALIDA" ${LIMITE:+--limite "$LIMITE"}

if [[ "$SPLIT" == "sample" && -z "$LIMITE" ]]; then
  paso "Evaluador oficial (sin RAGAS)"
  "$PY" scripts/evaluate.py --submission "$SALIDA" --split sample --out logs/eval_sample.json
fi

paso "Listo: $SALIDA"
