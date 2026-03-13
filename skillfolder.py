import os
import re


def _sanitize_name(name: str) -> str:
    """
    Remove any characters that are invalid in Windows/Linux folder names.
    Keeps alphanumerics, spaces, hyphens, underscores.
    """
    name = re.sub(r"[*#`\"'<>|?/\\:.]", "", name)
    name = name.strip()
    return name


def create_skill(skill):

    # Sanitize then normalize folder name
    clean_name = _sanitize_name(skill["name"])
    skill_name = clean_name.replace(" ", "_")

    if not skill_name:
        raise ValueError(f"Skill name is empty after sanitization: '{skill['name']}'")

    base = os.path.join("skills", skill_name)
    scripts_dir = os.path.join(base, "scripts")

    os.makedirs(scripts_dir, exist_ok=True)

    # Write SKILL.md
    skill_md_path = os.path.join(base, "SKILL.md")
    tags = skill.get("tags", [])
    tags_str = ",".join(tags)

    with open(skill_md_path, "w", encoding="utf-8") as f:
        f.write(f"""name: {clean_name}
description: {skill['description']}
tags: {tags_str}
script: scripts/{skill['script']}
""")

    # Write the Python script
    script_path = os.path.join(scripts_dir, skill["script"])

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(skill["code"].strip())

    print(f"\nSkill saved: {clean_name}")