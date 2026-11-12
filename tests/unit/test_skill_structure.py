import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO_ROOT / "skills" / "ghost-hunt"
SKILL_MD = SKILL_DIR / "SKILL.md"


def test_skill_file_and_directory_exist():
    assert SKILL_DIR.is_dir(), f"Skill directory missing: {SKILL_DIR}"
    assert SKILL_MD.is_file(), f"SKILL.md missing: {SKILL_MD}"


def test_skill_frontmatter_conforms_to_agent_skills_spec():
    content = SKILL_MD.read_text(encoding="utf-8")
    assert content.startswith("---"), "SKILL.md must start with YAML frontmatter delimiter '---'"
    parts = content.split("---", 2)
    assert len(parts) >= 3, "SKILL.md must have opening and closing '---' delimiters"
    frontmatter = parts[1]

    # Check required fields
    name_match = re.search(r"^name:\s*([a-z0-9_-]+)\s*$", frontmatter, re.MULTILINE)
    assert name_match is not None, "Frontmatter must contain valid 'name'"
    assert name_match.group(1) == "ghost-hunt", f"Skill name must be 'ghost-hunt', got {name_match.group(1)}"

    desc_match = re.search(r"^description:\s*(.+)$", frontmatter, re.MULTILINE)
    assert desc_match is not None, "Frontmatter must contain 'description'"
    assert len(desc_match.group(1).strip()) > 10, "Description must be substantive"


def test_skill_md_is_concise_under_500_lines():
    lines = SKILL_MD.read_text(encoding="utf-8").splitlines()
    assert len(lines) < 500, f"SKILL.md must be under 500 lines for progressive disclosure, got {len(lines)}"


def test_skill_relative_links_resolve_to_existing_files():
    content = SKILL_MD.read_text(encoding="utf-8")
    # Find markdown links: [text](path)
    links = re.findall(r"\[.*?\]\((?!http)([a-zA-Z0-9_./-]+\.[a-z0-9]+)\)", content)
    assert len(links) >= 5, "SKILL.md should reference supporting guides and templates"
    for link in links:
        target = (SKILL_DIR / link).resolve()
        assert target.exists(), f"Broken relative link in SKILL.md: {link} -> {target}"


def test_templates_and_examples_exist():
    templates_dir = SKILL_DIR / "templates"
    examples_dir = SKILL_DIR / "examples"

    assert (templates_dir / "report-template.md").is_file()
    assert (templates_dir / "journey-template.json").is_file()
    assert (examples_dir / "checkout-investigation.md").is_file()


def test_agent_integration_documents_exist():
    integrations_dir = REPO_ROOT / "integrations"
    for agent in ("antigravity", "claude-code", "codex", "vercel-skills"):
        readme = integrations_dir / agent / "README.md"
        assert readme.is_file(), f"Missing integration guide for {agent}: {readme}"
        text = readme.read_text(encoding="utf-8")
        assert "ghost-hunt" in text, f"Integration guide {agent} must reference 'ghost-hunt'"


def test_skills_and_agents_skills_mirror_are_synchronized():
    agents_skill_dir = REPO_ROOT / ".agents" / "skills" / "ghost-hunt"
    if not agents_skill_dir.exists():
        return

    # Check all canonical files exist in .agents copy
    for canonical_file in SKILL_DIR.rglob("*"):
        if canonical_file.is_file():
            rel_path = canonical_file.relative_to(SKILL_DIR)
            mirror_file = agents_skill_dir / rel_path
            assert mirror_file.is_file(), f"Mirror file missing in .agents: {rel_path}"
            if canonical_file.suffix.lower() in {".md", ".json", ".txt", ".yml", ".yaml"}:
                assert canonical_file.read_text(encoding="utf-8").splitlines() == (
                    mirror_file.read_text(encoding="utf-8").splitlines()
                ), f"Content divergence between canonical skill and .agents mirror: {rel_path}"
            else:
                assert canonical_file.read_bytes() == mirror_file.read_bytes(), (
                    f"Content divergence between canonical skill and .agents mirror: {rel_path}"
                )

    # Check no extra orphan files in .agents copy
    for mirror_file in agents_skill_dir.rglob("*"):
        if mirror_file.is_file():
            rel_path = mirror_file.relative_to(agents_skill_dir)
            canonical_file = SKILL_DIR / rel_path
            assert canonical_file.is_file(), f"Orphan file in .agents mirror not in canonical: {rel_path}"


