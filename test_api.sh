#!/usr/bin/env bash
# Smoke tests for wow-bot-brain v3
BASE="http://localhost:5000"

echo "=== Health ==="
curl -s "$BASE/health" | python3 -m json.tool

echo ""
echo "=== Chat: whisper from a stranger ==="
curl -s -X POST "$BASE/chat" \
  -H "Content-Type: application/json" \
  -d '{"bot_name":"Hadriano","player_name":"Gus","message":"hey whats up","channel":"WHISPER","location":"Stormwind City"}' \
  | python3 -m json.tool

echo ""
echo "=== Chat: someone says something nearby ==="
curl -s -X POST "$BASE/chat" \
  -H "Content-Type: application/json" \
  -d '{"bot_name":"Irkinklus","player_name":"Gus","message":"anyone wanna run deadmines?","channel":"SAY","location":"Westfall"}' \
  | python3 -m json.tool

echo ""
echo "=== Tick: LFG/trade/general activity ==="
curl -s -X POST "$BASE/tick" \
  -H "Content-Type: application/json" \
  -d '{"bot_name":"Chadro","location":"Ironforge","nearby_players":["Gus"]}' \
  | python3 -m json.tool

echo ""
echo "=== Tick: another bot ==="
curl -s -X POST "$BASE/tick" \
  -H "Content-Type: application/json" \
  -d '{"bot_name":"Gaemwa","location":"Stranglethorn Vale","nearby_players":[]}' \
  | python3 -m json.tool

echo ""
echo "=== Personalities (assigned so far) ==="
curl -s "$BASE/personalities" | python3 -m json.tool
