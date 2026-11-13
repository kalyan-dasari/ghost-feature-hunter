# Anthropic Claude Code Integration

Install and use the `ghost-hunt` Agent Skill with Anthropic Claude Code.

---

## 1. Quick Install via Agent Skills CLI

From your project root (requires Node.js 22.20.0+):

```bash
# Interactive selection
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt

# Or direct non-interactive installation
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt -y --copy --agent claude-code
```

The skill is installed to `.claude/skills/ghost-hunt/`.

---

## 2. Manual Installation

Copy the canonical skill directory into your Claude Code skills directory:

```bash
# Project-scoped skill (recommended)
mkdir -p .claude/skills/
cp -r path/to/ghost-feature-hunter/skills/ghost-hunt/ .claude/skills/ghost-hunt/

# Or Global user configuration
mkdir -p ~/.claude/skills/
cp -r path/to/ghost-feature-hunter/skills/ghost-hunt/ ~/.claude/skills/ghost-hunt/
```

Keep `SKILL.md`, `references/`, `templates/`, and `examples/` together in the directory.

---

## 3. How to Invoke in Claude Code

In Claude Code, invoke Ghost Hunt using any of its four execution modes:

```text
# 1. Project discovery & feature inventory
/ghost-hunt discover

# 2. Deep feature investigation & verification
/ghost-hunt investigate checkout

# 3. Whole-repository route & architecture audit
/ghost-hunt audit

# 4. Regression & fix verification
/ghost-hunt verify checkout
```

*(If you invoke bare `/ghost-hunt investigate`, Ghost Hunt detects your project context, locks scope away from example fixtures, and asks for a feature target).*

Or ask in natural language:

```text
"Investigate our checkout flow and identify why order totals are mismatched."
"Audit the repository for missing routes, unused endpoints, and testing gaps."
```

Claude Code executes the investigation using its native file access, terminal commands (`curl`, test runners), and diagnostics.

---

## 4. Optional Advanced CLI Engine

If you want deterministic CI/CD verification journeys using the Python CLI, install the package separately (requires Python 3.11+):

```bash
pip install "ghost-feature-hunter[all]"
```
