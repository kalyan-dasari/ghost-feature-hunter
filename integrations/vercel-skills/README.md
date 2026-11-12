# Agent Skills CLI Integration

Install the `ghost-hunt` Agent Skill directly using the open standard Agent Skills CLI (`skills@latest`, requires Node.js 22.20.0+):

```console
# Interactive selection
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt

# Direct non-interactive installation
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt -y --copy --agent antigravity
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt -y --copy --agent claude-code
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt -y --copy --agent codex
```

### Installation Targets:
- **Google Antigravity:** `.agents/skills/ghost-hunt/`
- **Anthropic Claude Code:** `.claude/skills/ghost-hunt/`
- **OpenAI Codex:** `.agents/skills/ghost-hunt/`

Once installed, open your coding agent in the repository and invoke:
- **Antigravity / Claude Code:** `/ghost-hunt` or `/ghost-hunt investigate <feature>`
- **OpenAI Codex:** `$ghost-hunt` or `$ghost-hunt investigate <feature>`

### Managing the Skill:
```console
# List installed skills
npx skills list

# Update skill to latest version
npx skills update ghost-hunt

# Remove skill
npx skills remove ghost-hunt
```

---

## Optional Deterministic Verification Engine

The skill functions immediately using your agent's native tools. If you also wish to install the optional Python CLI for deterministic CI verification journeys (requires Python 3.11+):

```console
pip install "ghost-feature-hunter[all]"
```
