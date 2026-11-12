# OpenAI Codex Integration

Install the `ghost-hunt` Agent Skill for OpenAI Codex / OpenAI Agents.

---

## 1. Quick Install via Agent Skills CLI

From your project root:

```bash
npx skills add kalyan-dasari/ghost-feature-hunter --skill ghost-hunt
```

When prompted, select **Codex / OpenAI Agents**.

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
```

Or ask in natural language:

```text
"Investigate our checkout feature and verify whether inventory deduction works."
```

Codex executes the investigation using its native sandbox tools, file reading, and terminal execution.

---

## 4. Optional Advanced CLI Engine

If you want deterministic CI/CD verification journeys using the Python CLI, install the package separately:

```bash
pip install "ghost-feature-hunter[all]"
```
