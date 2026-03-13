import os
import sys
import re
import shutil


sys.stdout.reconfigure(encoding="utf-8")

from sentence_transformers import SentenceTransformer
from langchain_ollama import ChatOllama

from skill_engine.loader import load_skills
from skill_engine.selector import select_skill
from skill_engine.runner import run_skill
from skill_engine.vector_memory import add_skill_vector, index

from skillfolder import create_skill
from parse import parse_skill
from planner.planner import plan, is_simple_task
from skill_engine.duplicate_filter import is_duplicate
from tool_generator import on_skill_created

from config import SKILL_MATCH_THRESHOLD, SKILLS_DIR, EMBEDDING_MODEL


# Initialize models
embedder = SentenceTransformer(EMBEDDING_MODEL)  # Uses model from config

llm = ChatOllama(
        model="mistral:7b",
        base_url="http://172.16.10.11:11435",
        temperature=0.1,
)


# Load skills from disk
skills = load_skills()

print("Loaded skills:")
for s in skills:
    print("-", s["name"])


def _build_embed_text(skill: dict) -> str:
    """
    Build rich embedding text including CamelCase decomposition
    so FAISS catches synonym queries.
    """
    name_words = re.sub(r"([A-Z])", r" \1", skill.get("name", "")).lower().strip()
    parts = [
        skill.get("name", ""),
        skill.get("description", ""),
        " ".join(skill.get("tags", [])),
        name_words,
    ]
    return " ".join(p for p in parts if p).strip()


# Embed all loaded skills into FAISS at startup if index is empty
if index.ntotal == 0 and skills:
    print("\nFAISS index is empty. Embedding loaded skills...")
    for s in skills:
        vec = embedder.encode([_build_embed_text(s)])[0]
        add_skill_vector(vec, s)
    print(f"Embedded {len(skills)} skills into FAISS index.\n")


def resolve_script_path(skill):
    script = skill["script"]
    if os.path.exists(script):
        return script
    folder = skill["name"].replace(" ", "_")
    return os.path.join(SKILLS_DIR, folder, "scripts", script)


def classify_intent(task: str) -> str:
    """
    Classify the user's input intent before any skill logic runs.

    Returns one of:
      "task"          — actionable request the agent should execute
      "conversational"— greeting, statement, question about the agent itself

    Uses fast regex rules first, falls back to LLM for ambiguous cases.
    """
    task_lower = task.lower().strip()

    # Time/date queries MUST always be tasks — never let LLM answer these
    # as it will hallucinate wrong times and dates
    time_date_task_patterns = [
        r"\b(whats|what.s)\s+(the\s+)?(date|time|day)\b",
        r"\bwhat\s+(is|are)\s+(the\s+)?(current\s+)?(time|date|day)\b",
        r"\bwhat\s+time\s+is\s+it\b",
        r"\bwhat\s+day\s+is\s+(it|today)\b",
        r"^(time|date|day)(\s+now)?\s*$",
        r"\b(current|today.s)\s+(time|date|day)\b",
        r"\btime\s+(now|today|currently)\b",
        r"\bdate\s+(today|now|currently)\b",
    ]
    for pattern in time_date_task_patterns:
        if re.search(pattern, task_lower):
            return "task"

    # Clear conversational patterns — handle immediately, no skill needed
    conversational_patterns = [
        r"^(hi|hello|hey|howdy|greetings|good (morning|afternoon|evening))",
        r"^(my name is|i am|i'm|call me)\b",
        r"^(thanks|thank you|cheers|great|awesome|cool|nice|ok|okay|got it|perfect)\b",
        r"^(bye|goodbye|see you|cya|quit|exit)\b",
        r"^(who are you|what are you|what can you do|help me understand)\b",
        r"^(yes|no|maybe|sure|of course|absolutely|definitely)\b",
        r"^(how are you|are you feeling|do you|can you tell me about yourself)\b",
        # Emotional/physical statements — not actionable tasks
        r"^i (am|feel|'m) (so |very |really )?(hungry|tired|bored|happy|sad|angry|excited|stressed)\b",
        r"^i (need|want) (a |to )?(break|rest|food|drink|coffee)\b",
    ]
    for pattern in conversational_patterns:
        if re.search(pattern, task_lower):
            return "conversational"

    # Pure arithmetic expressions — answer directly, never create a skill
    arith_match = re.match(r"^\s*-?\d+([\.,]\d+)?\s*[+\-*/^]\s*-?\d+", task_lower)
    if arith_match:
        return "conversational"

    # Clear task patterns — always actionable
    task_patterns = [
        r"\b(create|make|build|generate|write|find|get|show|list|calculate|count|"
         r"convert|translate|plan|search|extract|parse|format|run|execute)\b",
        r"\b(what is the (time|date|day|weather))\b",
        r"\b(how (much|many|long|far|old))\b",
        r"\.(txt|csv|json|pdf|xlsx|py)\b",  # file reference = task
    ]
    for pattern in task_patterns:
        if re.search(pattern, task_lower):
            return "task"

    # Ambiguous — ask LLM to classify
    prompt = f"""Classify this user input as either a task or conversational message.

A TASK is an actionable request asking the agent to do something, find something, or create something.
CONVERSATIONAL is a greeting, personal statement, small talk, or question about the agent.

Reply with ONE word only: task or conversational

Input: "{task}"
Classification:"""

    try:
        response = llm.invoke(prompt)
        classification = response.content.strip().lower().split()[0]
        if classification in ("task", "conversational"):
            return classification
    except Exception:
        pass

    # Default to task if unsure — better to attempt than ignore
    return "task"


