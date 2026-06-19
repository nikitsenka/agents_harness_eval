# Evaluation Scenarios

The scenarios the harness eval runs against each framework (Claude Code vs
Hermes), written **harness-neutral** in Gherkin so the same scenario can run on
either side. Setup, model parity, and scoring live in [../README.md](../README.md);
the per-scenario metrics table is under its **Metrics** section.

Memory scenarios are deliberately **implicit** — no "save / remember / note /
memory" trigger words. The agent must decide on its own what to persist and
recall it without being told where to look.

## S1 — Memory (implicit)

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
**S1.5 — Re-verify a volatile fact instead of trusting memory**
```gherkin
Given a fact in long-term memory that is the kind that goes stale (a price, status, schedule, count, live config value)
When the user asks a question that depends on its CURRENT value
Then the agent re-checks the live source (tool/file/web) rather than answering from the stored value
And it updates/reconciles memory if the live value has changed
But for a durable fact (a name, birthday, fixed path) it answers from memory without a needless re-check
```

## S2 — Skill creation

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

## S3 — Skills & tools usage

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

## S4 — Subagent (multi-agent) creation

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

## S5 — Subagent usage

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

## S6 — Goal completion

Scenarios S1–S5 probe individual capabilities; S6 scores the **whole task** — did the agent reach the user's actual goal, regardless of the path it took.

**S6.1 — Reach a multi-step goal end-to-end**
```gherkin
Given a request whose goal requires several dependent steps to satisfy
When the agent works the task to completion
Then the user's stated goal is actually achieved (the final artifact/state exists), not just the intermediate steps acknowledged
```
**S6.2 — Converge on the goal despite a mid-task redirection**
```gherkin
Given a multi-turn task where the user changes a requirement partway through
When the agent continues
Then the final result satisfies the updated goal, not the original and not a blend of the two
```
**S6.3 — Honest done / partial / blocked accounting**
```gherkin
Given a goal that cannot be fully completed because of a blocker outside the agent's control
When the agent ends the turn
Then it reports the true status (done / partial / blocked-on-X) and what remains, rather than declaring success
```

## S7 — Long-horizon context

On a fixed model, context management is the binding constraint, so this group
deliberately fills the window over many steps to exercise the context-efficiency
metrics (ctx_peak, fill rate, compaction) — which short scenarios leave flat.

**S7.1 — Early constraint survives a long run**
```gherkin
Given a constraint stated ONCE near the start of a long, multi-step task (e.g. "every output filename must start with run_")
When the agent works through many subsequent steps that fill the context window
Then it still honors that early constraint at the final step (no "forgot which convention applied")
```
**S7.2 — No silent work loss as context grows**
```gherkin
Given a task that processes a series of inputs while maintaining a running summary
When the agent has accumulated a long trajectory
Then every input is accounted for in the final summary (none silently dropped) and earlier results are not contradicted
```
