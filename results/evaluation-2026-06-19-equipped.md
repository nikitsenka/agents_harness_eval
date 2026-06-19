# Harness Evaluation (equipped, driver v2, post-fix) — 2026-06-19

Full run through the automated driver (`runners/run-eval.py`, stamp `0a32f35`)
over the executable spec ([scenarios/scenarios.yaml](../scenarios/scenarios.yaml),
21 scenarios S1–S7). Same model both sides (Sonnet 4.6 / Bedrock us-east-1).
clean-cc is **equipped** (seeded `CLAUDE.md`/skills/agents/memory); scoring is a
**blind judge** separate from the executor, informed by deterministic checks.

**Spec fixes applied since the prior run** (both were measurement artifacts):
- **s11** — dropped the brittle last-message `answer_contains "96"` check; the
  verdict now measures *unprompted memory persistence* only.
- **s22** — `reset: [skills]` before authoring, so s21's proactively-created
  skill no longer no-ops the author step. **Both harnesses now PASS s22.**

**Reset model changed:** state is reset to the seeded baseline **once before** the
run and **never after** — created skills/subagents/memory accumulate and are left
in place (see *Artifacts created* below).

Raw: [cc-equipped/results.json](cc-equipped/results.json) ·
[hermes-equipped/results.json](hermes-equipped/results.json) (+ `metrics.csv`).

## Scoreboard

| | clean-cc (equipped) | Hermes |
|---|---|---|
| PASS | 16 | 13 |
| PARTIAL | 3 | 4 |
| FAIL | 2 (s11, s12) | 2 (s62, s71) |
| SKIP | 0 | 2 (s42, s43) |
| Median cost / run | $0.035 | **$0.024** |
| Median latency / run | 7.0 s | 8.1 s |
| Suite cost (sum) | $0.91 | **$0.69** |

## Headline findings

1. **Equipped clean-cc authors loadable skills and subagents** — the vanilla
   skill-layout bug is gone: `csv-to-markdown/SKILL.md` is created in the correct
   `dir/SKILL.md` form (s22) **and fires** in a fresh session (s23 PASS), and a
   scoped `sql-migration-reviewer` subagent is authored + auto-registered
   (s42/s43 PASS). Scaffolding, not the model, fixed these.
2. **Unprompted memory capture is flaky on cc** — s11 FAILed this run (the agent
   answered the math but did **not** persist the SLA), which then **cascaded into
   s12** (recall had nothing to find). The prior run captured fine. Same model,
   same prompt → different behaviour: textbook motivation for pass^k / N-run
   scoring, and a caution that shared-memory scenarios chain failures.
3. **Hermes memory is rock-solid** — captured (s11), recalled (s12), updated
   atomically to 8h with no blend (s13), showed restraint (s14), and fetched live
   time for the volatile question (s15) — a clean S1 sweep.
4. **Hermes subagents remain dynamic-only** (s42/s43 SKIP — `delegate_task`, no
   file registry) and it **failed the long-horizon task** (s71) and the
   `config.json` write (s62 — security layer blocked the write and the automated
   driver has no terminal fallback, so it FAILs rather than PARTIALs).
5. **Cost gap ~1.5× in dollars** ($0.035 vs $0.024 median) — far less than the
   raw-token gap, because cc's tokens are mostly cheap cache-reads. Visible only
   after price-weighting.

## Independent Opus judge (blind re-judge)

The agents run Sonnet, so the Sonnet judge above is a *same-model* grader. As a
cross-check, every run was re-judged **blind by Opus** (anonymized evidence, no
harness identity), via `runners/judge_pool.py` (see
[judge-opus-vs-sonnet.json](judge-opus-vs-sonnet.json)).

- **Agreement: 39/42 (93%).**
- **All 3 disagreements are on subjective scenarios; none on deterministic ones:**

| Scenario | Sonnet judge | Opus judge | the call |
|---|---|---|---|
| cc s15 freshness | PARTIAL | FAIL | Opus stricter — answered from context, fetched nothing live |
| cc s51 delegate | PARTIAL | PASS | Opus credited the risk-flag as sufficient |
| hermes s23 loads | PARTIAL | PASS | Opus credited the skill having fired |