def handle_conversational(task: str) -> str:
    """Generate a natural conversational response using the LLM."""
    prompt = f"""You are a helpful AI agent assistant. Respond naturally and briefly to this message.
Do not mention skills, tools, or technical details unless asked.

User: {task}
Assistant:"""
    try:
        response = llm.invoke(prompt)
        return response.content.strip()
    except Exception:
        return "I'm here to help! What would you like me to do?"


def _needs_input(task: str, skill: dict = None) -> bool:
    """
    Determine if a task requires user-supplied input.
    Checks actual skill script code for sys.argv usage — most reliable.
    Falls back to task text inference when no skill is provided.
    """
    if skill:
        # Check in-memory code first (newly generated skills)
        if skill.get("code"):
            return "sys.argv" in skill["code"]
        # For disk-loaded skills, read the script file directly
        script_path = skill.get("script", "")
        if script_path and os.path.exists(script_path):
            try:
                with open(script_path, "r", encoding="utf-8") as f:
                    return "sys.argv" in f.read()
            except Exception:
                pass
        return False  # if we can't read the file, assume self-contained

    # No skill provided — infer from task text
    input_indicators = [
        # File-based tasks
        r"\bin\b.{0,30}\.(txt|csv|json|pdf|xlsx|py)\b",
        r"\bof\s+\d+\b",
        r"\bconvert\b",
        r"\btranslate\b",
        r"\bcount\b.{0,20}\bin\b",
        r"\bextract\b",
        r"\bparse\b",
        r"\bfrom\b.{0,30}\bfile\b",
        # Destination/topic tasks — these should ALWAYS be parameterized
        # e.g. "find attractions in Kenya", "find hotels in Tokyo"
        r"\b(attractions?|hotels?|restaurants?|places?|things to do)\b.{0,30}\bin\b",
        r"\b(find|search|list|show|get)\b.{0,40}\bin\b.{2,30}$",
        r"\b(itinerary|trip|travel|visit)\b.{0,30}\bfor\b.{0,30}$",
        r"\b(itinerary|trip|travel|visit)\b.{0,30}\bto\b.{0,30}$",
    ]
    task_lower = task.lower()
    for pattern in input_indicators:
        if re.search(pattern, task_lower):
            return True
    return False


