# Codex integration

Use the canonical Agent Skill at `../../skills/ghost-feature-hunter/SKILL.md`. Copy the complete `ghost-feature-hunter` skill directory to `.agents/skills/ghost-feature-hunter/` in a project or `~/.agents/skills/ghost-feature-hunter/` for user-wide availability. See [official Codex installation guidance](https://developers.openai.com/api/reference/cli).

Install the Python CLI separately from the repository root with `python -m pip install -e .`. The skill calls the same `ghost-hunter` engine used by other agents; it does not bundle a second engine.
