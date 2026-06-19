#!/usr/bin/env python3
"""Print answer + tool calls + token/latency + context-efficiency for one eval run.

The CONTEXT line reports context fill (ctx_peak, ctx/turn), cache-write ratio,
and compaction count. Per-turn context needs per-message usage: Claude Code's
stream-json has it; Hermes exports currently leave message token_count empty, so
its ctx_peak/ctx/turn read n/a (cacheW_ratio still applies).

Auto-detects the input format:
  - Claude Code  : stream-json (JSONL; final line type=="result")
  - Hermes       : `hermes sessions export` (single-line session object w/ messages[])

Usage: metrics.py <file> [label]
"""
import json, sys

# Approx AWS Bedrock Claude Sonnet 4.x pricing, USD per 1M tokens. Cache reads are
# ~10% of input and cache writes ~1.25x, which is why a raw token `total` overstates
# the dollar cost of a harness that reloads a big cached prefix each turn.
PRICE_PER_M = {"in": 3.0, "out": 15.0, "cacheR": 0.30, "cacheW": 3.75}


def cost_usd(inp, out, cr, cw):
    return round((inp * PRICE_PER_M["in"] + out * PRICE_PER_M["out"]
                  + cr * PRICE_PER_M["cacheR"] + cw * PRICE_PER_M["cacheW"]) / 1_000_000, 5)


def is_cc(lines):
    for l in lines:
        try:
            if json.loads(l).get("type") in ("result", "assistant", "system"):
                return True
        except Exception:
            pass
    return False


def ctx_stats(series, compactions):
    """Context-efficiency stats from a per-turn context-size series.
    peak = largest context reached; slope = tokens added per turn (fill rate)."""
    turns = len(series)
    peak = max(series) if series else 0
    if turns > 1:
        slope = round((series[-1] - series[0]) / (turns - 1))
    else:
        slope = series[0] if series else 0
    return {"peak": peak, "turns": turns, "slope": slope, "compactions": compactions}


def cc(lines):
    tools, result, usage, dur = [], None, {}, None
    ctx_series, compactions = [], 0
    for l in lines:
        try:
            o = json.loads(l)
        except Exception:
            continue
        t = o.get("type")
        if t == "assistant":
            msg = o.get("message", {})
            for b in msg.get("content", []):
                if b.get("type") == "tool_use":
                    tools.append(b.get("name"))
            u = msg.get("usage", {})
            # actual input context fed to the model on this turn
            turn_ctx = (u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                        + u.get("cache_creation_input_tokens", 0))
            if turn_ctx:
                ctx_series.append(turn_ctx)
        elif t == "system":
            if "compact" in str(o.get("subtype", "")).lower():
                compactions += 1
        elif t == "result":
            result, usage, dur = o.get("result"), o.get("usage", {}), o.get("duration_ms")
    inp = usage.get("input_tokens", 0)
    out = usage.get("output_tokens", 0)
    cr = usage.get("cache_read_input_tokens", 0)
    cw = usage.get("cache_creation_input_tokens", 0)
    lat = f"{round(dur/1000,1)}s" if dur else "?"
    return result, tools, inp, out, cr, cw, lat, ctx_stats(ctx_series, compactions)


def hermes(raw):
    o = json.loads(raw.splitlines()[0])
    msgs = o.get("messages", [])
    tools = [m.get("tool_name") for m in msgs if m.get("tool_name")]
    result = next((m.get("content") for m in reversed(msgs)
                   if m.get("role") == "assistant" and m.get("content")), None)
    uts = [m["timestamp"] for m in msgs if m.get("role") == "user" and m.get("timestamp")]
    ats = [m["timestamp"] for m in msgs if m.get("role") == "assistant" and m.get("timestamp")]
    lat = f"{round(max(ats)-min(uts),1)}s" if uts and ats else "?"
    # no per-turn input usage in the export; reconstruct the curve from cumulative
    # message sizes (token_count) — approximate, compare trends not absolutes.
    cum, ctx_series = 0, []
    for m in msgs:
        cum += m.get("token_count", 0) or 0
        ctx_series.append(cum)
    return (result, tools, o.get("input_tokens", 0), o.get("output_tokens", 0),
            o.get("cache_read_tokens", 0), o.get("cache_write_tokens", 0), lat,
            ctx_stats(ctx_series, None))


def parse_file(path):
    """Parse one run file into a metrics dict (importable for aggregation)."""
    raw = open(path).read().strip()
    lines = [l for l in raw.splitlines() if l.strip()]
    fmt_cc = is_cc(lines)
    result, tools, inp, out, cr, cw, lat, ctx = cc(lines) if fmt_cc else hermes(raw)
    lat_s = float(lat[:-1]) if lat.endswith("s") and lat[:-1].replace(".", "").isdigit() else None
    return {"format": "cc" if fmt_cc else "hermes", "result": result, "tools": tools,
            "in": inp, "out": out, "cacheR": cr, "cacheW": cw, "total": inp + out + cr + cw,
            "cost_usd": cost_usd(inp, out, cr, cw),
            "lat": lat, "lat_s": lat_s, "ctx": ctx,
            "cacheW_ratio": round(cw / (cr + cw), 2) if (cr + cw) else 0}


def main():
    path = sys.argv[1]
    label = sys.argv[2] if len(sys.argv) > 2 else path
    d = parse_file(path)
    comp = d["ctx"]["compactions"] if d["ctx"]["compactions"] is not None else "?"
    print(f"=== {label} ===")
    print("--- ANSWER ---")
    print((str(d["result"]) if d["result"] else "(no result)").strip()[:1400])
    print("--- TOOLS ---")
    print(d["tools"])
    print("--- METRICS ---")
    print(f"[{label}] latency={d['lat']} tools={len(d['tools'])} | "
          f"in={d['in']} out={d['out']} cacheR={d['cacheR']} cacheW={d['cacheW']} "
          f"total={d['total']} cost=${d['cost_usd']}")
    print("--- CONTEXT ---")
    # peak==0 means no per-turn token data in the telemetry (e.g. Hermes exports
    # leave message token_count empty) — report n/a rather than a misleading 0.
    if d["ctx"]["peak"]:
        head = f"ctx_peak={d['ctx']['peak']} ctx/turn={d['ctx']['slope']} turns={d['ctx']['turns']}"
    else:
        head = f"ctx_peak=n/a ctx/turn=n/a turns={d['ctx']['turns']}"
    print(f"[{label}] {head} cacheW_ratio={d['cacheW_ratio']} compactions={comp}")


if __name__ == "__main__":
    main()