def extract_skill_input(step: str, original_task: str) -> str:
    """
    Extract the actual argument to pass to a skill.

    KEY FIX: Uses the ORIGINAL USER TASK as the primary source of truth,
    with the planner step as context. This ensures the real parameters
    (city names, durations, filenames) are extracted correctly.

    e.g.:
      step="Find hotels in Kenya for 7 days"
      original_task="Plan a 7 day trip to Kenya"
      → extracts "Kenya" (the city/country) not "7" (the number)
    """
    # Pattern 1: filename
    file_match = re.search(
        r"\b([\w\-]+\.(txt|csv|json|pdf|xlsx|py|md|log))\b",
        original_task, re.I
    )
    if file_match:
        return file_match.group(1)

    # Pattern 2: quoted string
    quoted_match = re.search(r'["\'](.+?)["\']', original_task)
    if quoted_match:
        return quoted_match.group(1)

    # Pattern 3: destination/location fast regex — avoids LLM call for common cases
    # catches "trip to Kenya", "hotels in Australia", "visit Tokyo" etc.
    dest_match = re.search(
        r"\b(?:to|in|for|at|near|visit|visiting)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        original_task
    )
    if dest_match:
        candidate = dest_match.group(1).strip()
        _NOT_PLACES = {"the", "a", "an", "my", "our", "your", "this", "that", "it",
                       "day", "days", "week", "weeks", "me", "us", "you"}
        if candidate.lower() not in _NOT_PLACES and len(candidate) > 2:
            return candidate

    # Use LLM to extract the right argument given both step and original task
    prompt = f"""You are a parameter extractor for an AI agent.

Given a task step and the original user request, extract ONLY the key input value
the step's script should receive as sys.argv[1].

Rules:
- Return ONLY the extracted value — no explanation, no punctuation
- Prefer the most specific, meaningful value (city name, country, filename, number)
- If the step is self-contained and needs no input, return: NONE
- Never return the entire sentence

Examples:
Original task: Plan a 7 day trip to Kenya
Step: Find hotels in Kenya for 7 days
→ Kenya

Original task: Count lines in report.txt
Step: Count lines in report.txt
→ report.txt

Original task: Calculate factorial of 9
Step: Calculate factorial of 9
→ 9

Original task: What is the current time
Step: Get current system time
→ NONE

Original task: {original_task}
Step: {step}
→"""

    try:
        response = llm.invoke(prompt)
        extracted = response.content.strip().strip('"').strip("'").split("\n")[0].strip()
        if not extracted or extracted.upper() in ("NONE", "N/A", ""):
            return ""
        return extracted
    except Exception:
        return ""


# Errors that mean the SKILL IS BROKEN (bad code) — delete it
_SKILL_BROKEN_PATTERNS = [
    "Traceback (most recent call last)",
    "TypeError",
    "AttributeError",
    "NameError",
    "SyntaxError",
    "IndentationError",
    "ImportError",
    "ModuleNotFoundError",
    "IndexError",
    "KeyError",
    "ZeroDivisionError",
]

# Errors that mean the INPUT WAS WRONG — skill is fine, don't delete it
_INPUT_ERROR_PATTERNS = [
    "FileNotFoundError",
    "No such file or directory",
    "File \'",
    "File \"",
    "does not exist",
    "not found",
    "Usage:",
    "usage:",
    "HTTPError",
    "ConnectionError",
    "TimeoutError",
]


def _run_with_validation(script_path: str, skill_input: str) -> tuple:
    """
    Run a skill and check if the result is valid.
    Returns (result, success, is_broken).

    Distinguishes between:
    - Broken skill (bad generated code)  → success=False, is_broken=True  → delete skill
    - Bad input (missing file etc.)      → success=False, is_broken=False → keep skill
    - Empty output                       → success=False, is_broken=True  → delete skill
    - Valid output                       → success=True,  is_broken=False → keep skill
    """
    result = run_skill(script_path, skill_input)

    # Input-related errors — skill code is correct, just wrong/missing input
    for pattern in _INPUT_ERROR_PATTERNS:
        if pattern in result:
            return result, False, False  # not broken, just bad input

    # Code-level errors — skill itself is broken
    for pattern in _SKILL_BROKEN_PATTERNS:
        if pattern in result:
            return result, False, True  # broken skill — delete it

    # Empty output with no error — likely broken logic
    if not result.strip():
        return result, False, True

    return result, True, False


