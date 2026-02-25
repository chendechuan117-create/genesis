API_KEY="${DEEPSEEK_API_KEY}"

echo "=== Request 1 ==="
curl -s -X POST "https://api.deepseek.com/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "model": "deepseek-chat",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant. Here is a long static text to make sure the cache triggers. " '"'"'$(for i in {1..2000}; do echo -n "Static word $i. "; done)'"'"'},
      {"role": "user", "content": "What is 1+1?"}
    ]
  }' | jq '.usage'

echo "=== Request 2 ==="
curl -s -X POST "https://api.deepseek.com/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "model": "deepseek-chat",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant. Here is a long static text to make sure the cache triggers. " '"'"'$(for i in {1..2000}; do echo -n "Static word $i. "; done)'"'"'},
      {"role": "user", "content": "What is 1+2?"}
    ]
  }' | jq '.usage'
