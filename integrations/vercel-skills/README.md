# Vercel Agent Skills CLI Integration

Install the `ghost-hunt` Agent Skill directly using the Agent Skills open standard CLI:

```console
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt
```

The CLI will prompt you to select your target agent:
- **Google Antigravity** (`.agents/skills/ghost-hunt/`)
- **Anthropic Claude Code** (`.claude/skills/ghost-hunt/`)
- **OpenAI Codex** (`.agents/skills/ghost-hunt/`)
- **Custom Workspace**

Once installed, open your coding agent in the repository and invoke:
- Antigravity / Claude Code: `/ghost-hunt`
- OpenAI Codex: `$ghost-hunt`

---

## Optional Deterministic Verification Engine

The skill functions immediately using your agent's native tools. If you also wish to install the optional Python CLI for deterministic CI verification journeys:

```console
pip install "ghost-feature-hunter[all]"
```
