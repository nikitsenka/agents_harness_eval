# The story: can a memory provider make Hermes remember better — and is it worth it?

## The question
We wanted to know whether bolting **Hindsight** (an external agent-memory system) onto Hermes as its **native memory provider** actually improves long-term memory over Hermes' built-in file memory — and what it costs. Not a model test (everything stays on Bedrock Sonnet 4.6), a *memory-system* test.

## What we built
We stood up an **isolated Hindsight instance for Hermes** — its own container plus a dedicated LiteLLM so even Hindsight's internal extraction LLM runs on the same Bedrock model (parity), with local embeddings and zero new API keys. We wired it in the *proper* way — as Hermes' native `memory.provider=hindsight` (not a bolt-on MCP toolset) — and taught the eval driver a `--hindsight` flag that flips the whole config, resets/inspects the Hindsight bank over its REST API, and reverts cleanly.

## First surprise: Hermes was already too good
Our initial "hard" memory scenarios all **passed on built-in** — Hindsight changed nothing. Digging in, the reason was `session_search`: Hermes was just grepping its old session transcripts, so "memory" was never the bottleneck. That's a crutch a real cold session (days later, transcripts rotated out) wouldn't have. So we **disabled `session_search` in both conditions** to make it an honest test of the *durable store*, and rebuilt the scenarios around the one thing flat memory genuinely can't do.

## The discriminator we found
**Temporal/historical recall.** Built-in memory consolidates to the *current* state and throws history away. So we ask for *superseded* values — "what was the rate limit before the last three changes?", "what was the original price?", "the value two updates ago?" Built-in answers, verbatim: *"I only have the current value… no history recorded"* and asks the user for it. **0/9** across the historical scenarios. Hindsight retains each update as a dated fact and recovers them — **7/9**.

## Making the provider actually work
Getting the native provider to persist under the eval's one-shot runner took real debugging: retain fires on `on_session_end` (not per turn), built-in memory was shadowing it, and recall defaulted to consolidated-only facts. The fixes — clear built-in, `recall_types: observation,world,experience`, flush-on-session-end — got us a verified round-trip: retain → fresh-session recall straight from the bank, **0 MCP calls**, purely the native provider.

## The cost twist
Agent-side, Hindsight looked *cheaper* (~3×) — it keeps the prompt cache stable while built-in churns it. We almost concluded "break-even." Then we measured Hindsight's **internal** LLM spend (invisible to Hermes' telemetry) with a verified-empty bank: **~1M tokens and ~300 LLM calls per scenario** — ~5M tokens / ~1,500 uncached calls per run. That's the real bill. System-wide, Hindsight is **~16× built-in** with Sonnet doing its internal grunt-work.

## Then we tested the obvious objection
"You'd never run the extraction model on Sonnet in production." Correct — so we pointed Hindsight's internal LLM at **Haiku 4.5** and re-measured. **Quality held** (all three historical discriminators still pass — the work is mechanical, the token *volume* is identical), and cost dropped to **~5× built-in**. A cheap model lowers price-per-token but can't reduce the call volume, which is the real driver.

## Key findings

| | built-in | Hindsight |
|---|:--:|:--:|
| **pass@1 (N=3)** | 40% | **87%** |
| historical recall (hm1/hm2/hm4) | **0/9** | 7/9 |
| current-state recall (hm3/hm5) | 3/3 | 3/3 |
| **system cost / run** | **~$1.13** | ~$5.8 (Haiku) → ~$18.7 (Sonnet) |

- Built-in **structurally cannot** recall superseded values; Hindsight can. Where built-in already works (current state), they tie.
- Hindsight's edge is **real but consolidation-dependent** (hm2/hm4 flaky at 2/3 when it collapses the timeline).
- The cost is **volume-driven** (~1,500 internal calls/run); a cheap extractor cuts it from ~16× to ~5×, not to parity.
- **Verdict:** worth it **only if you need temporal/historical memory.** For current-state memory it's equal capability at 5–16× the cost, plus +37% latency and two extra services.

## What's in the PR
- `scenarios/memory-hard.yaml` — the HM group (temporal-recall discriminators + control)
- `runners/run-eval.py` — `--hindsight` provider mode (config flip, bank reset/inspection)
- `hermes/docker-compose.yml` + `hermes/litellm-config.yaml` — isolated Hindsight + LiteLLM (`--profile hindsight`), incl. the Haiku `cheap-extractor` route
- `runners/measure_memory.sh` — N=3 reliability + agent + Hindsight-internal token capture
- `results/` — both runs + the full evaluation report (`evaluation-2026-06-22-hermes-memory-provider.md`)

`config.yaml` stays pristine (built-in baseline); `--hindsight` applies every toggle at runtime.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
