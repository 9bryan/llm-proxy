#!/usr/bin/env bash
set -euo pipefail

URL="${URL:-http://localhost:8000/v1/chat/completions}"
API_KEY="${API_KEY:-sk-proxy-example}"
MODEL="${MODEL:-gpt-4o}"
PROMPT="${PROMPT:-Say hello from curl-test.sh}"

curl -sS -X POST "$URL" \
  -H "Authorization: Bearer ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d @- <<EOF
{
  "model": "${MODEL}",
  "messages": [{"role": "user", "content": "${PROMPT}"}]
}
EOF
echo