def execute_or_create_skill(step: str, original_task: str):
    """
    Try to match and run an existing skill for a step.
    If no match, generate and save a new one.

    Passes original_task for correct input extraction.
    Validates result and marks broken skills.
    """
    skill, score = select_skill(step, skills)

    if skill and score >= SKILL_MATCH_THRESHOLD:
        print(f"  Using skill: {skill['name']} (score: {score:.2f})")

        needs_input = _needs_input(step, skill)  # pass skill to check code directly
        if needs_input:
            skill_input = extract_skill_input(step, original_task)
            if not skill_input:
                skill_input = step
        else:
            skill_input = ""  # self-contained skill — pass empty string

        result, success, is_broken = _run_with_validation(resolve_script_path(skill), skill_input)
        if success:
            return result
        if is_broken:
            print(f"  [warn] Skill '{skill['name']}' is broken — removing and regenerating")
            _delete_skill(skill)
        else:
            print(f"  [warn] Skill '{skill['name']}' got bad input — skipping to generation")
            # Fall through to skill generation below

    # No skill found (or existing skill failed) — generate a new one
    print("  No skill found. Creating new skill...\n")

    needs_input = _needs_input(step)

    # Extract the actual input value NOW so we can tell the LLM what the script will receive
    if needs_input:
        skill_input = extract_skill_input(step, original_task)
        # If extraction returns nothing useful OR returns the full step text verbatim,
        # treat this as self-contained — don't pass garbage as sys.argv[1]
        if not skill_input or skill_input.lower().strip() == step.lower().strip() or len(skill_input.split()) > 5:
            skill_input = None
            needs_input = False
            input_rule = (
                "2. This skill is SELF-CONTAINED — it does NOT need any user input\n"
                "3. Do NOT use sys.argv at all — demonstrate with built-in example values"
            )
        else:
            input_rule = (
                f"2. This skill requires input — read it from sys.argv[1]\n"
                f"   The input will be a value like: '{skill_input}'\n"
                f"3. Always include 'import sys' at the top\n"
                f"4. If sys.argv[1] is not provided, use a sensible default value and run normally — NEVER print a usage/help message\n"
                f"5. Design the skill to be GENERIC and REUSABLE — not hardcoded to '{skill_input}' specifically"
            )
    else:
        skill_input = None
        input_rule = (
            "2. This skill is SELF-CONTAINED — it does NOT need any user input\n"
            "3. Do NOT use sys.argv at all — run with no arguments"
        )

    prompt = f"""You are an AI agent that creates reusable Python skills.

Task this skill must handle:
{step}

Rules:
1. The skill must directly solve the task
{input_rule}
6. Script must print the result
7. Script must be a full executable Python file
8. Always import every module you use at the top of the script
9. Use ONLY the Python standard library — NO network access of any kind: no requests, no urllib, no socket, no http.client, no external APIs, no DNS lookups, no TCP connections
10. Write the SIMPLEST possible solution — plain for loops, no unnecessary imports or data structures
11. For math operations use simple arithmetic (+, -, *, /) directly — never use operator or functools modules
12. Every variable must be defined before use

CRITICAL REUSABILITY RULES — read carefully, this is mandatory:
- Skills must work for ANY input, not just one specific case
- NEVER hardcode a country, city, person, topic, or any specific name in the data
- The input value (sys.argv[1]) IS the subject — your output must vary completely based on it
- Use the input value directly inside all printed strings and labels

REUSABLE SKILL PATTERN — follow this exactly for destination/topic skills:
    import sys
    destination = sys.argv[1]
    categories = {{
        "Must-See Landmarks":    [f"The Grand {{destination}} Museum", f"Historic {{destination}} Old Town", f"{{destination}} National Monument"],
        "Natural Wonders":       [f"{{destination}} National Park", f"The {{destination}} River Valley", f"{{destination}} Coastal Reserve"],
        "Local Experiences":     [f"{{destination}} Street Food Market", f"{{destination}} Cultural Festival", f"Traditional {{destination}} Village"],
    }}
    for category, items in categories.items():
        print(f"\n{{category}}:")
        for item in items:
            print(f"  - {{item}}")

- SKILL_NAME must be GENERIC — no location, country, or topic in the name
  GOOD: "FindAttractions", "PlanTripItinerary", "FindHotels"
  BAD:  "FindAttractionsInAustralia", "AustraliaTripPlanner", "KenyaHotelFinder"
- DESCRIPTION must describe the skill generically: "Finds top attractions in a given destination"

CRITICAL FORMAT RULES:
- No markdown, no bold, no asterisks, no hashes anywhere in your response
- Field names exactly as shown, at the start of a line
- Code wrapped in triple backticks with python tag

SKILL_NAME: <generic name, no specific location/topic>
DESCRIPTION: <generic description — works for any input>
TAGS: <comma separated>
SCRIPT_NAME: <generic filename.py>

```python
<full executable python script>
```
"""

    response = llm.invoke(prompt)
    text = response.content
    print(text)

    new_skill = parse_skill(text)
    if not new_skill:
        return "Failed to parse or validate skill — skipping."

    # ── Bloat guard: reject skills with location-specific names ──────────────
    # If Mistral ignored the reusability rules and generated "FindHotelsInAustralia",
    # we catch it here and refuse to save it.
    _PLACE_NAMES = [
        "australia","kenya","japan","france","germany","india","china","usa","uk","brazil",
        "canada","mexico","italy","spain","thailand","indonesia","nigeria","egypt","peru",
        "argentina","colombia","chile","vietnam","malaysia","singapore","nairobi","sydney",
        "melbourne","tokyo","paris","london","berlin","dubai","cairo","toronto","miami",
        "amsterdam","barcelona","rome","madrid","lisbon","zurich","stockholm","oslo",
    ]
    skill_name_lower = new_skill.get("name", "").lower().replace(" ", "").replace("_", "")
    for place in _PLACE_NAMES:
        if place.replace(" ","") in skill_name_lower:
            print(f"  [bloat guard] Skill name '{new_skill['name']}' is location-specific — regenerating as generic.")
            # Patch the name and description to be generic, then continue
            # Strip the place name from skill name using a simple replacement
            import re as _re
            generic_name = _re.sub(
                r"(?i)(in|for|at|of)?" + place.replace(" ", r"\s*"),
                "", new_skill["name"], flags=_re.IGNORECASE
            ).strip(" _-")
            if not generic_name or len(generic_name) < 4:
                generic_name = new_skill["name"].split("In")[0].split("For")[0].strip()
            new_skill["name"] = generic_name if generic_name else new_skill["name"]
            new_skill["script"] = new_skill["script"].replace(place, "").replace(place.capitalize(), "").strip("_-.")
            if not new_skill["script"].endswith(".py"):
                new_skill["script"] += ".py"
            print(f"  [bloat guard] Renamed to: '{new_skill['name']}'")
            break

    duplicate, existing_name = is_duplicate(new_skill, skills)
    if duplicate:
        # Run the existing skill instead of returning the duplicate message
        logger.info(f"Duplicate detected — running existing skill: {existing_name}") if False else None
        existing_skill = next((s for s in skills if s["name"] == existing_name), None)
        if existing_skill:
            ex_needs_input = _needs_input(step, existing_skill)
            ex_input = extract_skill_input(step, original_task) if ex_needs_input else ""
            ex_result, ex_success, _ = _run_with_validation(resolve_script_path(existing_skill), ex_input)
            if ex_success:
                return ex_result
        # existing skill also failed or not found — fall through to save regenerated version

    create_skill(new_skill)

    vec = embedder.encode([_build_embed_text(new_skill)])[0]
    add_skill_vector(vec, new_skill)
    skills.append(new_skill)

    print(f"\n  New skill saved: {new_skill['name']}")

    # notify tool generator of the new skill
    actual_needs_input = "sys.argv" in new_skill.get("code", "")
    on_skill_created(
        agent_instance=None,
        skill_name=new_skill['name'],
        description=new_skill.get('description', ''),
        tags=new_skill.get('tags', []),
        needs_input=actual_needs_input,
    )

    # Test run — only delete if skill code itself is broken, not for bad input
    result, success, is_broken = _run_with_validation(
        resolve_script_path(new_skill),
        skill_input if skill_input else step
    )
    if not success and is_broken:
        print(f"  [warn] Skill '{new_skill['name']}' failed test run — removing.")
        _delete_skill(new_skill)
    elif not success:
        print(f"  [warn] Skill '{new_skill['name']}' saved but input was missing/invalid.")
    return result


