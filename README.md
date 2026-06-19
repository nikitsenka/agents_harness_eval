# agents_harness_eval

An A/B evaluation harness for comparing **agent frameworks** on the **same
underlying LLM**. Two harnesses, side by side:

| Harness | What it is | How it's driven |
|---|---|---|
| **clean-cc** | Vanilla **Claude Code** — no project memory, no MCP, no skills | `claude -p … --strict-mcp-config` in an empty workspace |
| **hermes** | **Hermes Agent** (Nous Research), containerized | `hermes -z …` |

## What this measures (and what it doesn't)

The LLM is **held constant**, so this is **not** a model-quality test. It
evaluates the **harness/scaffolding** — how well each framework makes the *same
model* behave: memory, skill creation, tool use, and subagent (multi-agent)
management. A better harness makes the model punch above its weight.

**Model parity.** Both baselines run **Claude Sonnet 4.6 on AWS Bedrock**
(clean-cc via a LiteLLM `*`→`bedrock/eu.anthropic.claude-sonnet-4-6` route;
Hermes via its native `bedrock` provider). To compare on a different model,
repoint both at the same backend — see [Switching the model](#switching-the-model).

**Fairness controls:** same model + params, same tool surface, a fresh/empty
workspace per run, and a clean session unless the scenario is about persistence.

## Layout

```
agents_harness_eval/
├── README.md
├── docs/
│   └── SCENARIOS.md       # full S1–S6 scenario catalogue (Gherkin)
├── clean-cc/              # vanilla Claude Code baseline
│   ├── Dockerfile         #   claude-code on node:20-slim, runs as non-root, idles
│   ├── docker-compose.yml #   cc + litellm (model router)
│   ├── litellm-config.yaml#   "*" -> Bedrock Sonnet 4.6  (repoint to swap model)
│   ├── .env.example
│   └── workspace/         #   empty clean workspace (mounted)
├── hermes/                # Hermes Agent baseline
│   ├── docker-compose.yml #   cli + gateway; static AWS creds (SSO-cache fix)
│   ├── .env.example
│   ├── hermes-home/       #   tracked clean config (SOUL.md, config.yaml, ...)
│   └── workspace/         #   empty clean workspace (mounted)
└── runners/
    ├── run-cc.sh          # run-cc.sh LABEL "prompt" [--continue]
    ├── run-hermes.sh      # run-hermes.sh LABEL "prompt"
    └── metrics.py         # answer + tools + tokens/latency (auto-detects format)
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
(`latency`, `in/out/cacheR/cacheW` tokens). Reset a harness between full runs:
clean-cc `docker compose down && up`; Hermes `: > hermes-home/memories/USER.md`
and remove any test skills under `hermes-home/skills/`.

## Scenarios

The full scenario catalogue (S1–S6, harness-neutral Gherkin) lives in
[docs/SCENARIOS.md](docs/SCENARIOS.md). At a glance:

| Group | Covers |
|---|---|
| **S1 — Memory (implicit)** | capture · recall · update · restraint · freshness/re-grounding |
| **S2 — Skill creation** | recognize · author · loads |
| **S3 — Skills & tools usage** | select · tool+args · chain+recovery |
| **S4 — Subagent creation** | recognize · author · loads |
| **S5 — Subagent usage** | delegate · fan-out · failure isolation |
| **S6 — Goal completion** | end-to-end · mid-task redirection · honest done/partial/blocked |

Memory scenarios are deliberately **implicit** — no "save / remember / note /
memory" trigger words; the agent decides on its own what to persist and recalls
it without being told where to look.

## Metrics

Each run is scored on two axes — **did it pass the scenario** (functional) and
**what did it cost** (non-functional). `runners/metrics.py` extracts the
quantitative figures from each harness's own telemetry.

**Functional — per scenario:**

| Metric | Applies to | How it's checked |
|---|---|---|
| Outcome | all | PASS / PARTIAL / FAIL against the scenario's `Then` clause |
| Persistence | S1.1–S1.3 | the durable fact landed in the memory store and survives a fresh session |
| Restraint | S1.4 | the ephemeral input was **not** written to memory |
| Recall correctness | S1.2–S1.3 | the answer matches the latest value, no stale/blended data |
| Freshness | S1.5 | volatile facts are re-checked against the live source; durable facts are not needlessly re-fetched |
| Artifact validity | S2.2, S4.2 | created skill/subagent is in the expected on-disk format and is discovered |
| Selection accuracy | S2.3, S3.1, S5.1 | right skill/tool/subagent fires; near-misses don't |
| Tool / agent trace | S3, S4, S5 | which tools and subagents were actually invoked (from the run log) |
| Honesty | S3.3, S5.3 | no success claimed without the action; failures reported, not faked |
| Open-ended quality | all | blind LLM-as-judge with a stronger model |

**Non-functional — per run, emitted by `metrics.py`:**

| Field | Meaning |
|---|---|
| `latency` | wall-clock time to the final answer |
| `in` / `out` | input / output tokens |
| `cacheR` / `cacheW` | prompt-cache read / write tokens (the per-turn system-prompt overhead shows up here) |
| `total` | sum of the above — proxy for cost |
| `tools` | number of tool calls in the run |

Repeat a scenario N times and aggregate for **success rate** and
**latency / token medians**.

## Switching the model

The point is to keep the model identical across harnesses. To move both off
Bedrock Sonnet 4.6 onto another backend:

- **clean-cc:** repoint the `*` route in `clean-cc/litellm-config.yaml` at any
  model LiteLLM supports (add the needed creds to `.env`; set
  `DISABLE_PROMPT_CACHING=1` on the `cc` service if the backend lacks caching).
- **hermes:** set the model/provider in `hermes/hermes-home/config.yaml`, or
  front it with the same LiteLLM endpoint.
