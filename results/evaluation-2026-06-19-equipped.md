# Harness Evaluation (equipped, driver v2) — 2026-06-19

Full re-run through the new automated driver (`runners/run-eval.py`, stamp
`e404e9f`) over the executable spec
([scenarios/scenarios.yaml](../scenarios/scenarios.yaml), 21 scenarios S1–S7).
Same model both sides (Sonnet 4.6 / Bedrock us-east-1).

**What changed since the first run:**
- **clean-cc is now *equipped*** — seeded `CLAUDE.md` "soul", `.claude/skills/`
  (example `text-stats`), `.claude/agents/` (example `file-reviewer`), and
  `memory/`. So this compares two *scaffolded* harnesses, not vanilla-CC vs Hermes.
- **Scoring is now by a blind judge** ([judge.py](../runners/judge.py)) separate
  from the executor — it sees the goal + evidence + deterministic checks but not
  which harness produced the run.
- **Deterministic checks** (file/answer/memory assertions) run before the judge.
- **Cost is price-weighted** (`cost_usd`), correcting the raw-token comparison.

Raw data: [cc-equipped/results.json](cc-equipped/results.json) +
[metrics.csv](cc-equipped/metrics.csv),
[hermes-equipped/results.json](hermes-equipped/results.json) +
[metrics.csv](hermes-equipped/metrics.csv).

## Scoreboard

| | clean-cc (equipped) | Hermes |
|---|---|---|
| PASS | 16 | 13 |
| PARTIAL | 3 | 3 |
| FAIL | 2 | 3 |
| SKIP | 0 | 2 |
| Median cost / run | $0.043 | **$0.025** |
| Median latency / run | 8.4 s | 8.5 s |
| Suite cost (sum) | $1.15 | **$0.73** |

Two of each harness's FAILs are **measurement artifacts** (see below), not real
capability gaps — corrected, cc is ~18/21 and Hermes ~14/21 + 2 legitimate SKIP.

## Headline findings

1. **Equipping clean-cc closed its biggest gaps.** With the seeded `CLAUDE.md`
   conventions, CC now **authors a skill that actually loads and fires** (s23
   PASS — was PARTIAL/never-fired in the vanilla run) and **creates a valid,
   loadable subagent** (s42/s43 PASS, and s41 *recognize* now proposes a subagent
   instead of a hook). The vanilla run's skill-layout bug and S4.1 misfire are
   gone — scaffolding, not the model, fixed them. (Vanilla cc was 13 PASS / 6
   PARTIAL / 1 FAIL → equipped 16 PASS / 3 PARTIAL / 2 FAIL.)
2. **The price-weighted cost shrinks the gap to ~1.6×.** Raw tokens made cc look
   ~3× costlier; in real dollars it's **$0.043 vs $0.025 median** — because most
   of cc's tokens are cheap cache-reads. This is the honest A/B cost number and
   it only became visible after weighting.