def _delete_skill(skill: dict):
    """
    Remove a broken skill from disk, in-memory skills list, and FAISS index.
    FAISS doesn't support single-entry deletion, so we rebuild the index
    from the remaining in-memory skills list.
    """
    global skills

    # 1. Remove from disk
    folder = skill["name"].replace(" ", "_")
    skill_path = os.path.join(SKILLS_DIR, folder)
    shutil.rmtree(skill_path, ignore_errors=True)
    print(f"  [cleanup] Deleted skill folder: {skill_path}")

    # 2. Remove from in-memory list
    skills = [s for s in skills if s["name"] != skill["name"]]

    # 3. Rebuild FAISS index without this skill
    _rebuild_faiss_index()


def _rebuild_faiss_index():
    """Rebuild the FAISS index from current in-memory skills list."""
    from skill_engine.vector_memory import index, VECTOR_INDEX_PATH, VECTOR_META_PATH
    import faiss as faiss_module
    from config import EMBEDDING_DIMENSION

    # Reset index
    new_index = faiss_module.IndexFlatIP(EMBEDDING_DIMENSION)

    new_metadata = []
    for s in skills:
        vec = embedder.encode([_build_embed_text(s)])[0]
        from skill_engine.vector_memory import _normalize
        import numpy as np
        vec_norm = _normalize(np.array([vec], dtype="float32"))
        new_index.add(vec_norm)
        new_metadata.append(s)

    # Replace module-level index contents
    index.reset()
    if new_index.ntotal > 0:
        index.add_with_ids if hasattr(index, 'add_with_ids') else None
        # Reconstruct by re-adding all vectors
        for i in range(new_index.ntotal):
            vec = new_index.reconstruct(i).reshape(1, -1)
            index.add(vec)

    # Save updated index and metadata
    faiss_module.write_index(index, VECTOR_INDEX_PATH)
    import json
    json.dump(new_metadata, open(VECTOR_META_PATH, "w"), indent=2)
    print(f"  [cleanup] FAISS index rebuilt with {index.ntotal} skills.")


