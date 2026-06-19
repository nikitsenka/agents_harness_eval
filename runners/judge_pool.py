#!/usr/bin/env python3
"""Two-phase Opus-judge helper.

The agents under test run Sonnet, so the judge must be a *different, stronger*
model — Opus. judge.py's HTTP path calls the same Sonnet backend (a same-model
judge, only an assistive fallback). The canonical judge is Opus, run BLIND by the
Claude Code (Opus) session over an anonymized evidence pool:

  Phase 1  python3 runners/run-eval.py --harness cc     --no-judge   # execute + checks
           python3 runners/run-eval.py --harness hermes --no-judge
  Phase 2  python3 runners/judge_pool.py build results/cc-run results/hermes-run
           -> writes /tmp/judge_pool.json (anonymized: opaque ids, NO harness)
              and /tmp/judge_map.json (private id -> harness/scenario map)
           The Opus session then judges each pack in /tmp/judge_pool.json BLIND
           (e.g. fan out blind judge subagents) into /tmp/opus_verdicts.json:
              {"E000": {"verdict": "PASS", "reason": "..."}, ...}
  Phase 3  python3 runners/judge_pool.py merge /tmp/opus_verdicts.json <out.json>
           -> joins verdicts back to harness/scenario; prints agreement vs the
              recorded (Sonnet) verdict and the disagreement list.

Why blind + anonymized: strips harness identity so the judge can't favor a side,
and pooling both harnesses' packs under opaque ids keeps ordering uninformative.
"""
import json, random, sys, glob, yaml, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build(run_dirs):
    spec = {s["id"]: s for s in yaml.safe_load(open(os.path.join(ROOT, "scenarios/scenarios.yaml")))["scenarios"]}
    pool, mapping, n = {}, {}, 0
    for d in run_dirs:
        rj = json.load(open(os.path.join(ROOT, d, "results.json")))
        h = rj["harness"]
        for r in rj["scenarios"]:
            eid = f"E{n:03d}"; n += 1
            pool[eid] = {"rubric": spec[r["id"]]["judge"], "answer": (r["answer"] or "(no answer)")[:1200],
                         "tools": r["tools"],
                         "checks": [f"[{'ok' if c['ok'] else 'FAIL' if c['ok'] is False else 'n/a'}] {c['desc']}"
                                    for c in r["checks"]]}
            mapping[eid] = {"harness": h, "id": r["id"], "recorded_verdict": r["verdict"]}
    items = list(pool.items()); random.shuffle(items)
    json.dump(dict(items), open("/tmp/judge_pool.json", "w"), indent=1)
    json.dump(mapping, open("/tmp/judge_map.json", "w"), indent=1)
    print(f"built /tmp/judge_pool.json ({len(pool)} blind packs) + /tmp/judge_map.json")
    print("ids:", " ".join(pool))


def merge(verdicts_path, out_path):
    opus = {k: v["verdict"] if isinstance(v, dict) else v for k, v in json.load(open(verdicts_path)).items()}
    m = json.load(open("/tmp/judge_map.json"))
    out, dis = {}, []
    for eid, info in m.items():
        ov = opus.get(eid, "?")
        rec = info.get("recorded_verdict", info.get("sonnet_verdict", "?"))
        out[f"{info['harness']}_{info['id']}"] = {"recorded": rec, "opus": ov}
        if ov != rec:
            dis.append((info["harness"], info["id"], rec, ov))
    json.dump(out, open(out_path, "w"), indent=1, sort_keys=True)
    agree = len(m) - len(dis)
    print(f"agreement {agree}/{len(m)} ({round(100*agree/len(m))}%); disagreements:")
    for h, sid, rv, ov in sorted(dis):
        print(f"  {h:6} {sid:4} recorded={rv:8} opus={ov}")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "build":
        build(sys.argv[2:])
    elif len(sys.argv) == 4 and sys.argv[1] == "merge":
        merge(sys.argv[2], sys.argv[3])
    else:
        print(__doc__); sys.exit(2)
