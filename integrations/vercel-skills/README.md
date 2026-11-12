# Vercel Agent Skills CLI Integration

Install the canonical Agent Skill directly using the Agent Skills open standard CLI:

```console
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-feature-hunter
```

The CLI will prompt you to select your target agent (e.g. Anthropic Claude Code, OpenAI Codex, Google Antigravity, or custom workspace).

Install the Python verification engine separately in your environment:

```console
python -m pip install -e ".[dev,demo,browser]"
```

