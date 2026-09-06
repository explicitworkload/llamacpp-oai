#!/usr/bin/sh
set -e

MODEL_FILE=$(find /mnt/models -type f -name "*.gguf" | head -n 1)

if [ -z "$MODEL_FILE" ]; then
  echo "ERROR: No .gguf file found in /mnt/models"
  exit 1
fi

echo "Starting lemonade server with model: $MODEL_FILE"

# Start lemond in background on port 8080
./lemond --host 0.0.0.0 --port 8080 &
LEMOND_PID=$!

# Wait for server to be ready
until curl -sf http://localhost:8080/live > /dev/null 2>&1; do
  sleep 1
done

# Load the GGUF model with ROCm backend
curl -sf -X POST http://localhost:8080/v1/load \
  -H "Content-Type: application/json" \
  -d "{\"model_path\": \"$MODEL_FILE\", \"llamacpp_backend\": \"rocm\"}" || {
  echo "WARNING: Model load via API failed, server may still accept requests"
}

echo "Lemonade server ready on port 8080"

wait $LEMOND_PID
