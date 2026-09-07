#!/usr/bin/sh
set -e

MODEL_FILE=$(find /mnt/models -type f -name "*.gguf" | head -n 1)

if [ -z "$MODEL_FILE" ]; then
  echo "ERROR: No .gguf file found in /mnt/models"
  exit 1
fi

CONTEXT_LENGTH="${CONTEXT_LENGTH:-2048}"
N_GPU_LAYERS="${N_GPU_LAYERS:-99}"

FA_FLAG=""
if [ "${FLASH_ATTENTION}" = "on" ]; then
  FA_FLAG="-fa"
fi

echo "Starting llama-server with model: $MODEL_FILE (context: $CONTEXT_LENGTH, gpu layers: $N_GPU_LAYERS)"

# $EXTRA_ARGS is intentionally unquoted to allow word splitting for multiple flags
# "$@" passes through any args from KServe or the ServingRuntime command
exec llama-server \
  -m "$MODEL_FILE" \
  --host 0.0.0.0 \
  --port 8080 \
  -c "$CONTEXT_LENGTH" \
  -ngl "$N_GPU_LAYERS" \
  $FA_FLAG \
  --alias default \
  $EXTRA_ARGS \
  "$@"
