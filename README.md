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

**S1.1 — Unprompted capture of a durable fact**
```gherkin
Given the user mentions a durable project fact in passing, with NO instruction to remember it (no "save", "remember", "note", "memory")
When the agent replies to the immediate message
Then the agent judges the fact durable and persists it to long-term memory on its own initiative
```
**S1.2 — Oblique recall in a later session after restart**
```gherkin
Given a durable fact was captured earlier and the container/process has since restarted
When the user asks a question that depends on that fact, phrased indirectly and WITHOUT referencing memory or the earlier chat
Then the agent answers correctly from the persisted fact, without being told where to look
```
**S1.3 — Silent update on a casual contradiction**
```gherkin
Given a fact is already in long-term memory
When the user casually states a new value in passing, without asking for an update
Then the agent revises the stored fact, and a later oblique recall returns ONLY the new value with no blend of old and new
```
**S1.4 — Restraint: do not persist the ephemeral**
```gherkin
Given the user shares transient one-off context (a mood, a throwaway number for a quick calc, small talk)
When the agent handles the message
Then the agent does NOT write it to long-term memory, reserving persistence for durable facts (no memory spam)
```

### S2 — Skill creation

**S2.1 — Recognize that a repeated task warrants a new skill**
```gherkin
Given the user has asked the agent to perform the same multi-step procedure several times
When the agent completes the procedure again
Then the agent proposes creating a reusable skill for it
And explains what the skill would encapsulate and when it should trigger
```
**S2.2 — Author a correct, well-scoped skill**
```gherkin
Given the user asks the agent to create a skill for a described procedure
When the agent generates the skill
Then the skill has a clear name and a description that triggers on the right requests
And the skill body contains correct, runnable, well-ordered steps
And no over-scoping (it does not claim unrelated requests)
```
**S2.3 — A newly created skill actually works**
```gherkin
Given a skill the agent just created
When the user issues a request that should trigger it
Then the agent invokes the new skill without a restart or code change (correct on-disk format/location, discovered by the loader)
And the procedure completes end-to-end
```

### S3 — Skills & tools usage

**S3.1 — Select the right existing skill, ignore near-misses**
```gherkin
Given a skill exists that matches a class of request
When the user makes a request in that class
Then the agent invokes that skill instead of improvising
And when the user makes a near-miss request outside the skill's scope
Then the agent does not fire the skill
```
**S3.2 — Choose the correct tool with correct arguments**
```gherkin
Given multiple tools are available
When the user asks for an action that one specific tool serves
Then the agent calls that tool with valid arguments
And the result lands correctly in the shared workspace
```
**S3.3 — Sequence a multi-step tool chain and recover from errors**
```gherkin
Given a task that requires several tool calls in order
When one tool call is forced to return an error
Then the agent retries or adapts its approach
And does not report success it did not actually achieve
```

### S4 — Subagent (multi-agent) creation

**S4.1 — Recognize the need for a specialized subagent**
```gherkin
Given the user describes a recurring specialized role (e.g. "a reviewer that only checks SQL migrations for safety")
When discussing how to set it up
Then the agent proposes a dedicated subagent and explains its scope and which tools it should be limited to
```
**S4.2 — Author a valid subagent definition**
```gherkin
Given the user asks the agent to create that subagent
When the agent generates it
Then it writes a correctly-formatted agent definition in the harness's expected location (e.g. .claude/agents/<name>.md with name, description, tool scope)
And the description clearly scopes when work should be delegated to it
```
**S4.3 — The new subagent is registered and loadable**
```gherkin
Given a subagent the agent just created
When a new session starts
Then the harness lists/recognizes the subagent as available for delegation (correct format/location, no manual fix needed)
```

### S5 — Subagent usage

**S5.1 — Delegate a fitting task to the right subagent, not the wrong one**
```gherkin
Given a specialized subagent exists
When the user gives a task matching that subagent's scope
Then the agent delegates to that subagent rather than doing it inline
And when given an unrelated task, it does NOT mis-delegate to that subagent
```
**S5.2 — Parallel fan-out and coherent aggregation**
```gherkin
Given a task with 3 independent parts that map to subagent work
When the agent processes the task
Then it dispatches subagents that run in parallel
And aggregates their results into one coherent answer
```
**S5.3 — Failure isolation across subagents**
```gherkin
Given a multi-subagent task where one subagent is forced to fail
When the agent aggregates the results
Then it completes the recoverable parts and reports the failure honestly
And does not claim success for the failed part
```

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
