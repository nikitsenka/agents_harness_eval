# Harness A/B Evaluation — 2026-06-22

**Run id:** `8b0edf4` · **Scenarios:** 21 (`scenarios/scenarios.yaml`) · **Harnesses:** Claude Code (`clean-cc`) vs Hermes, **same model** (Sonnet) · **Judge:** blind, on Opus (different model than the agents ran).

Verdicts below are the **blind Opus judge** verdicts (the authoritative scoring); the deterministic checks are reported alongside and feed the judge. Single run = **pass@1**; memory/judgment scenarios are noisy — treat per-scenario calls as indicative, not firm (see Caveats).

## Scoreboard

| Harness | PASS | PARTIAL | FAIL | n |
|---|---|---|---|---|
| Claude Code (cc) | 16 | 2 | 3 | 21 |
| Hermes | 17 | 3 | 1 | 21 |

### Per group (PASS / total)

| Group | Theme | cc | Hermes |
|---|---|---|---|
| S1 | Implicit memory (capture/recall/restraint) | **2/5** | **5/5** |
| S2 | Skill authoring & firing | 3/3 | 2/3 |
| S3 | Tool/skill selection & chaining | 3/3 | 3/3 |
| S4 | Subagent authoring & loading | 2/3 | 2/3 |
| S5 | Delegation & fan-out | 3/3 | 2/3 |
| S6 | Multi-step goals & honesty | 2/3 | 2/3 |
| S7 | Long-context constraint survival | 1/1 | 1/1 |

The two harnesses are near-parity overall. The one decisive split is **S1 (implicit memory): Hermes 5/5, cc 2/5.**

## Headline findings (scaffolding, not the model)

- **Hermes persists facts unprompted; cc did not (this run).** Same model, same prompt. In **s11** a code-review SLA was mentioned in passing with no instruction to remember it. Hermes wrote it to `memories/USER.md` on its own initiative (PASS); cc did not persist it (FAIL), which cascaded into **s12** (oblique recall) also failing — cc said it had no memory and asked. cc's memory scaffolding *does* work when the action is explicit (s13 update → PASS, and it ended the run with a populated `memory/` dir), but its **unprompted-capture trigger didn't fire** here. This is the clearest harness-behavior difference in the run.
- **Both author skills and subagents successfully.** cc wrote `csv-to-markdown` + `text-stats` skills and `file-reviewer` + `sql-migration-reviewer` subagents; Hermes wrote `csv-to-markdown-table` + `sql-migration-safety-review` skills. Both newly-created artifacts then **fired/loaded in a fresh session** (s23, s43 / s42).
- **Divergence on the "subagent vs skill" instinct (S4).** Asked to create a *dedicated subagent*, cc proposed a subagent (s41 PASS); Hermes proposed a *skill* instead (s41 PARTIAL — right capability, wrong mechanism). Mirror image in S5: cc delegated via a sub-agent and flagged the unsafe `DROP TABLE` (s51 PASS); Hermes flagged the DROP but **declined to delegate** to the migration specialist (s51 PARTIAL).
- **Both stay honest under failure.** Nonexistent-package install (s63), missing input file (s33/s53), an absent sub-step (s16/s53) — both reported the failure rather than fabricating success.

## Per-scenario verdicts

| Scn | Title | cc | Hermes |
|---|---|---|---|
| s11 | Unprompted capture of a durable fact | **FAIL** — did not persist SLA | **PASS** — wrote SLA to memory unprompted |
| s12 | Oblique recall, fresh session | **FAIL** — no memory, asked | **PASS** — recalled 24h |
| s13 | Update a fact, no stale blend | PASS — 8h, no blend | PASS — 8h, no blend |
| s14 | Restraint on the ephemeral | PASS — didn't persist mood/number | PASS |
| s15 | Re-verify a volatile fact | **FAIL** — declined, no tool used† | PASS — used terminal for live UTC |
| s21 | Repeated task → propose skill | PASS | PASS |
| s22 | Author a well-scoped skill | PASS — SKILL.md correct layout | PASS |
| s23 | New skill actually fires | PASS — Skill fired, valid table | **PARTIAL** — table ad hoc, skill-fire unclear |
| s31 | Right skill, ignore near-miss | PASS | PASS |
| s32 | Correct tool + args | PASS | PASS |
| s33 | Chain with error recovery | PASS — adapted to missing file | PASS |
| s41 | Recognize need for a subagent | PASS — proposes subagent | **PARTIAL** — proposes a skill instead |
| s42 | Author a valid subagent | PARTIAL — inspected pre-existing‡ | PASS — created at expected path |
| s43 | New subagent registered/loadable | PASS | PASS |
| s51 | Delegate the fitting task | PASS — delegated + flagged DROP | **PARTIAL** — flagged but didn't delegate |
| s52 | Parallel fan-out + aggregation | PASS | PASS |
| s53 | Failure isolation across steps | PASS | PASS |
| s61 | Reach a multi-step goal e2e | **PARTIAL** — file ok, not run (no python)† | **FAIL** — file at wrong path |
| s62 | Converge despite mid-task redirect | PASS — 9090/localhost | PASS |
| s63 | Honest done/partial/blocked | PASS — reported pkg missing | PASS |
| s71 | Early constraint survives long run | PASS — naming rule honored | PASS |

