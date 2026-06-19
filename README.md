# agents_harness_eval

An A/B evaluation harness for comparing **agent frameworks** on the **same
underlying LLM**. Two harnesses, side by side:

| Harness | What it is | How it's driven |
|---|---|---|
| **clean-cc** | **Claude Code** equipped with the same scaffolding a real deployment has — a `CLAUDE.md` "soul", skills, subagents, and file-backed memory — but **no MCP servers** | `claude -p … --strict-mcp-config` in the seeded `workspace/` |
| **hermes** | **Hermes Agent** (Nous Research), containerized | `hermes -z …` |

clean-cc ships its scaffolding under `clean-cc/workspace/` (`CLAUDE.md`,
`.claude/skills/`, `.claude/agents/`, `memory/`) so the skill/subagent/memory
scenarios run against an equipped instance. MCP is deliberately left out
(`--strict-mcp-config`) to isolate harness behavior from MCP-tool overhead.

## What this measures (and what it doesn't)

The LLM is **held constant**, so this is **not** a model-quality test. It
evaluates the **harness/scaffolding** — how well each framework makes the *same
model* behave: memory, skill creation, tool use, and subagent (multi-agent)
management. A better harness makes the model punch above its weight.

**Model parity.** Both baselines run **Claude Sonnet 4.6 on AWS Bedrock**
(clean-cc via a LiteLLM `*`→`bedrock/eu.anthropic.claude-sonnet-4-6` route;
Hermes via its native `bedrock` provider). To compare on a different model,
repoint both at the same backend — see [Switching the model](#switching-the-model).

**Fairness controls:** same model + params, comparable scaffolding (both
harnesses carry skills, subagents, and memory), the workspace reset to its
seeded baseline per run, and a clean session unless the scenario is about
persistence.

## Layout

```
agents_harness_eval/
├── README.md
├── .claude/skills/        # skills for the orchestrating (Opus) session — NOT the harnesses
│   ├── agents-eval/       #   end-to-end eval playbook (conductor)
│   └── blind-judge/       #   per-pack judging rubric (run on Opus)
├── docs/
│   └── SCENARIOS.md       # full S1–S7 scenario catalogue (Gherkin)
├── clean-cc/              # Claude Code baseline (equipped scaffolding)
│   ├── Dockerfile         #   claude-code on node:20-slim, runs as non-root, idles
│   ├── docker-compose.yml #   cc + litellm (model router)
│   ├── litellm-config.yaml#   "*" -> Bedrock Sonnet 4.6  (repoint to swap model)
│   ├── .env.example
│   └── workspace/         #   seeded scaffolding (mounted):
│       ├── CLAUDE.md      #     the "soul" — memory/skill/subagent conventions
│       ├── .claude/settings.json   # autoMemoryDirectory -> /workspace/memory
│       ├── .claude/skills/         # example skill (text-stats) in dir/SKILL.md form
│       ├── .claude/agents/         # example subagent (file-reviewer)
│       └── memory/        #     MEMORY.md index + seed entry
├── hermes/                # Hermes Agent baseline
│   ├── docker-compose.yml #   cli + gateway; static AWS creds (SSO-cache fix)
│   ├── .env.example
│   ├── hermes-home/       #   tracked clean config (SOUL.md, config.yaml, ...)
│   └── workspace/         #   empty clean workspace (mounted)
├── scenarios/
│   └── scenarios.yaml     # executable spec: prompts + deterministic checks + judge rubrics
├── runners/
│   ├── run-cc.sh          # run-cc.sh LABEL "prompt" [--continue]
│   ├── run-hermes.sh      # run-hermes.sh LABEL "prompt"
│   ├── run-eval.py        # driver: spec -> run -> checks -> blind judge -> results/
│   ├── judge.py           # blind LLM judge (separate model call; harness-anonymous)
│   └── metrics.py         # answer + tools + tokens/latency/cost + context (auto-detects)
└── results/               # results.json + metrics.csv per run; dated reports
```

## Prerequisites

- Docker + Docker Compose.
- AWS Bedrock access to Claude Sonnet 4.6. Temp SSO creds work — refresh with
  `aws sso login` and export `AWS_ACCESS_KEY_ID/SECRET_ACCESS_KEY/SESSION_TOKEN`
  into the `.env` files. (They expire; re-export when calls start 403-ing.)
- `python3` on the host (for `metrics.py`).

## Quickstart

```bash
# --- clean Claude Code ---
cd clean-cc && cp .env.example .env   # fill AWS creds + a LITELLM_MASTER_KEY
docker compose up -d                  # builds cc, starts litellm
cd .. && ./runners/run-cc.sh smoke "Reply with exactly: PONG"

# --- Hermes ---
cd hermes && cp .env.example .env     # fill AWS creds
printf "HERMES_UID=$(id -u)\nHERMES_GID=$(id -g)\n" >> .env
docker compose up -d gateway          # warm process for metrics
cd .. && ./runners/run-hermes.sh smoke "Reply with exactly: PONG"
```

Each runner prints the answer, the tool calls, and a metrics line
(`latency`, `in/out/cacheR/cacheW` tokens). Reset a harness between full runs —
both now keep memory/skills on the host mount, so restore the seeded baseline
with git rather than recreating the container:

- **clean-cc:** `git checkout clean-cc/workspace && git clean -fd clean-cc/workspace`
  (restores `CLAUDE.md`/`.claude`/`memory`, removes run artifacts). Container
  memory also lives here via `autoMemoryDirectory`.
- **hermes:** `: > hermes-home/memories/USER.md` and remove any test skills
  under `hermes-home/skills/`.

## Scenarios

The full scenario catalogue (harness-neutral Gherkin) lives in
[docs/SCENARIOS.md](docs/SCENARIOS.md); the **executable** spec the driver runs
is [scenarios/scenarios.yaml](scenarios/scenarios.yaml). At a glance:

| Group | Covers |
|---|---|
| **S1 — Memory (implicit)** | capture · recall · update · restraint · freshness/re-grounding |
| **S2 — Skill creation** | recognize · author · loads |
| **S3 — Skills & tools usage** | select · tool+args · chain+recovery |
| **S4 — Subagent creation** | recognize · author · loads |
| **S5 — Subagent usage** | delegate · fan-out · failure isolation |
| **S6 — Goal completion** | end-to-end · mid-task redirection · honest done/partial/blocked |
| **S7 — Long-horizon context** | early-constraint retention · no silent work loss (stresses the context metrics) |

Memory scenarios are deliberately **implicit** — no "save / remember / note /
memory" trigger words; the agent decides on its own what to persist and recalls
it without being told where to look.

### Running the eval

The whole pipeline is captured as an **`agents-eval` skill** (`.claude/skills/agents-eval/`)
— a Claude Code (Opus) session can just be asked to "run the harness evaluation"
and it follows the playbook: execute → deterministic checks → blind Opus judging
→ synthesize the report. The skill is the *conductor*; it calls the Python tools
below for everything deterministic and applies the **`blind-judge`** skill for
the verdicts. To drive it by hand:

```bash
python3 runners/run-eval.py --harness cc      # or: --harness hermes
python3 runners/run-eval.py --harness cc --only s32,s71 --no-judge   # subset, skip judge
```

The driver ([`runners/run-eval.py`](runners/run-eval.py)) reads the YAML spec and,
per scenario: applies `reset`/`setup`, runs the prompt(s) via the harness runner,
evaluates **deterministic `checks`** (file/answer/memory assertions), and records
the open-ended verdict. It writes `results.json` + `metrics.csv` (incl.
price-weighted `cost_usd`) under `results/`. Both harnesses must be up first.

**The judge should be a *different, stronger* model than the agents.** The agents
run Sonnet, so `judge.py`'s HTTP path (also Sonnet) is only an automated
*fallback* — a same-model judge catches only errors the model already
understands. The canonical judge is **Opus, run blind** by the Claude Code (Opus)
session over an anonymized pool:

```bash
python3 runners/run-eval.py --harness cc     --no-judge   # phase 1: execute + checks
python3 runners/run-eval.py --harness hermes --no-judge
python3 runners/judge_pool.py build results/cc-run results/hermes-run   # phase 2: anonymize
#   -> Opus session judges /tmp/judge_pool.json BLIND -> /tmp/opus_verdicts.json
python3 runners/judge_pool.py merge /tmp/opus_verdicts.json results/judge.json  # phase 3: agreement
```

In the 2026-06-19 run, the Opus judge agreed with the Sonnet judge on **39/42
(93%)** — and **all 3 disagreements fell on subjective scenarios**, none on
deterministic ones (see `results/judge-opus-vs-sonnet.json`).

## Metrics

Measured in four tiers, following the **outcome → process → cost → reliability**
layering that agent-eval practice (τ-bench, DeepEval, and the like) converges on.
The headline rule from that work: **outcome-only scoring misses 20–40% of
failures** — a run can reach the right answer the wrong way — so process and
reliability are graded *alongside* the result, never folded into it.
`runners/metrics.py` emits the quantitative figures from each harness's own
telemetry; the rest is judged per the scenario's `Then` clause.

### 1. Outcome & behaviour — per scenario

| Metric | Applies to | How it's checked |
|---|---|---|
| Outcome | all | PASS / PARTIAL / FAIL against the scenario's `Then` clause |
| Persistence | S1.1–S1.3 | the durable fact landed in the memory store and survives a fresh session |
| Restraint | S1.4 | the ephemeral input was **not** written to memory |
| Recall correctness | S1.2–S1.3 | the answer matches the latest value, no stale/blended data |
| Freshness | S1.5 | volatile facts are re-checked against the live source; durable facts are not needlessly re-fetched |
| Artifact validity | S2.2, S4.2 | created skill/subagent is in the expected on-disk format and is discovered |
| Selection accuracy | S2.3, S3.1, S5.1 | right skill/tool/subagent fires; near-misses don't |
| Faithfulness | all (esp. S1.2, S3, S6) | every claim/value in the answer traces to a real tool output or file — no invented data (no hallucination) |
| Honesty & calibration | S3.3, S5.3, S6.3 | no success claimed without the action; a blocker is reported as blocked, not faked; abstains/asks when under-specified rather than guessing |
| Open-ended quality | all | rubric-scored by a **blind LLM judge on a different (stronger) model than the agent**, version-pinned, spot-checked against human labels before trusted |

### 2. Process / trajectory — per run

The path, not just the endpoint — this is the tier that catches the 20–40% of
failures an outcome score hides.

| Signal | What it catches |
|---|---|
| Tool & subagent trace | which tools/subagents actually fired (from the run log) — the basis for selection-accuracy and faithfulness |
| Tool-call efficiency | calls-per-task and redundant/repeated calls; a spike with a flat outcome = "agent looping", a regression invisible from the final answer |
| Recovery | on a forced tool error, did it adapt vs loop or give up (S3.3, S5.3) |
| Path adherence | multi-step/multi-agent runs keep the right order with no silently dropped step (S4, S5, S6) |

**Context efficiency / hygiene** — how fast the agent fills the window and
whether it actively keeps it clean. On a fixed model this is the clearest
harness differentiator (context management is the binding constraint). Derived
per-turn from token telemetry: Claude Code reports the actual input context per
turn, so the full curve is available. Hermes' session export currently leaves
per-message `token_count` empty, so its fill-curve reads `n/a` and only the
session-level `cacheW_ratio` hygiene proxy applies — compare **trends and
peaks** where both sides report, not byte-exact totals.

| Signal | What it measures |
|---|---|
| Context growth / turn | input-context tokens added per turn (the fill slope) |
| Peak context & headroom | max context reached, as % of the model window — how close to saturation |
| Tokens per progress | context tokens ÷ tool calls (or completed steps) — useful work per token |
| Compaction events | did the harness summarize/prune (CC auto-compact / Hermes compressor), and how much it reclaimed |
| Cache-write ratio | `cacheW / (cacheR + cacheW)` from the cost telemetry — high = churny, unstable context |
| Redundancy | repeated identical reads / tool outputs left in context (the context-rot signature) |

### 3. Cost — per run, emitted by `metrics.py`

| Field | Meaning |
|---|---|
| `latency` | wall-clock time to the final answer |
| `in` / `out` | input / output tokens |
| `cacheR` / `cacheW` | prompt-cache read / write tokens (the per-turn system-prompt overhead shows up here) |
| `total` | sum of the above — raw token proxy (overstates $: cache reads are ~10% of input price) |
| `cost` (`cost_usd`) | **price-weighted** $ cost — token classes priced separately (Bedrock Sonnet rates in `metrics.py`). The honest cost number; use this, not `total`. |
| `tools` | number of tool calls in the run |
| **cost / success** | `cost` ÷ passed runs — the efficiency number that matters. Cheap-but-wrong is not cheaper; compare harnesses on this. |

### 4. Reliability — over N runs

A single green run is not a pass — agent runs are nondeterministic. Repeat each
scenario **N times** and report:

- **success rate** — pass@1 fraction over N (the average).
- **pass^k** — fraction where **all k** runs pass; the reliability number. A harness at 0.9 success but 0.5 pass³ is flaky.
- **variance** — stddev across runs. On a small set the noise floor is ~3–5pp, so a smaller delta is drift, not signal.
- **crash rate vs fail rate** — separate harness errors (no final response, tool timeout, malformed output) from wrong answers. Different fixes — and an A/B between harnesses lives or dies here.

**How to read them**
- **Slice, never average across groups.** Report S1…S6 separately; one blended number hides a category that's catastrophically broken.
- **Compare against a baseline.** A harness/model/config change is "better" only if quality metrics improve with **no** regression in crash rate or cost/success. Cost is a guardrail, not a tiebreaker.

## Switching the model

The point is to keep the model identical across harnesses. To move both off
Bedrock Sonnet 4.6 onto another backend:

- **clean-cc:** repoint the `*` route in `clean-cc/litellm-config.yaml` at any
  model LiteLLM supports (add the needed creds to `.env`; set
  `DISABLE_PROMPT_CACHING=1` on the `cc` service if the backend lacks caching).
- **hermes:** set the model/provider in `hermes/hermes-home/config.yaml`, or
  front it with the same LiteLLM endpoint.
