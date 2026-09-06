#!/usr/bin/sh
set -e

MODEL_FILE=$(find /mnt/models -type f -name "*.gguf" | head -n 1)

if [ -z "$MODEL_FILE" ]; then
  echo "ERROR: No .gguf file found in /mnt/models"
  exit 1
fi

# KServe sends the InferenceService name as the model name.
# /mnt/models is read-only, so symlink from a writable directory.
ISVC_NAME="${HOSTNAME%%-predictor-*}"
MODELS_DIR="/tmp/models"
mkdir -p "$MODELS_DIR"
ln -sf "$MODEL_FILE" "$MODELS_DIR/${ISVC_NAME}.gguf"
echo "Symlinked model as: ${ISVC_NAME}.gguf -> $MODEL_FILE"

echo "Starting lemonade server"

exec ./lemond --host 0.0.0.0 --port 8080
