#!/usr/bin/env python3
from pathlib import Path
import json

paths = ['.jen/mission.md', '.jen/tasks.json', '.jen/verification.md', '.jen/handoff.md']
for p in paths:
    path = Path(p)
    print(f"\n## {p}")
    if path.exists():
        text = path.read_text(encoding='utf-8')
        print(text[-4000:])
    else:
        print('(missing)')
