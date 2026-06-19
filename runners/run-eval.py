#!/usr/bin/env python3
"""Deterministic driver for the harness A/B eval.

Reads scenarios/scenarios.yaml, runs each scenario against a harness via the
existing runners, applies deterministic `checks`, then asks a BLIND judge for an
open-ended verdict. Writes results.json + metrics.csv under results/.

Usage:
  python3 runners/run-eval.py --harness cc      [--only s32,s33] [--no-judge]
  python3 runners/run-eval.py --harness hermes  --out results/hermes-run

Run from the repo root. The target harness must be up (docker compose up -d).
"""
import argparse, csv, json, os, re, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yaml
from metrics import parse_file
from judge import judge as blind_judge

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS = {
    "cc":     {"runner": "runners/run-cc.sh",     "ws": "clean-cc/workspace", "tmp": "/tmp/cceval_{}.jsonl",
               "compose": "clean-cc/docker-compose.yml", "svc": "cc"},
    "hermes": {"runner": "runners/run-hermes.sh", "ws": "hermes/workspace",   "tmp": "/tmp/hereval_{}.jsonl",
               "compose": "hermes/docker-compose.yml", "svc": "gateway"},
}


def sh(cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, **kw)


def ws_path(h, rel):
    return os.path.join(ROOT, HARNESS[h]["ws"], rel)


# ---- reset / setup ----------------------------------------------------------
CC_SUBTREE = {"workspace": "clean-cc/workspace",
              "memory": "clean-cc/workspace/memory",
              "skills": "clean-cc/workspace/.claude/skills"}


def _git_restore(path):
    # restore tracked seeded files + drop untracked/ignored run artifacts
    sh(["bash", "-lc", f"git checkout -- {path} 2>/dev/null; git clean -fdx {path} >/dev/null 2>&1; true"])


def reset(h, kinds):
    for kind in kinds:
        if h == "cc":
            # clean-cc scaffolding (CLAUDE.md/.claude/memory) is seeded + tracked;
            # restore it to the committed baseline rather than deleting it.
            sub = CC_SUBTREE.get(kind)
            if sub:
                _git_restore(sub)
        else:  # hermes — state lives in hermes-home; workspace is an empty mount
            if kind == "workspace":
                wd = os.path.join(ROOT, HARNESS[h]["ws"])
                for f in os.listdir(wd):
                    if f != ".gitkeep":
                        sh(["rm", "-rf", os.path.join(wd, f)])
            elif kind == "memory":
                sh(["bash", "-lc", "rm -f hermes/hermes-home/memories/USER.md hermes/hermes-home/memories/*.lock"])
            # hermes skills are bundled+host-mounted; per-eval skill reset is best-effort, skipped.


def setup(h, files):
    for f in files or []:
        p = ws_path(h, f["path"])
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            fh.write(f.get("content", ""))


def read_memory(h):
    # both harnesses keep memory on the host mount: hermes-home/memories (hermes)
    # and clean-cc/workspace/memory (cc, via autoMemoryDirectory).
    d = os.path.join(ROOT, "hermes/hermes-home/memories" if h == "hermes" else "clean-cc/workspace/memory")
    out = []
    for f in os.listdir(d):
        if f.endswith(".md"):
            out.append(open(os.path.join(d, f)).read())
    return "\n".join(out)


# ---- runner + checks --------------------------------------------------------
def run_step(h, label, prompt):
    c = HARNESS[h]
    sh(["bash", c["runner"], label, prompt], timeout=300)
    path = c["tmp"].format(label)
    if not os.path.exists(path) or not open(path).read().strip():
        return {"answer": "(no result / run produced no telemetry)", "tools": [], "metrics": None}
    try:
        d = parse_file(path)
    except Exception as e:
        return {"answer": f"(parse error: {e})", "tools": [], "metrics": None}
    return {"answer": d["result"], "tools": [t for t in d["tools"] if t],
            "metrics": {k: d[k] for k in ("in", "out", "cacheR", "cacheW", "total", "cost_usd", "lat_s")}
                       | {"ctx_peak": d["ctx"]["peak"], "ctx_per_turn": d["ctx"]["slope"],
                          "compactions": d["ctx"]["compactions"], "cacheW_ratio": d["cacheW_ratio"]}}


