#!/usr/bin/sh
set -e

MODEL_FILE=$(find /mnt/models -type f -name "*.gguf" | head -n 1)

if [ -z "$MODEL_FILE" ]; then
  echo "ERROR: No .gguf file found in /mnt/models"
  exit 1
fi

MODEL_BASE=$(basename "$MODEL_FILE" .gguf)

echo "Found model: $MODEL_FILE"
echo "Starting lemonade server"

./lemond --host 0.0.0.0 --port 8080 &
LEMOND_PID=$!

until curl -sf http://localhost:8080/live > /dev/null 2>&1; do
  sleep 1
done

# KServe sends the InferenceService name as the model name.
# Register the extra model under that alias so requests resolve.
ISVC_NAME="${HOSTNAME%%-predictor-*}"
if [ -n "$ISVC_NAME" ] && [ "$ISVC_NAME" != "$MODEL_BASE" ]; then
  echo "Registering model alias: $ISVC_NAME -> $MODEL_BASE"
  curl -sf -X POST http://localhost:8080/v1/pull \
    -H "Content-Type: application/json" \
    -d "{\"model_name\": \"user.$ISVC_NAME\", \"recipe\": \"llamacpp\", \"checkpoint\": \"file://$MODEL_FILE\"}" || \
    echo "WARNING: Failed to register model alias"
fi

wait $LEMOND_PID
