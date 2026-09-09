"""Print the last assistant reply of a Claude Code transcript (JSONL), ready to be spoken:
code blocks collapsed, inline code and links unwrapped, tables flattened, markdown marks
dropped, a trailing `-signature` line removed."""
import re
import sys

last = None
for line in open(sys.argv[1], encoding="utf-8", errors="ignore"):
    try:
        j = __import__("json").loads(line)
    except Exception:
        continue
    if j.get("type") != "assistant":
        continue
    parts = [c.get("text", "") for c in j.get("message", {}).get("content", [])
             if isinstance(c, dict) and c.get("type") == "text"]
    t = "\n".join(p for p in parts if p.strip())
    if t.strip():
        last = t
if not last:
    sys.exit(0)
t = last
t = re.sub(r"```.*?```", " code block omitted. ", t, flags=re.S)
t = re.sub(r"`([^`]*)`", r"\1", t)
t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
t = re.sub(r"https?://\S+", "link", t)
t = re.sub(r"^\s*\|[-| :]+\|\s*$", "", t, flags=re.M)          # table rule rows
t = re.sub(r"^\s*\|(.*)\|\s*$", lambda m: ", ".join(c.strip() for c in m.group(1).split("|")), t, flags=re.M)
t = re.sub(r"^\s*[-*]{3,}\s*$", "", t, flags=re.M)
t = re.sub(r"[#*_>~]+", "", t)
t = re.sub(r"(?:^|\s)-[a-z]{2,12}\s*$", "", t.strip())         # "-code" style sign-off, not "self-hosted"
t = re.sub(r"[ \t]+", " ", t)
t = re.sub(r"\n{2,}", ". \n", t)
print(t.strip())
