import re


def _clean(value: str) -> str:
    """Strip markdown bold/italic asterisks, hashes, backticks, and whitespace."""
    value = re.sub(r"[*#`]", "", value)
    return value.strip()


def _check_imports(code: str) -> str:
    """
    Auto-inject missing common imports into generated skill code.
    Uses regex with word boundaries to avoid false positives.
    """
    fixes = {
        r"\bdatetime\.datetime\b":  "import datetime",
        r"\bdatetime\.date\b":      "import datetime",
        r"\bdatetime\.timedelta\b": "import datetime",
        r"\bmath\.\w":              "import math",
        r"\bjson\.\w":              "import json",
        r"\bos\.path\b":            "import os",
        r"\bos\.makedirs\b":        "import os",
        r"\bos\.listdir\b":         "import os",
        r"\bos\.getcwd\b":          "import os",
        r"\bre\.\w":                "import re",
        r"\brandom\.\w":            "import random",
        r"\bsys\.argv\b":           "import sys",
        r"\bsys\.exit\b":           "import sys",
    }
    imports_to_add = []
    for pattern, imp in fixes.items():
        if re.search(pattern, code) and imp not in code:
            imports_to_add.append(imp)

    if imports_to_add:
        code = "\n".join(sorted(set(imports_to_add))) + "\n" + code
    return code


def _validate_syntax(code: str):
    """Run compile() to catch syntax errors before saving the skill."""
    try:
        compile(code, "<generated_skill>", "exec")
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError on line {e.lineno}: {e.msg}"


# Flexible field patterns — handles "SKILL_NAME", "Skill Name", "SKILL NAME" etc.
_FIELD_PATTERNS = {
    "name":        re.compile(r"SKILL[\s_]NAME\s*:\s*(.+)",   re.I),
    "description": re.compile(r"DESCRIPTION\s*:\s*(.+)",      re.I),
    "tags":        re.compile(r"TAGS\s*:\s*(.+)",             re.I),
    "script":      re.compile(r"SCRIPT[\s_]NAME\s*:\s*(.+)",  re.I),
}


def parse_skill(text):

    skill = {}

    matches = {field: pattern.search(text) for field, pattern in _FIELD_PATTERNS.items()}

    # Extract code block
    code_match = re.search(r"```python(.*?)```", text, re.S)
    if not code_match:
        code_match = re.search(r"SCRIPT[\s_]CODE\s*:\s*\n(.*)", text, re.S | re.I)

    # name, description and code are the minimum required fields
    if not (matches["name"] and matches["description"] and code_match):
        print(f"  [parse] Missing required fields — "
              f"name:{bool(matches['name'])} "
              f"desc:{bool(matches['description'])} "
              f"code:{bool(code_match)}")
        return None

    skill["name"]        = _clean(matches["name"].group(1))
    skill["description"] = _clean(matches["description"].group(1))
    skill["code"]        = _check_imports(code_match.group(1).strip())

    # Validate syntax before accepting
    valid, error = _validate_syntax(skill["code"])
    if not valid:
        print(f"  [parse] Rejected skill '{skill['name']}' — {error}")
        return None

    # Reject skills that print placeholder text — these produce garbage chatbot replies
    # Matches: print("[result]"), print("<value>"), print("Usage:"), f"[destination]" etc.
    _placeholder_in_code = re.search(
        r'print\s*\(.*?[\'"]\s*(\[[A-Za-z_][A-Za-z0-9_ ]*\]|<[A-Za-z_][A-Za-z0-9_ ]*>)',
        skill["code"]
    )
    if _placeholder_in_code:
        print(f"  [parse] Rejected skill '{skill['name']}' — contains placeholder output: {_placeholder_in_code.group(1)}")
        return None

    # Reject skills that have "Usage:" or "usage:" as a printed string in code
    if re.search(r'print\s*\(.*?[Uu]sage:', skill["code"]):
        print(f"  [parse] Rejected skill '{skill['name']}' — prints usage/help message")
        return None

    # Derive script filename from SCRIPT_NAME or fall back to SKILL_NAME
    if matches["script"]:
        skill["script"] = _clean(matches["script"].group(1))
    else:
        skill["script"] = re.sub(r"[^\w]", "_", skill["name"]).lower() + ".py"

    # Handle tags safely
    if matches["tags"]:
        raw_tags = _clean(matches["tags"].group(1))
        skill["tags"] = [t.strip() for t in raw_tags.split(",") if t.strip()]
    else:
        skill["tags"] = []

    return skill