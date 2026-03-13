import os
import yaml


def load_skills():

    skills = []
    base_dir = "skills"

    if not os.path.exists(base_dir):
        print("Skills directory not found.")
        return skills

    for folder in os.listdir(base_dir):

        skill_dir = os.path.join(base_dir, folder)

        if not os.path.isdir(skill_dir):
            continue

        skill_file = os.path.join(skill_dir, "SKILL.md")

        if not os.path.exists(skill_file):
            continue

        try:

            with open(skill_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if data is None:
                print(f"Skipping empty skill file: {skill_file}")
                continue

            if not isinstance(data, dict):
                print(f"Invalid skill format in {skill_file}")
                continue

            name = data.get("name", folder)
            description = data.get("description", "")
            script = data.get("script", "")
            tags = data.get("tags", [])

            # Normalize tags
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            elif not isinstance(tags, list):
                tags = []

            script_path = os.path.join(skill_dir, script)

            if not os.path.exists(script_path):
                print(f"Script not found for skill '{name}': {script_path}")
                continue

            skill = {
                "name": name,
                "description": description,
                "tags": tags,
                "script": script_path
            }

            skills.append(skill)

        except Exception as e:
            print(f"Error reading {skill_file}: {e}")

    return skills