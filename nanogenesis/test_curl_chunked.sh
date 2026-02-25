#!/bin/bash
API_KEY=$DEEPSEEK_API_KEY
URL="https://api.deepseek.com/chat/completions"

echo "=== Run 1: Curl with explicit file (sends Content-Length) ==="
curl -k -s -X POST $URL \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  --data-binary @data1.json > out1.json

grep -o '"prompt_cache_hit_tokens":[0-9]*' out1.json

sleep 2

echo "=== Run 2: Curl with explicit file (sends Content-Length) ==="
curl -k -s -X POST $URL \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  --data-binary @data2.json > out2.json

grep -o '"prompt_cache_hit_tokens":[0-9]*' out2.json

sleep 2

echo "=== Run 3: Curl with stdin (sends Transfer-Encoding: chunked) ==="
cat data2.json | curl -k -s -X POST $URL \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  --data-binary @- > out3.json

grep -o '"prompt_cache_hit_tokens":[0-9]*' out3.json

