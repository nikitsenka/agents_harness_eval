# Vanilla Claude Code — no soul, no project memory, no MCP, no skills.
# A bare harness baseline to compare against Hermes on the same model.
FROM node:20-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates git ripgrep \
    && rm -rf /var/lib/apt/lists/*

# Pinned to the version used in the recorded eval; bump as needed.
RUN npm install -g @anthropic-ai/claude-code@2.1.169

# Claude Code refuses --dangerously-skip-permissions as root.
RUN useradd --create-home --uid 10001 app
USER app
WORKDIR /workspace

# Idle so the eval runner can `docker compose exec` into it.
CMD ["sleep", "infinity"]
