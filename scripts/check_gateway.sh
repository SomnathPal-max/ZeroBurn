#!/usr/bin/env bash
# scripts/check_gateway.sh - Verify Bifrost gateway and virtual key provider restrictions
set -e

# Load .env if present
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

BIFROST_URL="${BIFROST_URL:-http://localhost:8080/v1}"
# Ensure trailing slash removed
BIFROST_URL="${BIFROST_URL%/}"
# If url ends with /v1, strip it for consistency if needed, but OpenAI endpoint is /chat/completions or /v1/chat/completions
if [[ "$BIFROST_URL" =~ /v1$ ]]; then
  ENDPOINT="$BIFROST_URL/chat/completions"
else
  ENDPOINT="$BIFROST_URL/v1/chat/completions"
fi

BIFROST_VK_STANDARD="${BIFROST_VK_STANDARD:-sk-bf-standard}"
BIFROST_VK_CONFIDENTIAL="${BIFROST_VK_CONFIDENTIAL:-sk-bf-confidential}"
CLOUD_MODEL="${CLOUD_MODEL:-openai/gpt-4o-mini}"
LOCAL_MODEL="${LOCAL_MODEL:-ollama/llama3.2:latest}"

echo "Testing Gateway at $ENDPOINT"
echo "Standard Virtual Key: $BIFROST_VK_STANDARD"
echo "Confidential Virtual Key: $BIFROST_VK_CONFIDENTIAL"

# Check (a): standard key + cloud model succeeds
echo -n "Checking (a) standard key + cloud model: "
RESP_A=$(curl -s -w "\n%{http_code}" -X POST "$ENDPOINT" \
  -H "Authorization: Bearer $BIFROST_VK_STANDARD" \
  -H "x-bf-vk: $BIFROST_VK_STANDARD" \
  -H "Content-Type: application/json" \
  -d "{\"model\": \"$CLOUD_MODEL\", \"messages\": [{\"role\": \"user\", \"content\": \"ping\"}], \"max_tokens\": 5}")

CODE_A=$(echo "$RESP_A" | tail -n 1)
BODY_A=$(echo "$RESP_A" | sed '$d')

if [ "$CODE_A" -eq 200 ]; then
  echo "PASS"
else
  echo "FAIL (HTTP $CODE_A: $BODY_A)"
fi

# Check (b): confidential key + Ollama model succeeds
echo -n "Checking (b) confidential key + Ollama model: "
RESP_B=$(curl -s -w "\n%{http_code}" -X POST "$ENDPOINT" \
  -H "Authorization: Bearer $BIFROST_VK_CONFIDENTIAL" \
  -H "x-bf-vk: $BIFROST_VK_CONFIDENTIAL" \
  -H "Content-Type: application/json" \
  -d "{\"model\": \"$LOCAL_MODEL\", \"messages\": [{\"role\": \"user\", \"content\": \"ping\"}], \"max_tokens\": 5}")

CODE_B=$(echo "$RESP_B" | tail -n 1)
BODY_B=$(echo "$RESP_B" | sed '$d')

if [ "$CODE_B" -eq 200 ]; then
  echo "PASS"
else
  echo "FAIL (HTTP $CODE_B: $BODY_B)"
fi

# Check (c): confidential key + cloud model is rejected by the gateway
echo -n "Checking (c) confidential key + cloud model rejected: "
RESP_C=$(curl -s -w "\n%{http_code}" -X POST "$ENDPOINT" \
  -H "Authorization: Bearer $BIFROST_VK_CONFIDENTIAL" \
  -H "x-bf-vk: $BIFROST_VK_CONFIDENTIAL" \
  -H "Content-Type: application/json" \
  -d "{\"model\": \"$CLOUD_MODEL\", \"messages\": [{\"role\": \"user\", \"content\": \"ping\"}], \"max_tokens\": 5}")

CODE_C=$(echo "$RESP_C" | tail -n 1)
BODY_C=$(echo "$RESP_C" | sed '$d')

if [ "$CODE_C" -eq 403 ] || [ "$CODE_C" -eq 400 ] || [ "$CODE_C" -eq 422 ]; then
  echo "PASS (Rejected with HTTP $CODE_C)"
else
  echo "FAIL (Expected HTTP 403/400/422, got HTTP $CODE_C: $BODY_C)"
fi
