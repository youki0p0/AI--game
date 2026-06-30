#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path

try:
    data = json.load(sys.stdin)
except Exception as e:
    data = {"parse_error": str(e)}

Path('.jen/logs').mkdir(parents=True, exist_ok=True)
entry = {
    "ts": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    "event": "PostToolUse",
    "data": data,
}
with open('.jen/logs/tool-events.jsonl', 'a', encoding='utf-8') as f:
    f.write(json.dumps(entry, ensure_ascii=False) + '\n')