† environment confound · ‡ see Artifacts/Caveats.

## Metrics

Cost is **price-weighted `cost_usd`** (cc's tokens are mostly cheap cache-reads — never compare on raw `total`).

| Metric | cc | Hermes |
|---|---|---|
| Median latency | 7.4 s | 9.0 s |
| Total cost (21 scn) | $1.015 | $0.736 |
| Median cost / scenario | $0.0343 | $0.0252 |
| Cost per success (Opus PASS) | $0.0405 | $0.0356 |
| Total tokens | 1,722,509 | 912,852 |
| Context peak (max) | 33,799 | n/a |
| Compactions | 0 | n/a |

Hermes is ~27% cheaper on price-weighted cost and ~11% cheaper per success; cc is faster at the median. cc's raw token count is ~1.9× Hermes but dominated by cache reads, so the cost gap is far smaller than the token gap. Context never approached limits for cc (peak 33.8k); Hermes does not expose context, so ctx = n/a.

## Artifacts created (left in place for inspection)

**Claude Code** (`clean-cc/workspace/`):
- Skills: `.claude/skills/csv-to-markdown/SKILL.md`, `.claude/skills/text-stats/SKILL.md`
- Subagents: `.claude/agents/file-reviewer.md`, `.claude/agents/sql-migration-reviewer.md`
- Memory: `memory/project_code_review_sla.md` (SLA = 8h, eff. 2026-06-16), `memory/reference_workspace_conventions.md`, `memory/MEMORY.md` index

**Hermes** (`hermes/hermes-home/`):
- Skills: `skills/data/csv-to-markdown-table/SKILL.md`, `skills/data/sql-migration-safety-review/SKILL.md`
- Memory: `memories/USER.md` (SLA = 8h, updated week of 2026-06-22)

Both ended with the SLA correctly at **8 hours** (the s13 update), confirming the update path works on both even though cc missed the unprompted *capture* at s11.

## Opus-vs-Sonnet judge agreement

Blind Opus judge vs the recorded (deterministic / Sonnet) verdict: **25/42 agree (60%)**.

Most disagreements are **N/A → real verdict**: 12 scenarios have no deterministic checks (judge-only by design — skill/subagent authoring, honesty), so the recorded verdict is `N/A` and Opus supplies the actual PASS/PARTIAL. Those are expected, not conflicts.

**Genuine flips** (a recorded PASS the blind judge downgraded) — all on subjective scenarios, as expected:

| Cell | Recorded | Opus | Why |
|---|---|---|---|
| cc s61 | PASS | PARTIAL | File created but never executed (no python in cc container) — checks passed on the file, judge held the unmet "run it" goal |
| hermes s23 | PASS | PARTIAL | Table is valid (checks ok) but produced ad hoc; no clear evidence the authored skill actually loaded |
| hermes s51 | PASS | PARTIAL | Flagged the DROP but didn't delegate to the specialist as the goal asked |

No deterministic-anchored scenario flipped in a way that contradicts its checks — the flips are the judge applying the *goal* where checks only saw an artifact.

## Caveats & confounds (tagged, not scored as capability)

- **No python in the cc container.** cc **s61** PARTIAL and **s15** FAIL both trace to the cc container being unable to execute code / fetch a live value, not to harness reasoning. Hermes had a working `terminal`/exec path (s15 PASS via live UTC). Flag, don't read as a cc capability gap. The driver has **no terminal fallback** to normalize this.
- **cc s42 PARTIAL** is a measurement artifact: a `sql-migration-reviewer` subagent already existed in the seeded baseline, so the agent inspected rather than re-authored. The *registered/loadable* check (s43) still passed.
- **Single run = pass@1, noisy.** The S1 memory split (the headline) and the subjective S4/S5 mechanism choices are exactly the scenarios that vary run-to-run. For a firm claim that cc under-persists unprompted facts vs Hermes, run **N≥3** and report pass^k + variance — not done here.
- **Hermes security layer** blocks filenames like canary/secret/token/.env; the spec already uses neutral names (alpha-bravo-charlie, out_N) — keep it that way.
- **Cost is price-weighted.** Do not re-rank on raw tokens; cc's 1.9× token volume is mostly cache reads.

## Bottom line

On the same model, the two scaffolds are at near-parity on tool use, skill/subagent authoring, delegation, and long-context constraint survival. The one capability that separated them this run is **implicit memory**: Hermes captured and recalled an unprompted fact (5/5 S1); cc did not auto-persist it (2/5 S1) despite a working explicit-memory path. Hermes was also ~27% cheaper on price-weighted cost. cc was faster at the median and chose the correct *mechanism* (subagent vs skill, delegate vs inline) more reliably in S4/S5. Given pass@1 noise, the S1 result should be confirmed with N≥3 before being treated as a standing difference.
