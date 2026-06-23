---
name: agents-eval
description: Run the full A/B harness evaluation for this repo — Claude Code (clean-cc) vs Hermes on the SAME model — over scenarios/scenarios.yaml; executes scenarios, applies deterministic checks, judges the evidence blind on Opus, and synthesizes a results report. Trigger when asked to "run the eval", "run the harness evaluation", "re-run the scenarios", "compare the harnesses", or produce a new results report. Not for editing scenarios or one-off single-scenario runs.
---

# Run the agents harness evaluation

End-to-end playbook for a full A/B run. **You are the conductor, not the
calculator:** call the Python tools for everything deterministic (running
scenarios, checks, parsing telemetry, anonymizing, merging) and only do the
reasoning yourself (blind judging, interpreting confounds, writing the report).
Never re-implement parsing or checks in prose.

## Layers
- `runners/run-eval.py` — execute scenarios + deterministic `checks` (Python).
- `runners/judge_pool.py` — `build` (anonymize/pool) + `merge` (join verdicts, agreement) (Python).
- `runners/metrics.py` — telemetry → tokens / price-weighted `cost_usd` / context (Python).
- **`blind-judge` skill** — the per-pack rubric you apply during the judge phase.
- This skill — orchestration + synthesis.

## Prerequisites
- Both harnesses up: `docker compose -f clean-cc/docker-compose.yml ps` and
  `... hermes/docker-compose.yml ps` (litellm healthy; hermes gateway up). If
  down, `docker compose up -d` per the README. Fresh AWS creds in the `.env`s.
- Pick a run id (use the short git sha as `--stamp`) and an output dir per
  harness, e.g. `results/cc-equipped` / `results/hermes-equipped`.

## Steps

1. **Reset to the seeded baseline — BEFORE only, never after.** The driver does
   this once at the start of each `run-eval.py` invocation (cc → git-restore
   `clean-cc/workspace`; hermes → clear `hermes-home/memories/USER.md`). Do not
   reset after the run — leave created skills/subagents/memory in place for
   inspection.

2. **Execute + deterministic checks** (no LLM judge yet):
   ```bash
   python3 runners/run-eval.py --harness cc     --no-judge --stamp <sha> --out results/cc-equipped
   python3 runners/run-eval.py --harness hermes --no-judge --stamp <sha> --out results/hermes-equipped
   ```
   Each writes `results.json` (+ `metrics.csv`) with answer, tools, checks, and a
   `PENDING` verdict.

### Hermes memory provider A/B (built-in vs Hindsight) — `--hindsight`

A focused long-term-memory comparison for **Hermes only**, using the native
Hindsight memory provider (`memory.provider=hindsight`) instead of built-in
file memory. Spec: `scenarios/memory-hard.yaml` (group HM — temporal/historical
recall after a chain of updates, where flat memory keeps only current state).

- **Prereq:** isolated Hindsight up — `cd hermes && docker compose --profile
  hindsight up -d litellm hindsight` (own LiteLLM → Bedrock parity; API on host
  `:8889`, in-network `hindsight:8888`).
- **Control:** `session_search` is disabled on the eval Hermes
  (`hermes tools disable session_search`) so the test isolates the durable
  store, not transcript grep — a real cold session wouldn't have transcripts.
  Apply to BOTH conditions.
- `--hindsight` flips the eval Hermes config: `memory.provider=hindsight`,
  built-in `memory_enabled`/`user_profile_enabled` off, bank reset/inspection via
  the Hindsight REST API; baseline restores built-in. Self-correcting + restarts
  the gateway. Retain fires on session end; recall via `auto_recall`. Provider
  config: `hermes/hermes-home/hindsight/config.json` (`recall_types:
  observation,world,experience` is needed to surface per-update history).
```bash
HM=hm1,hm2,hm3,hm4,hm5
python3 runners/run-eval.py --harness hermes --scenarios scenarios/memory-hard.yaml --only $HM            --no-judge --stamp <sha> --out results/hermes-builtin
python3 runners/run-eval.py --harness hermes --scenarios scenarios/memory-hard.yaml --only $HM --hindsight --no-judge --stamp <sha> --out results/hermes-hindsight
```
Judge + report as below (pool the two `results.json`). Note in the report:
Hindsight's history advantage is **real but consolidation-dependent** (it can
collapse updates into a current-only observation), so run N≥3 for firm claims.

3. **Build the blind pool** (anonymized, harness-stripped, shuffled):
   ```bash
   python3 runners/judge_pool.py build results/cc-equipped results/hermes-equipped
   ```
   → `/tmp/judge_pool.json` (packs) + `/tmp/judge_map.json` (private map; do not
   read it while judging).

4. **Judge blind on Opus.** This runs on your session model (Opus) — that is the
   point (the agents ran Sonnet; the judge must differ). Read the pack ids from
   `/tmp/judge_pool.json`, split them into ~6 batches, and **fan out blind-judge
   subagents** (one per batch, in a single message so they run concurrently).
   Give each subagent its batch of ids and the `blind-judge` skill's rules; each
   returns `{id: {verdict, reason}}`. Collect all into `/tmp/opus_verdicts.json`.
   (Headless fallback only, no Opus session: `runners/judge.py` calls the
   same-model Sonnet endpoint — lower trust; note it in the report.)

5. **Merge + agreement:**
   ```bash
   python3 runners/judge_pool.py merge /tmp/opus_verdicts.json results/judge-opus-vs-sonnet.json
   ```
   Records the verdict per harness/scenario and prints agreement vs the recorded
   (deterministic/Sonnet) verdict. Expect disagreements to cluster on the
   **subjective** scenarios; if a deterministic-anchored scenario flips, re-check.

6. **Synthesize the report** at `results/evaluation-<date>.md`. Read both
   `results.json` + the merged judge file + `metrics.csv`. Include:
   - **Scoreboard** per harness (PASS/PARTIAL/FAIL/SKIP) and **per group** (S1–S7).
   - **Headline findings** — what the *scaffolding* (not the model) did differently.
   - **Per-scenario verdict table** with one-line evidence.
   - **Metrics** — median latency, **price-weighted `cost_usd`** (not raw tokens),
     tokens/cost-per-success, context (cc only; hermes ctx = n/a).
   - **Artifacts created** — the skills/subagents/memory each agent wrote (paths).
   - **Opus-vs-Sonnet judge** agreement + the disagreement cells.
   - **Caveats** (see below).

7. **Leave state in place** for inspection; commit only `results/` + framework
   changes, never the dirty `clean-cc/workspace` / `hermes-home` run artifacts.

## Judgment guidance (the reasoning this skill owns)
- **Slice, never average across groups.** Report S1–S7 separately; a blended
  number hides a catastrophically broken category.
- **Tag confounds, don't fold them in.** "No python in the cc container",
  "Hermes security blocked the write", "no terminal fallback in the driver" are
  *environment/policy*, not harness reasoning — flag them, don't score them as
  capability.
- **Single run = pass@1; it's noisy.** Memory capture and judgment scenarios vary
  run-to-run. For firm claims, run N≥3 and report pass^k + variance (note when
  you did not).
- **Cost is price-weighted.** cc's tokens are mostly cheap cache-reads; compare
  on `cost_usd`, never raw `total`.
- **Neutral filenames only.** Hermes' security layer blocks names like
  canary/secret/credential/token/key/.env — the spec already avoids them; keep it so.

## Pointers
- Scenarios: `scenarios/scenarios.yaml` (executable) · `docs/SCENARIOS.md` (Gherkin).
- Prior runs + method notes: `results/`.
