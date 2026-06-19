# Subagents

Subagent definitions. Each subagent is a markdown file:

```
.claude/agents/<agent-name>.md
```

with YAML frontmatter (`name`, `description` — when to delegate to it, optional
`tools`) followed by the agent's system prompt. Add one when a task type is
worth delegating (e.g. review passes, research sweeps).
