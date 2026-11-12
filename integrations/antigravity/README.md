# Google Antigravity Integration

Install and use the `ghost-hunt` Agent Skill with Google Antigravity.

---

## 1. Install via Agent Skills CLI

From your project root (requires Node.js 22.20.0+):

```bash
# Project-level install (recommended)
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt -y --copy --agent antigravity

# Or Global user-level install across all projects
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt -g --copy --agent antigravity
```

- **Project Target:** `<project-root>/.agents/skills/ghost-hunt/`
- **Global Target (Skills CLI):** `~/.gemini/config/skills/ghost-hunt/`

---

## 2. Manual Installation

If installing manually without `npx`, copy the canonical skill directory into your project workspace or global Antigravity configuration:

```bash
# Workspace-scoped skill (recommended)
mkdir -p .agents/skills/
cp -r path/to/ghost-feature-hunter/skills/ghost-hunt/ .agents/skills/ghost-hunt/

# Or Global user configuration
mkdir -p ~/.gemini/antigravity/skills/
cp -r path/to/ghost-feature-hunter/skills/ghost-hunt/ ~/.gemini/antigravity/skills/ghost-hunt/
```

> [!NOTE]
> **Antigravity Global Paths:** The official Skills CLI maps Antigravity global skills to `~/.gemini/config/skills/`, while Antigravity's native environment also discovers global skills from `~/.gemini/antigravity/skills/`. Both paths are recognized depending on your setup; workspace installation (`.agents/skills/ghost-hunt/`) is recommended for project isolation.

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
