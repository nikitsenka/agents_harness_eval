#!/usr/bin/env python3
"""Print answer + tool calls + token/latency metrics for one eval run.

Auto-detects the input format:
  - Claude Code  : stream-json (JSONL; final line type=="result")
  - Hermes       : `hermes sessions export` (single-line session object w/ messages[])

Usage: metrics.py <file> [label]
"""
import json, sys

path = sys.argv[1]
label = sys.argv[2] if len(sys.argv) > 2 else path
raw = open(path).read().strip()
lines = [l for l in raw.splitlines() if l.strip()]


def is_cc(lines):
    for l in lines:
        try:
            if json.loads(l).get("type") in ("result", "assistant", "system"):
                return True
        except Exception:
            pass
    return False


def cc(lines):
    tools, result, usage, dur = [], None, {}, None
    for l in lines:
        try:
            o = json.loads(l)
        except Exception:
            continue
        if o.get("type") == "assistant":
            for b in o.get("message", {}).get("content", []):
                if b.get("type") == "tool_use":
                    tools.append(b.get("name"))
        elif o.get("type") == "result":
            result, usage, dur = o.get("result"), o.get("usage", {}), o.get("duration_ms")
    inp = usage.get("input_tokens", 0)
    out = usage.get("output_tokens", 0)
    cr = usage.get("cache_read_input_tokens", 0)
    cw = usage.get("cache_creation_input_tokens", 0)
    lat = f"{round(dur/1000,1)}s" if dur else "?"
    return result, tools, inp, out, cr, cw, lat


def hermes(raw):
    o = json.loads(raw.splitlines()[0])
    msgs = o.get("messages", [])
    tools = [m.get("tool_name") for m in msgs if m.get("tool_name")]
    result = next((m.get("content") for m in reversed(msgs)
                   if m.get("role") == "assistant" and m.get("content")), None)
    uts = [m["timestamp"] for m in msgs if m.get("role") == "user" and m.get("timestamp")]
    ats = [m["timestamp"] for m in msgs if m.get("role") == "assistant" and m.get("timestamp")]
    lat = f"{round(max(ats)-min(uts),1)}s" if uts and ats else "?"
    return (result, tools, o.get("input_tokens", 0), o.get("output_tokens", 0),
            o.get("cache_read_tokens", 0), o.get("cache_write_tokens", 0), lat)


result, tools, inp, out, cr, cw, lat = cc(lines) if is_cc(lines) else hermes(raw)
print(f"=== {label} ===")
print("--- ANSWER ---")
print((str(result) if result else "(no result)").strip()[:1400])
print("--- TOOLS ---")
print(tools)
print("--- METRICS ---")
print(f"[{label}] latency={lat} tools={len(tools)} | "
      f"in={inp} out={out} cacheR={cr} cacheW={cw} total={inp+out+cr+cw}")
