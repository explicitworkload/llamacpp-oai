#!/usr/bin/sh
set -e

# Find the first GGUF model in the mounted directory
MODEL_FILE=$(find /mnt/models -type f -name "*.gguf" | head -n 1)

if [ -z "$MODEL_FILE" ]; then
  echo "ERROR: No .gguf file found in /mnt/models"
  exit 1
fi

echo "Starting llama-server with model: $MODEL_FILE"

# "$@" passes through custom runtime arguments configured in the OpenShift AI UI
exec llama-server -m "$MODEL_FILE" --host 0.0.0.0 --port 8080 --alias default "$@"