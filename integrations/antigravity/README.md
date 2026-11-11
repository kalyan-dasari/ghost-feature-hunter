# Google Antigravity integration

Copy the canonical Agent Skill directory from `../../skills/ghost-feature-hunter/` to `.agents/skills/ghost-feature-hunter/` in a project or `~/.gemini/config/skills/ghost-feature-hunter/` for user-wide availability. Antigravity's app, CLI, and IDE use these shared workspace/global locations. Keep `SKILL.md` and its `references/` directory together. See [Antigravity skills documentation](https://antigravity.google/docs/skills).

Install the Python CLI separately from the repository root with `python -m pip install -e .`. This integration uses the same engine as Codex and Claude Code; there is no platform-specific verification engine.
