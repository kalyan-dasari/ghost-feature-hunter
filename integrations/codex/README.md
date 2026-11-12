# OpenAI Codex Integration

Install and use the `ghost-hunt` Agent Skill with OpenAI Codex.

---

## 1. Quick Install via Agent Skills CLI

From your project root (requires Node.js 22.20.0+):

```bash
# Interactive selection
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt

# Or direct non-interactive installation
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt -y --copy --agent codex
```

The skill is installed to `.agents/skills/ghost-hunt/`.

---

## 2. Manual Installation

Copy the canonical skill directory into your Codex skills directory:

```bash
# Project-scoped skill (recommended)
mkdir -p .agents/skills/
cp -r path/to/ghost-feature-hunter/skills/ghost-hunt/ .agents/skills/ghost-hunt/

# Or Global user configuration
mkdir -p ~/.agents/skills/
cp -r path/to/ghost-feature-hunter/skills/ghost-hunt/ ~/.agents/skills/ghost-hunt/
```

Keep `SKILL.md`, `references/`, `templates/`, and `examples/` together in the directory.

---

## 3. How to Invoke in Codex

In Codex, invoke using the `$skill` command format:

```text
$ghost-hunt
```

Or run an explicit feature investigation:

```text
$ghost-hunt investigate checkout
$ghost-hunt investigate user-registration
$ghost-hunt investigate payment-processing
```

Or ask in natural language:

```text
"Investigate our checkout feature and verify whether inventory deduction works."
```

Codex executes the investigation using its native sandbox tools, file reading, and terminal execution.

---

## 4. Optional Advanced CLI Engine

If you want deterministic CI/CD verification journeys using the Python CLI, install the package separately (requires Python 3.11+):

```bash
pip install "ghost-feature-hunter[all]"
```
