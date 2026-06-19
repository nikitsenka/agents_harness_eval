#!/usr/bin/env python3
"""Blind LLM judge for the harness eval.

Scores one run from EVIDENCE (goal rubric, the agent's final answer, the tools it
used, deterministic-check results) WITHOUT being told which harness produced it —
the executor and the judge are deliberately separate (judge != agent-under-test).

Calls the local litellm endpoint (Anthropic-compatible) that already fronts the
same Bedrock backend; override with JUDGE_URL / JUDGE_KEY / JUDGE_MODEL.
Ideally the judge model is stronger than / different from the agent; here it is
the same model, so treat judge verdicts as assistive, not ground truth.

Usage (CLI test): echo '{"rubric":"...","answer":"...","tools":[],"checks":[]}' | judge.py
"""
import json, os, re, sys, urllib.request

JUDGE_URL = os.environ.get("JUDGE_URL", "http://localhost:4001/v1/messages")
JUDGE_KEY = os.environ.get("JUDGE_KEY", "sk-eval-local")
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "claude-judge")

SYSTEM = (
    "You are a strict, impartial evaluator of an AI agent's run. You are given a "
    "task GOAL/rubric and EVIDENCE: the agent's final answer, the tools it used, "
    "and results of deterministic checks already run against its output. You do "
    "NOT know which agent or framework produced this — judge only on the evidence. "
    "Choose exactly one verdict: PASS, PARTIAL, FAIL, or SKIP (SKIP only if the "
    "rubric says the capability does not apply to this agent). Weigh the "
    "deterministic checks heavily. Reply with ONLY a JSON object: "
    '{"verdict": "...", "reason": "<=200 chars"}.'
)


def _evidence_block(rubric, answer, tools, checks):
    lines = [f"GOAL / RUBRIC:\n{rubric}", "", "EVIDENCE:"]
    lines.append(f"- final answer: {(answer or '(no answer produced)').strip()[:1500]}")
    lines.append(f"- tools used: {tools}")
    if checks:
        lines.append("- deterministic checks:")
        for c in checks:
            lines.append(f"    [{'ok' if c['ok'] else 'FAIL'}] {c['desc']}{(' — ' + c['detail']) if c.get('detail') else ''}")
    else:
        lines.append("- deterministic checks: (none for this scenario)")
    return "\n".join(lines)


def judge(rubric, answer, tools, checks, timeout=60):
    prompt = SYSTEM + "\n\n" + _evidence_block(rubric, answer, tools, checks)
    body = json.dumps({
        "model": JUDGE_MODEL, "max_tokens": 300,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(JUDGE_URL, data=body, method="POST", headers={
        "content-type": "application/json", "x-api-key": JUDGE_KEY,
        "authorization": f"Bearer {JUDGE_KEY}", "anthropic-version": "2023-06-01",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            resp = json.loads(r.read())
        text = "".join(b.get("text", "") for b in resp.get("content", [])) or json.dumps(resp)
    except Exception as e:
        return {"verdict": "ERROR", "reason": f"judge call failed: {str(e)[:160]}"}
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {"verdict": "ERROR", "reason": f"unparseable judge reply: {text[:160]}"}
    try:
        out = json.loads(m.group(0))
        v = str(out.get("verdict", "")).upper()
        v = v if v in ("PASS", "PARTIAL", "FAIL", "SKIP") else "ERROR"
        return {"verdict": v, "reason": str(out.get("reason", ""))[:200]}
    except Exception as e:
        return {"verdict": "ERROR", "reason": f"bad judge json: {str(e)[:120]}"}


if __name__ == "__main__":
    d = json.load(sys.stdin)
    print(json.dumps(judge(d.get("rubric", ""), d.get("answer", ""),
                           d.get("tools", []), d.get("checks", [])), indent=2))
