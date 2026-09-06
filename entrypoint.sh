#!/usr/bin/sh
set -e

MODEL_FILE=$(find /mnt/models -type f -name "*.gguf" | head -n 1)

if [ -z "$MODEL_FILE" ]; then
  echo "ERROR: No .gguf file found in /mnt/models"
  exit 1
fi

# KServe sends the InferenceService name as the model name.
# Symlink the GGUF so lemonade registers it under that name via extra_models_dir.
ISVC_NAME="${HOSTNAME%%-predictor-*}"
if [ -n "$ISVC_NAME" ]; then
  ln -sf "$MODEL_FILE" "/mnt/models/${ISVC_NAME}.gguf"
  echo "Symlinked model as: ${ISVC_NAME}.gguf -> $MODEL_FILE"
fi

echo "Starting lemonade server"

exec ./lemond --host 0.0.0.0 --port 8080
