# Google Antigravity Integration

Install the `ghost-hunt` Agent Skill for Google Antigravity.

---

## 1. Quick Install via Agent Skills CLI

From your project root:

```bash
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt
```

When prompted, select **Google Antigravity**.

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
```

Or ask in natural language:

```text
"Investigate my checkout feature and verify whether order persistence works."
```

Antigravity executes the investigation using its native tools (file reader, shell/terminal commands, browser tool).

---

## 4. Optional Advanced CLI Engine

If you want deterministic CI/CD verification journeys using the Python CLI, install the package separately:

```bash
pip install "ghost-feature-hunter[all]"
```
