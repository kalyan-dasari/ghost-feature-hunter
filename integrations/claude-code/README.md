# Claude Code Integration

Install the `ghost-hunt` Agent Skill for Anthropic Claude Code.

---

## 1. Quick Install via Agent Skills CLI

From your project root:

```bash
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt
```

When prompted, select **Claude Code**.

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

In Claude Code, invoke the slash command:

```text
/ghost-hunt
```

Or run an explicit feature investigation:

```text
/ghost-hunt investigate checkout
```

Or ask in natural language:

```text
"Investigate our checkout flow and identify why order totals are mismatched."
```

Claude Code executes the investigation using its native file access, terminal commands (`curl`, test runners), and diagnostics.

---

## 4. Optional Advanced CLI Engine

If you want deterministic CI/CD verification journeys using the Python CLI, install the package separately:

```bash
pip install "ghost-feature-hunter[all]"
```