This is the thesis in miniature: a different/stronger judge moves **only** the
judgment cells (s15/s51/s23), and agrees everywhere a deterministic check anchors
the verdict — so the deterministic backbone is robust and the subjective verdicts
are the ones to treat as soft. Under the Opus judge the tallies shift to cc
**17 PASS / 1 PARTIAL / 3 FAIL** and hermes **14 PASS / 3 PARTIAL / 2 SKIP / 2 FAIL**.

## Artifacts the agents created (preserved for inspection)

State was **not** reset after the run; these are the real files each agent wrote.

**clean-cc** (`clean-cc/workspace/`)
- `memory/project_code_review_sla.md` — proper frontmatter + body: *"Code review
  SLA is 8 hours, effective 2026-06-19"* with **Why/How** (captured 24h then
  updated to 8h, no blend), and `memory/MEMORY.md` index updated to point at it.
- `.claude/skills/csv-to-markdown/SKILL.md` — correct `dir/SKILL.md` layout, YAML
  frontmatter with a precise trigger description, and 6 ordered runnable steps.
- `.claude/agents/sql-migration-reviewer.md` — frontmatter (`name`, `description`,
  `tools: Read, Glob, Grep`) + a detailed safety-review system prompt.

**Hermes** (`hermes/hermes-home/`)
- `memories/USER.md` — flat, atomic: *"Team's standard code-review SLA is 8 hours
  (updated June 2026)."*
- `skills/data/csv-to-markdown/SKILL.md` and `skills/data/sql-migration-review/SKILL.md`
  — both with frontmatter + a `triggers:` list (Hermes authored a **skill** for
  the SQL-review role rather than a subagent — consistent with its dynamic model).
- No file-based subagents (delegation is the runtime `delegate_task` tool).

## Per-scenario verdicts

| Scn | clean-cc | Hermes | notes |
|---|---|---|---|
| s11 capture | **FAIL** | PASS | cc didn't persist this run (flaky); hermes did |
| s12 recall | **FAIL** | PASS | cc cascade from s11; hermes recalled 24h |
| s13 update | PASS | PASS | both 8h, no blend |
| s14 restraint | PASS | PASS | 62, nothing persisted |
| s15 freshness | PARTIAL | PASS | cc answered from context; hermes ran `date` |
| s21 recognize | PASS | PARTIAL | both propose reuse; hermes leaned skill-ish |
| s22 author | PASS | PASS | **fixed** — both author a real skill now |
| s23 loads | PASS | PARTIAL | cc skill fired; hermes table ok, load less certain |
| s31 select | PASS | PASS | near-miss ignored |
| s32 tool+args | PASS | PASS | notes.txt exact |
| s33 chain+recovery | PASS | PASS | header then append; honest |
| s41 recognize | PASS | PARTIAL | cc proposed subagent; hermes proposed skill |
| s42 author | PASS | SKIP | cc file-based subagent; hermes dynamic-only |
| s43 loads | PASS | SKIP | cc registered; hermes no named registry |
| s51 delegate | PARTIAL | PARTIAL | both flagged DROP; delegation not clean |
| s52 fan-out | PASS | PASS | a=3, c=437, b correct |
| s53 isolation | PASS | PASS | missing step honest |
| s61 end-to-end | PARTIAL | PASS | cc no python to run; hermes ran greet.py |
| s62 redirection | PASS | **FAIL** | hermes security blocked the config.json write |
| s63 honest blocked | PASS | PASS | reported nonexistent package |
| s71 long-horizon | PASS | **FAIL** | cc produced all out_N; hermes did not |

## Limitations (unchanged)

- **Single run (pass@1)** — s11/s12 prove run-to-run variance is real; N≥3 + pass^k
  is the next step before treating cells as firm.
- **Judge:** the automated `judge.py` is same-model (Sonnet); the canonical
  verdicts are cross-checked by a **blind Opus** re-judge (93% agreement, above).
- **s71 still doesn't stress context** (`ctx_peak` ~32–36k, no compaction); scale it
  up to discriminate the context tier on cc.
- **Hermes context curve = n/a** (`token_count` null) and **s62/s71 FAILs are partly
  harness-policy** (security block / no driver fallback), not pure reasoning.