def check(h, c, answer):
    t = c["type"]
    a = (answer or "").lower()
    def fcontent(path):
        p = ws_path(h, path)
        return open(p).read() if os.path.exists(p) else None
    if t in ("file_exists",):
        ok = os.path.exists(ws_path(h, c["path"])); return ok, f"{c['path']} exists", "" if ok else "missing"
    if t in ("file_equals", "file_contains", "file_matches", "file_not_contains"):
        body = fcontent(c["path"])
        if body is None: return False, f"{c['path']} {t}", "file missing"
        b = body.strip()
        if t == "file_equals": ok = b == c["value"].strip()
        elif t == "file_contains": ok = c["value"] in body
        elif t == "file_not_contains": ok = c["value"] not in body
        else: ok = re.search(c["regex"], body) is not None
        return ok, f"{c['path']} {t} {c.get('value', c.get('regex',''))!r}", "" if ok else f"got: {b[:80]!r}"
    if t == "answer_contains":
        ok = c["value"].lower() in a; return ok, f"answer contains {c['value']!r}", ""
    if t == "answer_not_contains":
        ok = c["value"].lower() not in a; return ok, f"answer omits {c['value']!r}", ""
    if t == "tool_used":
        return None, f"tool {c['name']} used", "checked by judge from tools list"
    if t == "tool_not_used":
        return None, f"tool {c['name']} not used", "checked by judge from tools list"
    if t in ("memory_contains", "memory_not_contains"):
        mem = read_memory(h).lower()
        present = c["value"].lower() in mem
        ok = present if t == "memory_contains" else not present
        return ok, f"memory {t} {c['value']!r}", "" if ok else "(memory store inspected)"
    return None, f"unknown check {t}", ""


# ---- main -------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--harness", required=True, choices=["cc", "hermes"])
    ap.add_argument("--scenarios", default="scenarios/scenarios.yaml")
    ap.add_argument("--only", default="", help="comma-separated scenario ids")
    ap.add_argument("--out", default="")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--stamp", default="manual", help="run id stamp (e.g. git sha) for provenance")
    args = ap.parse_args()

    spec = yaml.safe_load(open(os.path.join(ROOT, args.scenarios)))
    scen = spec["scenarios"]
    if args.only:
        keep = set(args.only.split(","))
        scen = [s for s in scen if s["id"] in keep]
    out_dir = os.path.join(ROOT, args.out or f"results/{args.harness}-run")
    os.makedirs(out_dir, exist_ok=True)

    results = []
    for s in scen:
        h = args.harness
        print(f"[{h}] {s['id']} {s['title']} ...", flush=True)
        reset(h, s.get("reset", []))
        setup(h, s.get("setup", []))
        steps_out = []
        for i, st in enumerate(s["steps"]):
            label = f"{h}_{s['id']}_{i}"
            steps_out.append(run_step(h, label, st["prompt"]))
        last = steps_out[-1]
        # aggregate metrics across steps
        mets = [x["metrics"] for x in steps_out if x["metrics"]]
        agg = None
        if mets:
            agg = {k: round(sum(m[k] for m in mets), 5) for k in ("in", "out", "cacheR", "cacheW", "total", "cost_usd")}
            agg["lat_s"] = round(sum((m["lat_s"] or 0) for m in mets), 1)
            agg["ctx_peak"] = max(m["ctx_peak"] for m in mets)
            agg["compactions"] = sum((m["compactions"] or 0) for m in mets)
        tools = sorted({t for x in steps_out for t in x["tools"]})
        checks = []
        for c in s.get("checks", []):
            ok, desc, detail = check(h, c, last["answer"])
            checks.append({"ok": ok, "desc": desc, "detail": detail})
        det_ok = [c for c in checks if c["ok"] is True]
        det_fail = [c for c in checks if c["ok"] is False]
        if args.no_judge:
            verdict = {"verdict": "PASS" if not det_fail and checks else ("FAIL" if det_fail else "N/A"),
                       "reason": "deterministic-only"}
        else:
            verdict = blind_judge(s["judge"], last["answer"], tools, checks)
        print(f"    -> {verdict['verdict']}  (checks: {len(det_ok)} ok / {len(det_fail)} fail)  {verdict['reason'][:90]}")
        results.append({"id": s["id"], "group": s["group"], "title": s["title"], "harness": h,
                        "answer": last["answer"], "tools": tools, "checks": checks,
                        "verdict": verdict["verdict"], "judge_reason": verdict["reason"], "metrics": agg})

    # write artifacts
    with open(os.path.join(out_dir, "results.json"), "w") as f:
        json.dump({"harness": args.harness, "stamp": args.stamp, "scenarios": results}, f, indent=2)
    cols = ["id", "group", "verdict", "in", "out", "cacheR", "cacheW", "total", "cost_usd",
            "lat_s", "ctx_peak", "compactions"]
    with open(os.path.join(out_dir, "metrics.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for r in results:
            row = {"id": r["id"], "group": r["group"], "verdict": r["verdict"]}
            row.update({k: (r["metrics"] or {}).get(k, "") for k in cols[3:]})
            w.writerow(row)

    n = len(results)
    from collections import Counter
    tally = Counter(r["verdict"] for r in results)
    print(f"\n[{args.harness}] {n} scenarios -> {dict(tally)}")
    print(f"wrote {out_dir}/results.json and metrics.csv")


if __name__ == "__main__":
    main()
