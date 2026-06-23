# Hermes memory provider A/B — built-in vs Hindsight (2026-06-22, N=3)

Does swapping Hermes' built-in file memory for the **native Hindsight memory
provider** (`memory.provider=hindsight`) make the *same model* recall better on
hard, long-term-memory tasks — and at what cost?

- **Scope:** Hermes only. Group **HM** (`scenarios/memory-hard.yaml`) — temporal /
  historical recall after a chain of casual updates across separate sessions.
- **Hindsight:** isolated instance for Hermes (`hermes/docker-compose.yml`
  `--profile hindsight`), its own LiteLLM → Bedrock. Connected as the **native
  provider** (`local_external`), built-in memory OFF so Hindsight is the sole
  store. Verified: retain via `on_session_end`, recall via `auto_recall`, no MCP
  tools. (`--hindsight` in `run-eval.py` applies/reverts the whole config.)
- **Control:** `session_search` disabled on the eval Hermes in BOTH conditions —
  it greps prior transcripts (a crutch a real cold session wouldn't have) and
  masks memory quality. This makes it a true durable-memory test.
- **Judge:** blind, on Opus. Deterministic substring checks over-credited
  Hindsight (the right token appeared mid-timeline on wrong answers); verdicts
  here are Opus-corrected.

## Reliability (pass@1 over N=3)

| HM | capability | built-in | Hindsight |
|----|---|:--:|:--:|
| hm1 | value two changes before current | **0/3** | **3/3** |
| hm2 | the original/first value | **0/3** | 2/3 |
| hm3 | predecessor in a dated rotation | 3/3 | 3/3 |
| hm4 | metric two updates ago | **0/3** | 2/3 |
| hm5 | multi-hop join (control) | 3/3 | 3/3 |
| | **pass@1** | **40%** | **87%** |

**Built-in structurally cannot recall a superseded value.** On hm1/hm2/hm4 it
answers verbatim *"I only have the current value … no history recorded"* and
asks the user — **0/9** across the historical scenarios. Hindsight retains each
update as a dated fact and recovers them — **7/9** (hm1 rock-solid; hm2/hm4
flaky at 2/3 when its consolidation collapses the timeline). On **current-state**
recall (hm3/hm5) the two are equal. So the gain is **large on a capability
built-in lacks entirely, and zero where built-in already works.**

## Cost — the decisive finding

Two separate bills: the **agent's** tokens (in Hermes' telemetry) and
**Hindsight's internal LLM** (extraction / entity-resolution / consolidation /
multi-strategy recall — invisible to Hermes' telemetry, measured from its
`llm-requests/stats` with a verified-empty bank).

| per run (5 scenarios) | built-in | Hindsight (Sonnet internal) | Hindsight (Haiku internal) |
|---|--:|--:|--:|
| agent tokens | 718k | 667k | 667k |
| agent cost | $1.13 | $0.34 | $0.34 |
| Hindsight internal tokens | — | ~5.0M (uncached, ~1,500 calls) | ~5.5M (~1,540 calls) |
| Hindsight internal cost | — | ~$18.4 | ~$5–6 |
| **system total / run** | **~$1.13** | **~$18.7 (≈16×)** | **~$5.8 (≈5×)** |

- **Agent-side, Hindsight is ~3× cheaper** ($0.34 vs $1.13, stable across 3 runs):
  built-in churns the prompt cache (cache-write ratio 33%), Hindsight keeps it
  stable (3.7%). Real, but small in absolute terms.
- **System-wide, Hindsight is far more expensive.** The driver is **volume**:
  Hindsight fires **~300 internal LLM calls / ~1M tokens per scenario**
  (uncached). With Sonnet internal that's **~16× built-in**.
- **A cheap extraction model recovers most of it — proven, not assumed.**
  Pointing Hindsight's internal LLM at **Haiku 4.5** (agent still Sonnet): the 3
  historical discriminators **still PASS** (quality holds — the token *volume* is
  unchanged, only the price/token drops), cutting system cost to **~5× built-in**.
  Set `HINDSIGHT_LLM_MODEL=cheap-extractor` (a Haiku route in `litellm-config.yaml`).
- **Latency** rises ~37% either way (provider round-trips), plus two always-on
  containers (Hindsight + LiteLLM).

## Bottom line

- The eval now **discriminates**: built-in reliably fails historical/temporal
  recall (0/9); the Hindsight provider — properly connected, verified — recovers
  it (7/9), netting **87% vs 40% pass@1**.
- **But it is not free, and not "slightly more."** System-wide it is **~5×**
  (cheap extractor) **to ~16×** (Sonnet extractor) the cost of built-in, driven by
  Hindsight's ~1,500 uncached internal LLM calls/run — a cheap model lowers the
  price per token but not the call volume.
- **Decision rule:** worth it **only if the workload genuinely needs
  temporal/historical memory.** For current-state memory, built-in is equal and
  far cheaper. If you do adopt it, use the cheap-extractor config and expect ~5×
  cost + extra latency/ops.

## Reproduce

```bash
cd hermes && docker compose --profile hindsight up -d litellm hindsight
docker exec hermes-eval-gateway /opt/hermes/bin/hermes tools disable session_search
HM=hm1,hm2,hm3,hm4,hm5
python3 runners/run-eval.py --harness hermes --scenarios scenarios/memory-hard.yaml --only $HM            --no-judge --out results/hermes-builtin
python3 runners/run-eval.py --harness hermes --scenarios scenarios/memory-hard.yaml --only $HM --hindsight --no-judge --out results/hermes-hindsight
bash runners/measure_memory.sh   # N=3 reliability + agent + Hindsight-internal token capture
```
Cheap-extractor cost test: `HINDSIGHT_LLM_MODEL=cheap-extractor docker compose
--profile hindsight up -d hindsight`, then re-measure internal tokens.
