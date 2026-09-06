#!/usr/bin/sh
set -e

MODEL_FILE=$(find /mnt/models -type f -name "*.gguf" | head -n 1)

if [ -z "$MODEL_FILE" ]; then
  echo "ERROR: No .gguf file found in /mnt/models"
  exit 1
fi

echo "Found model: $MODEL_FILE"
echo "Starting lemonade server with --extra-models-dir /mnt/models"

exec ./lemond --host 0.0.0.0 --port 8080 --extra-models-dir /mnt/models
