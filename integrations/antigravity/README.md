# Google Antigravity Integration

Install and use the `ghost-hunt` Agent Skill with Google Antigravity.

---

## 1. Quick Install via Agent Skills CLI

From your project root (requires Node.js 22.20.0+):

```bash
# Interactive selection
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt

# Or direct non-interactive installation
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt -y --copy --agent antigravity
```

The skill is installed to `.agents/skills/ghost-hunt/`.

---

## 2. Manual Installation

Copy the canonical skill directory into your project workspace or global Antigravity configuration:

```bash
# Workspace-scoped skill (recommended)
mkdir -p .agents/skills/
cp -r path/to/ghost-feature-hunter/skills/ghost-hunt/ .agents/skills/ghost-hunt/

# Or Global user configuration
mkdir -p ~/.gemini/antigravity/skills/
cp -r path/to/ghost-feature-hunter/skills/ghost-hunt/ ~/.gemini/antigravity/skills/ghost-hunt/
```

Keep `SKILL.md`, `references/`, `templates/`, and `examples/` together in the directory.

---

## 3. How to Invoke in Antigravity Chat

In any Antigravity conversation or IDE session, invoke the skill directly:

```text
/ghost-hunt
```

Or trigger specific feature investigations:

```text
/ghost-hunt investigate checkout
/ghost-hunt investigate user-registration
/ghost-hunt investigate payment-webhooks
```

Or ask in natural language:

```text
"Investigate my checkout feature and verify whether order persistence works."
```

Antigravity executes the investigation using its native tools (file reader, shell/terminal commands, `curl`, browser tool).

---

## 4. Optional Advanced CLI Engine

If you want deterministic CI/CD verification journeys using the Python CLI, install the package separately (requires Python 3.11+):

```bash
pip install "ghost-feature-hunter[all]"
```
