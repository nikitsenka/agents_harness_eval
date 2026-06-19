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

Memory scenarios are deliberately **implicit** — no "save / remember / note /
memory" trigger words. The agent must decide on its own what to persist and
recall it without being told where to look.

### S1 — Memory (implicit)
- **S1.1 Capture** — a durable fact is mentioned in passing → agent persists it unprompted.
- **S1.2 Recall** — after a restart, an indirect question is answered from the persisted fact.
- **S1.3 Update** — a casually-stated new value silently overwrites the old; later recall returns only the new value (no blend).
- **S1.4 Restraint** — transient chit-chat / one-off numbers are NOT persisted.

### S2 — Skill creation
- **S2.1 Recognize** — after repeating a procedure, propose turning it into a skill.
- **S2.2 Author** — produce a clear, well-scoped skill (right triggers, runnable steps, no over-scoping).
- **S2.3 Loads** — the new skill is discovered & fires in a fresh session (correct on-disk format/location).

### S3 — Skills & tools usage
- **S3.1 Select** — fire the right skill for a matching request; ignore near-misses.
- **S3.2 Tool+args** — pick the correct tool with valid args; result lands in the workspace.
- **S3.3 Chain+recovery** — sequence multiple tool calls; on a forced error, adapt instead of faking success.

### S4 — Subagent (multi-agent) creation
- **S4.1 Recognize** — propose a dedicated subagent for a recurring specialized role.
- **S4.2 Author** — write a valid subagent definition in the harness's expected location, scoped (tools + when to delegate).
- **S4.3 Loads** — the subagent is registered/available for delegation in a new session.

### S5 — Subagent usage
- **S5.1 Delegate** — hand a fitting task to the right subagent; don't mis-delegate unrelated work.
- **S5.2 Fan-out** — split an independent 3-part task across subagents and aggregate coherently.
- **S5.3 Isolation** — when one subagent fails, finish the rest and report the failure honestly.

Scoring: automated where possible (did-it-persist, skill/tool/subagent
selection correct, file changed, tokens/latency, success over N runs) +
blind LLM-as-judge for open-ended quality.

## Switching the model

The point is to keep the model identical across harnesses. To move both off
Bedrock Sonnet 4.6 onto another backend:

- **clean-cc:** repoint the `*` route in `clean-cc/litellm-config.yaml` at any
  model LiteLLM supports (add the needed creds to `.env`; set
  `DISABLE_PROMPT_CACHING=1` on the `cc` service if the backend lacks caching).
- **hermes:** set the model/provider in `hermes/hermes-home/config.yaml`, or
  front it with the same LiteLLM endpoint.

## Findings (Sonnet 4.6 baseline run)

- **Memory:** both proactively capture *and* show restraint. Claude Code failed
  **S1.3** — its split `MEMORY.md` index desynced from the detail file, so a
  recall returned the stale value; Hermes' flat `USER.md` updated atomically.
- **Skill creation (S2.3):** Claude Code authors skills in the wrong layout
  (flat `skills/<name>.md` instead of `skills/<name>/SKILL.md`) so its own
  loader ignores them; Hermes' skill tooling emits a loadable skill.
- **Subagents:** Claude Code has a strong first-class primitive
  (`.claude/agents/<name>.md` via the Task tool) but under-reaches for it;
  Hermes delegates readily via a dynamic `delegate_task` tool but is slower.

## Notes / known issues

- **Hermes AWS auth:** its `~/.aws` mount is read-only, so when the SSO token
  expires (~hourly) boto3 can't refresh it. This repo injects **static** creds
  via `.env` so boto3 skips the SSO cache entirely. Re-export when they expire.
- **clean-cc memory** lives in the container's `~/.claude` (not mounted), so it
  resets when the container is recreated — intentional for a clean baseline.
- Claude Code version is pinned in `clean-cc/Dockerfile`; bump as needed.
