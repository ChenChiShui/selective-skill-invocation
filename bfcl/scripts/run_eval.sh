#!/bin/bash
# Run BFCL evaluation with skill-enabled model via vLLM.
#
# Usage:
#   bash bfcl/scripts/run_eval.sh \
#       --model-path    /path/to/checkpoint \
#       --data-dir      /path/to/bfcl_eval/data \
#       --func-doc-dir  /path/to/bfcl_eval/data/multi_turn_func_doc \
#       --output-dir    eval_results/bfcl \
#       [--port 8700] [--tp 4] [--no-skill]

set -e

MODEL_PATH=""
DATA_DIR=""
FUNC_DOC_DIR=""
OUTPUT_DIR=""
PORT=8700
TP=4
NO_SKILL=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --model-path)  MODEL_PATH="$2"; shift 2 ;;
    --data-dir)    DATA_DIR="$2"; shift 2 ;;
    --func-doc-dir) FUNC_DOC_DIR="$2"; shift 2 ;;
    --output-dir)  OUTPUT_DIR="$2"; shift 2 ;;
    --port)        PORT="$2"; shift 2 ;;
    --tp)          TP="$2"; shift 2 ;;
    --no-skill)    NO_SKILL="--no-skill"; shift ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

if [ -z "$MODEL_PATH" ] || [ -z "$DATA_DIR" ] || [ -z "$OUTPUT_DIR" ]; then
  echo "Usage: bash bfcl/scripts/run_eval.sh --model-path ... --data-dir ... --output-dir ..."
  exit 1
fi

FUNC_DOC_DIR="${FUNC_DOC_DIR:-$DATA_DIR/multi_turn_func_doc}"
PYTHON="${PYTHON:-python3}"
REPO="$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")"

mkdir -p "$OUTPUT_DIR"

# Start vLLM server
echo "Starting vLLM server (model: $MODEL_PATH, port: $PORT, tp: $TP)..."
$PYTHON -m vllm.entrypoints.openai.api_server \
  --model "$MODEL_PATH" --port "$PORT" \
  --tensor-parallel-size "$TP" \
  --max-model-len 32768 --trust-remote-code \
  --enable-prefix-caching --dtype bfloat16 &

VLLM_PID=$!
echo "Waiting for vLLM server to start..."
sleep 120

# Run eval
echo "Running BFCL evaluation..."
cd "$REPO"
$PYTHON bfcl/scripts/eval.py \
  --vllm-url "http://localhost:${PORT}/v1" \
  --model-name "$(basename $MODEL_PATH)" \
  --skills-dir bfcl/skills \
  --data-dir "$DATA_DIR" \
  --func-doc-dir "$FUNC_DOC_DIR" \
  --output-dir "$OUTPUT_DIR" \
  --python-bin "$PYTHON" \
  $NO_SKILL

kill $VLLM_PID 2>/dev/null || true
echo "Done. Results in: $OUTPUT_DIR"
