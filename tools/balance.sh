#!/usr/bin/env bash
# Prints remaining OpenRouter budget in USD
cd "$(dirname "$0")/.." && export $(grep -v '^#' .env | xargs) && curl -s https://openrouter.ai/api/v1/auth/key -H "Authorization: Bearer $OPENROUTER_API_KEY" | python -c "import json,sys; d=json.load(sys.stdin)['data']; print('remaining USD:', d['limit_remaining'], '| spent:', d['usage'])"
