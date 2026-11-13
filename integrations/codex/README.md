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

In Codex, invoke using the `$skill` command format with any of the four execution modes:

```text
# 1. Project discovery & feature inventory
$ghost-hunt discover

# 2. Deep feature investigation & verification
$ghost-hunt investigate checkout

# 3. Whole-repository route & architecture audit
$ghost-hunt audit

# 4. Regression & fix verification
$ghost-hunt verify checkout
```

*(If you invoke bare `$ghost-hunt investigate`, Ghost Hunt detects your project context, locks scope away from example fixtures, and asks for a feature target).*

Or ask in natural language:

```text
"Investigate our checkout feature and verify whether inventory deduction works."
"Audit the repository for missing routes, unused endpoints, and testing gaps."
```

Codex executes the investigation using its native sandbox tools, file reading, and terminal execution.

---

## 4. Optional Advanced CLI Engine

If you want deterministic CI/CD verification journeys using the Python CLI, install the package separately (requires Python 3.11+):

```bash
pip install "ghost-feature-hunter[all]"
```