3. **Hermes failed the long-horizon task (s71); cc passed.** CC produced all six
   `out_N` files honoring the early naming rule; Hermes' deterministic checks all
   failed (files not produced as specified). First real S7 signal — and the one
   place the new long-horizon scenario discriminated. (Context curve still cc-only;
   `ctx_peak` stayed ~32–36k, so even s71 didn't trigger compaction.)
4. **Subagents still differ in kind.** cc has file-based subagents (authored +
   loadable). Hermes remains dynamic-delegation-only → s42/s43 legitimately SKIP.
5. **Honesty held** across both on the blocked/missing cases (s53, s61, s63).

## Measurement artifacts the run exposed (fix before trusting these cells)

- **s11 FAILs on BOTH** — the prompt bundles a memory fact + "what is 12×8?".
  Both agents persisted the fact but their *final* message was the memory
  confirmation, so `answer_contains "96"` (checked on the last message) missed
  the math answer. This is a last-message-extraction + multi-intent-prompt
  artifact, not a capability gap. Fix: split the scenario, or scan all messages.
- **s22 FAILs on BOTH** — s21 ("recognize") proactively *created* the csv skill,
  so s22 ("author it") found it already present and no-op'd → judged FAIL.
  Cross-scenario contamination. Fix: make s21 propose-only, or `reset: [skills]`
  before s22.

Both are exactly the kind of issue the executable spec + blind judge are meant
to surface — and both are one-line spec fixes.

## clean-cc (equipped) — verdicts

| Scenario | Verdict | cost | note |
|---|---|---|---|
| s11 capture | FAIL* | $0.158 | persisted SLA; final msg lacked "96" (artifact) |
| s12 recall | PASS | $0.017 | recalled 24h from memory |
| s13 update | PASS | $0.072 | 8h only, no blend |
| s14 restraint | PASS | $0.017 | 62; nothing persisted |
| s15 freshness | PARTIAL | $0.017 | answered from training, didn't fetch live |
| s21 recognize | PASS | $0.103 | proposed csv-to-markdown skill |
| s22 author | FAIL* | $0.043 | skill already created in s21 (artifact) |
| s23 loads | PASS | $0.053 | **skill loaded & fired** (vanilla bug fixed) |
| s31 select | PASS | $0.017 | near-miss correctly ignored |
| s32 tool+args | PASS | $0.029 | notes.txt exact |
| s33 chain+recovery | PASS | $0.041 | created header then appended; honest |
| s41 recognize | PASS | $0.104 | proposed a scoped subagent (not a hook) |
| s42 author | PASS | $0.052 | valid `.claude/agents/sql-migration-reviewer.md` |
| s43 loads | PASS | $0.139 | subagent listed/available in new session |
| s51 delegate | PARTIAL | $0.032 | flagged risk but did not delegate to a specialist |
| s52 fan-out | PASS | $0.045 | a=3, c=437, b correct |
| s53 isolation | PASS | $0.031 | missing step honest |
| s61 end-to-end | PARTIAL | $0.064 | greet.py written, couldn't execute (no python) |
| s62 redirection | PASS | $0.029 | port 9090 + host, no 8080 |
| s63 honest blocked | PASS | $0.018 | reported package nonexistent |
| s71 long-horizon | PASS | $0.067 | all six out_N correct, naming rule honored |

## Hermes — verdicts

| Scenario | Verdict | cost | note |
|---|---|---|---|
| s11 capture | FAIL* | $0.059 | persisted SLA; final msg lacked "96" (artifact) |
| s12 recall | PASS | $0.052 | recalled 24h |
| s13 update | PASS | $0.072 | 8h only, no blend |
| s14 restraint | PASS | $0.006 | 62; nothing persisted |
| s15 freshness | PASS | $0.011 | used terminal to fetch live UTC |
| s21 recognize | PASS | $0.051 | proposed + saved a SKILL.md |
| s22 author | FAIL* | $0.066 | only viewed existing skill (s21 artifact) |
| s23 loads | PARTIAL | $0.027 | table produced; skill-load less certain |
| s31 select | PASS | $0.006 | near-miss ignored |
| s32 tool+args | PASS | $0.018 | notes.txt exact (no security block this run) |
| s33 chain+recovery | PASS | $0.025 | header then append; honest |
| s41 recognize | PARTIAL | $0.016 | proposed a skill, not a tool-limited subagent |
| s42 author | SKIP | $0.088 | no file-based subagent mechanism (dynamic delegation) |
| s43 loads | SKIP | $0.078 | dynamic delegation only; no named registry |
| s51 delegate | PARTIAL | $0.034 | flagged DROP as critical; delegation unclear |
| s52 fan-out | PASS | $0.015 | a=3, c=437, b correct |
| s53 isolation | PASS | $0.015 | missing step honest |
| s61 end-to-end | PASS | $0.029 | wrote greet.py and executed it → "hi" |
| s62 redirection | PASS | $0.019 | port 9090 + host, no 8080 |
| s63 honest blocked | PASS | $0.013 | reported package nonexistent |
| s71 long-horizon | FAIL | $0.023 | out_N / summary not produced as specified |

\* artifact — see the measurement-artifacts section.

## Method notes / limitations

- **Single run (pass@1)** — still no pass^k/variance. Judgment + the two
  artifacts make individual cells noisy; re-run N≥3 before treating as firm.
- **Judge is the same model as the agents** (only backend available), run blind
  with a rubric. Prefer a different/stronger judge model when one exists.
- **s71 doesn't yet stress context** — `ctx_peak` ~32–36k, no compaction. Scale
  it up (more files/turns) to make the context tier discriminate on cc too.
- **Hermes context curve = n/a** (`token_count` null) — half the context
  comparison remains blind.
