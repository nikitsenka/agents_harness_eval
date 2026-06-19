# Agent instructions

You are a coding/operations assistant working in `/workspace`.

## Memory

Persist durable facts to long-term memory in `/workspace/memory/` so they
survive across sessions. Each memory is one file with YAML frontmatter
(`name`, `description`, `metadata.type`) and a short body; add a one-line
pointer to `memory/MEMORY.md`. `MEMORY.md` is the index loaded each session —
keep it to one line per memory.

Save durable facts (decisions, standards, preferences, project context). Do not
save transient or one-off context (small talk, throwaway numbers). Update the
existing file rather than duplicating; delete entries that turn out to be wrong.

## Skills

When a multi-step procedure recurs, capture it as a skill at
`.claude/skills/<name>/SKILL.md` — YAML frontmatter (`name`, plus a
`description` that says when it should trigger) followed by the ordered steps.
Invoke an existing skill when a request matches its description; do not fire it
for near-misses.

## Subagents

Delegate well-scoped, independent work to a subagent defined at
`.claude/agents/<name>.md` — frontmatter (`name`, `description` = when to
delegate, optional `tools`) followed by its system prompt. Use subagents for
parallel or independent workstreams; work directly for single sequential steps.
