"""
tool_generator.py
When AgentGeneral creates a new skill, this module:
1. Generates the equivalent Laravel PHP Tool class
2. Writes it to the Laravel project (via the WSL bind mount)
3. Runs composer dump-autoload inside the Docker container

Call on_skill_created(agent_instance, skill_name, description, tags, needs_input)
after a new skill is saved.
"""

import os
import subprocess
import logging
import re

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
LARAVEL_TOOLS_PATH = r"\\wsl.localhost\Ubuntu\home\wizmboya\Projects\chatbotapp\app\Ai\Tools"
DOCKER_CONTAINER   = "chatbotapp-laravel.test-1"


def _to_pascal_case(name: str) -> str:
    """Convert snake_case or CamelCase skill name to PascalCase PHP class name."""
    words = re.sub(r'([A-Z])', r'_\1', name).strip('_').split('_')
    return ''.join(w.capitalize() for w in words if w)


def _sanitize_description(desc: str) -> str:
    return desc.replace("'", "\\'")


def _tags_to_php_comment(tags: list) -> str:
    if not tags:
        return ""
    return "     * Tags: " + ", ".join(tags)


def generate_laravel_tool(
    skill_name: str,
    description: str,
    tags: list = None,
    needs_input: bool = True,
) -> dict:
    """
    Generate a Laravel Tool PHP class for the given AgentGeneral skill.
    """
    tags = tags or []
    class_name = _to_pascal_case(skill_name) + "Tool"
    file_name  = class_name + ".php"
    file_path  = os.path.join(LARAVEL_TOOLS_PATH, file_name)

    # Enrich description for better Laravel keyword matching.
    # Laravel's Tool matcher uses keyword overlap between user message and description().
    # Strategy: add CamelCase-decomposed skill name words + action verb synonyms
    # so paraphrased queries ("Create a meal plan", "Make a diet schedule") all match.

    name_words = re.sub(r'([A-Z])', r' \1', skill_name).strip().lower()

    # Build synonym expansions for common action verbs found in skill names/descriptions
    _VERB_SYNONYMS = {
        "generate":  "create make build produce",
        "create":    "generate make build produce",
        "make":      "create generate build produce",
        "find":      "search get fetch retrieve locate",
        "search":    "find get fetch retrieve lookup",
        "get":       "fetch retrieve find obtain",
        "plan":      "schedule organise organize create build",
        "schedule":  "plan organise organize create",
        "list":      "show display enumerate get find",
        "show":      "display list print output",
        "calculate": "compute evaluate solve work out",
        "compute":   "calculate evaluate solve",
        "count":     "tally total number sum",
        "convert":   "transform change translate",
        "translate":  "convert change",
        "format":    "style arrange structure",
        "extract":   "parse read retrieve get",
        "parse":     "extract read analyse analyze",
        "run":       "execute perform do",
        "execute":   "run perform do",
        "workout":   "exercise fitness training",
        "meal":      "food diet nutrition eating",
        "recipe":    "meal food cooking dish",
        "trip":      "travel journey itinerary",
        "itinerary": "trip travel schedule plan journey",
        "hotel":     "accommodation stay lodging",
        "attraction": "landmark sight tour destination",
        "weather":   "forecast temperature climate",
    }

    # Collect synonyms for words appearing in both description and skill name
    combined_text = (description + " " + name_words).lower()
    synonym_additions = []
    for word, synonyms in _VERB_SYNONYMS.items():
        if word in combined_text:
            synonym_additions.append(synonyms)

    enriched_description = " ".join(filter(None, [
        description,
        name_words,
        " ".join(synonym_additions),
    ])).strip()

    safe_description = _sanitize_description(enriched_description)
    tags_comment     = _tags_to_php_comment(tags)

    # ── handle() body — AgentGeneralService::run() returns an array,
    #    we must extract ['result'] and cast to string.
    if needs_input:
        schema_block = """
    public function schema(JsonSchema $schema): array
    {
        return [
            'input' => $schema->string()->required(),
        ];
    }"""
        handle_body = """
        $response = app(\\App\\Services\\AgentGeneralService::class)->run(
            $request['input'] ?? ''
        );
        return is_array($response) ? (string)($response['result'] ?? '') : (string)$response;"""
    else:
        schema_block = """
    public function schema(JsonSchema $schema): array
    {
        return [];
    }"""
        # Self-contained skill — pass the skill name as the task so AgentGeneral
        # routes directly to it via FAISS (score will be 1.0 on exact name match).
        handle_body = f"""
        $response = app(\\App\\Services\\AgentGeneralService::class)->run(
            '{skill_name}'
        );
        return is_array($response) ? (string)($response['result'] ?? '') : (string)$response;"""

    php_class = f"""<?php

namespace App\\Ai\\Tools;

use Illuminate\\Contracts\\JsonSchema\\JsonSchema;
use Laravel\\Ai\\Contracts\\Tool;
use Laravel\\Ai\\Tools\\Request;
use Stringable;

/**
 * {class_name}
 *
 * Auto-generated by AgentGeneral skill: {skill_name}
 * Description: {description}
{tags_comment}
 *
 * Delegates execution to AgentGeneral via HTTP.
 * AgentGeneral matches the skill via FAISS — no generation cost on repeat calls.
 */
class {class_name} implements Tool
{{
    public function description(): Stringable|string
    {{
        return '{safe_description}';
    }}

    public function handle(Request $request): Stringable|string
    {{{handle_body}
    }}
{schema_block}
}}
"""

    # ── Write the PHP file ────────────────────────────────────────────────────
    try:
        os.makedirs(LARAVEL_TOOLS_PATH, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(php_class)
        logger.info(f"PHP Tool class written: {file_path}")
    except Exception as e:
        logger.error(f"Failed to write PHP Tool class: {e}")
        return {"success": False, "class_name": class_name, "file_path": file_path, "error": str(e)}

    # ── Run composer dump-autoload inside Docker ──────────────────────────────
    try:
        cmd    = ["docker", "exec", DOCKER_CONTAINER, "composer", "dump-autoload", "--quiet"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            logger.info("composer dump-autoload completed successfully.")
        else:
            logger.warning(f"composer dump-autoload stderr: {result.stderr}")
    except subprocess.TimeoutExpired:
        logger.error("composer dump-autoload timed out.")
        return {"success": False, "class_name": class_name, "file_path": file_path, "error": "timeout"}
    except Exception as e:
        logger.error(f"Failed to run composer dump-autoload: {e}")
        return {"success": False, "class_name": class_name, "file_path": file_path, "error": str(e)}

    return {
        "success":    True,
        "class_name": class_name,
        "file_name":  file_name,
        "file_path":  file_path,
        "error":      None,
    }


def on_skill_created(
    agent_instance,
    skill_name: str,
    description: str,
    tags: list = None,
    needs_input: bool = True,
) -> dict:
    """
    Hook called from agent.py / server.py after a new skill is saved to disk.
    Generates the Laravel Tool and sets flags on the agent instance for the API response.
    """
    result = generate_laravel_tool(skill_name, description, tags or [], needs_input)

    if result["success"]:
        agent_instance._last_tool_generated  = True
        agent_instance._last_tool_class_name = result["class_name"]
        logger.info(f"Laravel Tool '{result['class_name']}' generated and registered.")
    else:
        agent_instance._last_tool_generated  = False
        agent_instance._last_tool_class_name = None
        logger.error(f"Laravel Tool generation failed: {result['error']}")

    return result