while True:

    task = input("\nAsk the agent: ").strip()

    if not task:
        continue


    # ----------------------------------
    # 0️⃣ Intent classification
    #    Filter out conversational inputs
    #    before any skill logic runs
    # ----------------------------------

    intent = classify_intent(task)

    if intent == "conversational":
        response = handle_conversational(task)
        print(f"\nAgent: {response}")
        continue


    # ----------------------------------
    # 0.5 "Create a skill" shortcut
    #    User explicitly asks to create/build a skill.
    #    Skip planner and selector — go straight to generation.
    # ----------------------------------

    if re.match(r"^(create|make|build|write|add|generate)\s+(a\s+)?(new\s+)?skill\b", task.lower()):
        print("  Skill creation request — generating directly...")
        result = execute_or_create_skill(task, task)
        print("Result:", result)
        continue

    # ----------------------------------
    # 1️⃣ Try direct skill match
    # ----------------------------------

    skill, score = select_skill(task, skills)

    if skill and score >= SKILL_MATCH_THRESHOLD:
        print(f"\nUsing existing skill: {skill['name']} (score: {score:.2f})")
        needs_input = _needs_input(task, skill)  # check skill code directly
        if needs_input:
            skill_input = extract_skill_input(task, task)
            if not skill_input:
                skill_input = task
        else:
            skill_input = ""  # self-contained — no input needed
        result, success, is_broken = _run_with_validation(resolve_script_path(skill), skill_input)
        if not success and is_broken:
            print(f"  [warn] Skill '{skill['name']}' is broken — removing.")
            _delete_skill(skill)
            result = "Skill was broken and has been removed. Please try again."
        print("Result:", result)
        continue


    # ----------------------------------
    # 2️⃣ Complexity gate — skip planner
    #    for simple single-action tasks
    # ----------------------------------

    if is_simple_task(task):
        print("\nSimple task detected. Skipping planner...")
        result = execute_or_create_skill(task, task)
        print("Result:", result)
        continue


    # ----------------------------------
    # 3️⃣ Plan complex multi-step tasks
    # ----------------------------------

    print("\nNo direct skill found. Planning task...")
    steps = plan(llm, task, skills)

    print("\nPlan:")
    for s in steps:
        print(" -", s)


    # ----------------------------------
    # 4️⃣ Execute each step
    #    Pass original task for context
    # ----------------------------------

    for step in steps:
        print(f"\nExecuting step: {step}")
        result = execute_or_create_skill(step, task)  # ← original task passed here
        print("Result:", result)