#!/usr/bin/env python3
import json, re, sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

tool = data.get("tool_name") or data.get("tool") or ""
cmd = ""
if isinstance(data.get("tool_input"), dict):
    cmd = data["tool_input"].get("command") or data["tool_input"].get("cmd") or ""
cmd_l = cmd.lower()

patterns = [
    (r"\brm\s+-rf\s+/(\s|$)", "rm -rf / is forbidden"),
    (r"\brm\s+-rf\s+\.\.(/|\s|$)", "rm -rf outside repository is forbidden"),
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard requires human approval"),
    (r"\bgit\s+push\b.*\s--force", "force push requires human approval"),
    (r"\b(npm|pnpm|yarn)\s+publish\b", "package publish requires human approval"),
    (r"\b(vercel|netlify|firebase|supabase)\s+deploy\b", "deployment requires human approval"),
    (r"\b(drop|truncate)\s+table\b", "destructive database operation requires human approval"),
    (r"\bchmod\s+-r\s+777\b", "recursive chmod 777 is forbidden"),
]

if tool.lower() == "bash" or cmd:
    for pat, reason in patterns:
        if re.search(pat, cmd_l):
            print(f"JEN_GUARD_BLOCKED: {reason}\nCommand: {cmd}", file=sys.stderr)
            sys.exit(2)

sys.exit(0)
