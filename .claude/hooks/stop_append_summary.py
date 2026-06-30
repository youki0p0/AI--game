#!/usr/bin/env python3
import json, time
from pathlib import Path
import sys

try:
    data = json.load(sys.stdin)
except Exception as e:
    data = {"parse_error": str(e)}

Path('.jen/logs').mkdir(parents=True, exist_ok=True)
entry = {
    "ts": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    "event": "Stop",
    "data": data,
}
with open('.jen/logs/stop-events.jsonl', 'a', encoding='utf-8') as f:
    f.write(json.dumps(entry, ensure_ascii=False) + '\n')
