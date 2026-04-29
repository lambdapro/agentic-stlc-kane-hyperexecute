#!/bin/bash
set -e

# Start Ollama server in background
ollama serve &
OLLAMA_PID=$!
sleep 3
echo "=== Ollama running (pid $OLLAMA_PID) ==="
ollama list

# Start LiteLLM proxy — capture output so errors are visible in docker logs
litellm --config /etc/litellm/config.yaml --port 4000 > /tmp/litellm.log 2>&1 &
LITELLM_PID=$!
echo "=== LiteLLM starting (pid $LITELLM_PID) ==="

# Wait up to 60s for LiteLLM to become ready
TIMEOUT=60
COUNT=0
until curl -sf http://localhost:4000/health > /dev/null 2>&1; do
  COUNT=$((COUNT + 1))
  if [ $COUNT -ge $TIMEOUT ]; then
    echo "=== ERROR: LiteLLM did not start after ${TIMEOUT}s ==="
    echo "=== LiteLLM log ==="
    cat /tmp/litellm.log
    exit 1
  fi
  # Print litellm log every 10s so GitHub Actions shows progress
  if [ $((COUNT % 10)) -eq 0 ]; then
    echo "--- litellm log at ${COUNT}s ---"
    cat /tmp/litellm.log
  fi
  sleep 1
done

echo "=== LiteLLM proxy ready on port 4000 ==="

# Keep container alive — trap signals for clean shutdown
wait $OLLAMA_PID $LITELLM_PID
