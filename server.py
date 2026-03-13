"""
AgentGeneral FastAPI Server
===========================
Runs the AgentGeneral pipeline as an HTTP API WITHOUT importing agent.py
(which has a blocking while True loop at module level).

Instead, we import the individual engine modules directly and replicate
the exact same logic from agent.py's main loop here.

Run with:
    python -m uvicorn server:app --host 0.0.0.0 --port 8765 --reload
"""

import os
import re
import sys
import shutil
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── AgentGeneral engine imports (safe — none of these have blocking loops) ──
from sentence_transformers import SentenceTransformer
from langchain_ollama import ChatOllama

from skill_engine.loader import load_skills
from skill_engine.selector import select_skill
from skill_engine.runner import run_skill
from skill_engine.vector_memory import add_skill_vector, index
from skill_engine.duplicate_filter import is_duplicate

from skillfolder import create_skill
from parse import parse_skill
from planner.planner import plan, is_simple_task
from tool_generator import on_skill_created
from config import SKILL_MATCH_THRESHOLD, SKILLS_DIR, EMBEDDING_MODEL, EMBEDDING_DIMENSION

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="AgentGeneral API",
    description="Skill-based autonomous agent exposed as HTTP API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Models & skills (initialised once at startup) ────────────────────────────
embedder = SentenceTransformer(EMBEDDING_MODEL)

llm = ChatOllama(
    model="mistral:7b",
    base_url="http://172.16.10.11:11435",
    temperature=0.1,
)

skills = load_skills()
logger.info(f"Loaded {len(skills)} skills.")

# Embed all skills into FAISS at startup if index is empty
def _build_embed_text(skill: dict) -> str:
    name_words = re.sub(r"([A-Z])", r" \1", skill.get("name", "")).lower().strip()
    parts = [
        skill.get("name", ""),
        skill.get("description", ""),
        " ".join(skill.get("tags", [])),
        name_words,
    ]
    return " ".join(p for p in parts if p).strip()


if index.ntotal == 0 and skills:
    logger.info("FAISS index empty — embedding loaded skills...")
    for s in skills:
        vec = embedder.encode([_build_embed_text(s)])[0]
        add_skill_vector(vec, s)
    logger.info(f"Embedded {len(skills)} skills into FAISS.")


# ── Agent logic (copied from agent.py, no blocking input() calls) ────────────

def resolve_script_path(skill):
    script = skill["script"]
    if os.path.exists(script):
        return script
    folder = skill["name"].replace(" ", "_")
    return os.path.join(SKILLS_DIR, folder, "scripts", script)


_SKILL_BROKEN_PATTERNS = [
    "Traceback (most recent call last)", "TypeError", "AttributeError",
    "NameError", "SyntaxError", "IndentationError", "ImportError",
    "ModuleNotFoundError", "IndexError", "KeyError", "ZeroDivisionError",
]

_INPUT_ERROR_PATTERNS = [
    "FileNotFoundError", "No such file or directory", "File '", 'File "',
    "does not exist", "not found", "Usage:", "usage:", "HTTPError",
    "ConnectionError", "TimeoutError",
]


def _run_with_validation(script_path: str, skill_input: str) -> tuple:
    result = run_skill(script_path, skill_input)
    for pattern in _INPUT_ERROR_PATTERNS:
        if pattern in result:
            return result, False, False
    for pattern in _SKILL_BROKEN_PATTERNS:
        if pattern in result:
            return result, False, True
    if not result.strip():
        return result, False, True
    return result, True, False


def _needs_input(task: str, skill: dict = None) -> bool:
    if skill:
        if skill.get("code"):
            return "sys.argv" in skill["code"]
        script_path = skill.get("script", "")
        if script_path and os.path.exists(script_path):
            try:
                with open(script_path, "r", encoding="utf-8") as f:
                    return "sys.argv" in f.read()
            except Exception:
                pass
        return False

    input_indicators = [
        r"\bin\b.{0,30}\.(txt|csv|json|pdf|xlsx|py)\b",
        r"\bof\s+\d+\b",
        r"\bconvert\b",
        r"\btranslate\b",
        r"\bcount\b.{0,20}\bin\b",
        r"\bextract\b",
        r"\bparse\b",
        r"\bfrom\b.{0,30}\bfile\b",
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
    file_match = re.search(r"\b([\w\-]+\.(txt|csv|json|pdf|xlsx|py|md|log))\b", original_task, re.I)
    if file_match:
        return file_match.group(1)

    quoted_match = re.search(r'["\'](.+?)["\']', original_task)
    if quoted_match:
        return quoted_match.group(1)

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

    prompt = f"""You are a parameter extractor for an AI agent.
Extract ONLY the key input value the step's script should receive as sys.argv[1].
Return ONLY the value — no explanation. If no input needed, return: NONE

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


def _delete_skill(skill: dict):
    global skills
    folder = skill["name"].replace(" ", "_")
    skill_path = os.path.join(SKILLS_DIR, folder)
    shutil.rmtree(skill_path, ignore_errors=True)
    skills = [s for s in skills if s["name"] != skill["name"]]
    _rebuild_faiss_index()


def _rebuild_faiss_index():
    from skill_engine.vector_memory import index, VECTOR_INDEX_PATH, VECTOR_META_PATH
    import faiss as faiss_module
    import numpy as np
    from skill_engine.vector_memory import _normalize
    import json

    new_index = faiss_module.IndexFlatIP(EMBEDDING_DIMENSION)
    new_metadata = []
    for s in skills:
        vec = embedder.encode([_build_embed_text(s)])[0]
        vec_norm = _normalize(np.array([vec], dtype="float32"))
        new_index.add(vec_norm)
        new_metadata.append(s)

    index.reset()
    for i in range(new_index.ntotal):
        vec = new_index.reconstruct(i).reshape(1, -1)
        index.add(vec)

    faiss_module.write_index(index, VECTOR_INDEX_PATH)
    json.dump(new_metadata, open(VECTOR_META_PATH, "w"), indent=2)
    logger.info(f"FAISS index rebuilt with {index.ntotal} skills.")


_PLACE_NAMES = [
    "australia", "kenya", "japan", "france", "germany", "india", "china",
    "usa", "uk", "brazil", "canada", "mexico", "italy", "spain", "thailand",
    "indonesia", "nigeria", "egypt", "peru", "argentina", "colombia", "chile",
    "vietnam", "malaysia", "singapore", "nairobi", "sydney", "melbourne",
    "tokyo", "paris", "london", "berlin", "dubai", "cairo", "toronto", "miami",
    "amsterdam", "barcelona", "rome", "madrid", "lisbon", "zurich", "stockholm", "oslo",
]


# ── Pre-save health-check helpers ────────────────────────────────────────────
# IMPORTANT: temp files are written to the OS temp directory (tempfile.gettempdir()),
# NOT inside the project folder. This prevents uvicorn --reload from detecting the
# file change and restarting the server mid-job, which would kill the async job thread.

import tempfile as _tempfile

def _write_temp_skill(skill: dict) -> str:
    """Write skill code to OS temp directory for pre-save testing."""
    try:
        # NamedTemporaryFile with delete=False so we can run it as a script.
        # suffix=.py so Python can execute it. dir=None = system temp folder.
        tmp = _tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", prefix="agentgeneral_healthcheck_",
            delete=False, encoding="utf-8"
        )
        tmp.write(skill.get("code", ""))
        tmp.close()
        return tmp.name
    except Exception as e:
        logger.warning(f"Could not write temp skill file: {e}")
        return ""


def _cleanup_temp_skill(temp_path: str):
    """Delete the temp file after health-check."""
    if temp_path and os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except Exception:
            pass


# Patterns that indicate a skill printed placeholder text instead of real output
_PLACEHOLDER_PATTERNS = [
    r"\[[A-Za-z_][A-Za-z0-9_ ]*\]",   # [variable_name], [result], [destination]
    r"<[A-Za-z_][A-Za-z0-9_ ]*>",      # <value>, <input>
    r"Usage:\s",                         # Usage: python script.py
    r"usage:\s",
    r"Example:\s",
]

def _has_placeholder_output(text: str) -> bool:
    """Return True if the skill output contains placeholder or usage text."""
    for pattern in _PLACEHOLDER_PATTERNS:
        if re.search(pattern, text, re.MULTILINE):
            return True
    return False


# Stateful container so execute_or_create_skill can report back to the API
class _RunContext:
    skill_used: Optional[str] = None
    new_tool_generated: bool = False
    new_tool_class_name: Optional[str] = None


def execute_or_create_skill(step: str, original_task: str, ctx: _RunContext) -> str:
    global skills

    skill, score = select_skill(step, skills)

    if skill and score >= SKILL_MATCH_THRESHOLD:
        logger.info(f"Using skill: {skill['name']} (score: {score:.2f})")
        ctx.skill_used = skill["name"]
        needs_input = _needs_input(step, skill)
        skill_input = extract_skill_input(step, original_task) if needs_input else ""
        if needs_input and not skill_input:
            skill_input = step

        result, success, is_broken = _run_with_validation(resolve_script_path(skill), skill_input)
        if success:
            return result
        if is_broken:
            logger.warning(f"Skill '{skill['name']}' broken — removing and regenerating.")
            _delete_skill(skill)
        else:
            logger.warning(f"Skill '{skill['name']}' got bad input — falling through to generation.")

    # ── No match or broken — generate new skill ──────────────────────────────
    logger.info("No skill found. Generating new skill...")
    ctx.skill_used = None

    needs_input = _needs_input(step)
    if needs_input:
        skill_input = extract_skill_input(step, original_task)
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
                f"4. If sys.argv[1] is not provided, use a sensible default value — NEVER print a usage/help message\n"
                f"5. Design the skill to be GENERIC and REUSABLE — not hardcoded to '{skill_input}' specifically"
            )
    else:
        skill_input = None
        input_rule = (
            "2. This skill is SELF-CONTAINED — it does NOT need any user input\n"
            "3. Do NOT use sys.argv at all\n"
            "4. Always print a complete, real result — never print placeholder text like [result] or [value]"
        )

    prompt = f"""You are an AI agent that creates reusable Python skills for a chatbot.
The skill output is fed DIRECTLY to a language model to form a natural chat reply.

Task this skill must handle:
{step}

Rules:
1. The skill must directly solve the task
{input_rule}
6. Script must print a complete, real, human-readable result — not a placeholder
7. Script must be a full executable Python file
8. Always import every module you use at the top of the script
9. Use ONLY the Python standard library — NO network access of any kind: no requests, no urllib, no socket
10. Write the SIMPLEST possible solution — plain for loops, no unnecessary data structures
11. For math use simple arithmetic (+, -, *, /) directly — never use operator or functools modules
12. Every variable must be defined before use

OUTPUT QUALITY RULES — these are critical:
- NEVER print placeholder text like [result], [value], [destination], [number], or any [bracketed] text
- NEVER print "Usage:", "usage:", "Example:", or any help/instructions text
- NEVER print Python tracebacks or error messages as normal output
- Output must be clean prose or structured text a language model can summarise naturally
- If the task asks to "generate", "create", or "produce" something — actually produce it with realistic content
- If the skill uses sys.argv[1] and no value is provided, use a built-in default value and run normally

REUSABILITY RULES:
- NEVER hardcode a specific country, city, person, or topic name in the data
- The input value (sys.argv[1]) IS the subject — use it throughout the output
- SKILL_NAME must be GENERIC — no location or specific topic in the name
  GOOD: FindAttractions, WeeklyMealPlanner, WorkoutRoutineGenerator
  BAD:  FindAttractionsInAustralia, KenyaMealPlan

FORMAT RULES — follow exactly:
- No markdown, no bold, no asterisks, no hashes anywhere
- Field names at the start of a line as shown below

SKILL_NAME: <generic name>
DESCRIPTION: <one sentence, generic, describes what the skill does for any input>
TAGS: <comma separated keywords>
SCRIPT_NAME: <generic_filename.py>

```python
<full executable python script>
```
"""

    try:
        response = llm.invoke(prompt)
        text = response.content
        new_skill = parse_skill(text)
        if not new_skill:
            return "Failed to parse skill."

        # Bloat guard — strip location names from skill names
        # Also handles adjectival forms: Japanese→japan+ese, Australian→australia+n
        # and prepositions: FindHotelsInAustralia → FindHotels
        skill_name_lower = new_skill.get("name", "").lower().replace(" ", "").replace("_", "")

        # Build extended place list including adjectival forms
        _PLACE_ADJECTIVE_MAP = {
            "japan": ["japanese", "japan"],
            "australia": ["australian", "australia"],
            "france": ["french", "france"],
            "germany": ["german", "germany"],
            "spain": ["spanish", "spain"],
            "italy": ["italian", "italy"],
            "china": ["chinese", "china"],
            "india": ["indian", "india"],
            "brazil": ["brazilian", "brazil"],
            "kenya": ["kenyan", "kenya"],
            "mexico": ["mexican", "mexico"],
            "thailand": ["thai", "thailand"],
        }
        _extended_place_forms = {}
        for base, forms in _PLACE_ADJECTIVE_MAP.items():
            for f in forms:
                _extended_place_forms[f] = base
        for p in _PLACE_NAMES:
            if p not in _extended_place_forms:
                _extended_place_forms[p] = p

        matched_place = None
        for place_form, base_place in _extended_place_forms.items():
            if place_form in skill_name_lower:
                matched_place = place_form
                break

        if matched_place:
            # Remove the place form (and optional preceding In/For/At/Of) from the name
            generic_name = re.sub(
                r"(?i)(in|for|at|of|from)?\s*" + matched_place,
                "", new_skill["name"], flags=re.IGNORECASE
            ).strip(" _-")
            # Clean up residual lowercase fragments at start: "eseBeginnersGuide" → "BeginnersGuide"
            generic_name = re.sub(r"^[a-z]+(?=[A-Z])", "", generic_name).strip(" _-")
            if not generic_name or len(generic_name) < 4:
                generic_name = re.sub(r"(?i)(japanese|australian|french|german|spanish|"
                                      r"italian|chinese|indian|brazilian|kenyan|mexican|thai)",
                                      "", new_skill["name"]).strip(" _-")
            if not generic_name or len(generic_name) < 4:
                generic_name = new_skill["name"].split("In")[0].split("For")[0].strip()
            new_skill["name"] = generic_name if generic_name else new_skill["name"]
            logger.info(f"[bloat guard] Renamed '{new_skill['name']}' (matched: {matched_place})")

        duplicate, existing_name = is_duplicate(new_skill, skills)
        if duplicate:
            # Don't return the duplicate message as a chatbot reply.
            # Instead find the existing skill and run it directly.
            logger.info(f"Duplicate detected — running existing skill: {existing_name}")
            existing_skill = next((s for s in skills if s["name"] == existing_name), None)
            if existing_skill:
                ctx.skill_used = existing_skill["name"]
                existing_needs_input = _needs_input(step, existing_skill)
                existing_input = extract_skill_input(step, original_task) if existing_needs_input else ""
                if existing_needs_input and not existing_input:
                    existing_input = ""  # let default kick in — don't pass garbage
                ex_result, ex_success, _ = _run_with_validation(
                    resolve_script_path(existing_skill), existing_input
                )
                if ex_success:
                    return ex_result
                # Existing skill also failed — fall through to save the regenerated one
                logger.warning(f"Existing skill '{existing_name}' also failed — saving regenerated version.")
            else:
                logger.warning(f"Duplicate detected but existing skill not found in memory — saving regenerated version.")

        # ── Health-check before saving ──────────────────────────────────────
        # Test-run the new skill now, BEFORE persisting it.
        # This catches: placeholder output, usage messages, empty output, crashes.
        pre_save_input = skill_input if skill_input else ""
        temp_path = _write_temp_skill(new_skill)
        if not temp_path:
            logger.warning("Could not create temp file for health-check — skipping check.")
            pre_success, pre_broken, pre_result = True, False, ""
        else:
            pre_result, pre_success, pre_broken = _run_with_validation(temp_path, pre_save_input)

        if not pre_success:
            if pre_broken:
                logger.warning(f"Pre-save health-check failed (broken code) — discarding skill.")
                _cleanup_temp_skill(new_skill)
                return "Could not generate a working skill for this task."
            else:
                logger.warning(f"Pre-save health-check: bad input result — saving skill anyway.")

        # Check for placeholder text in output — discard if found
        if pre_success and _has_placeholder_output(pre_result):
            logger.warning(f"Pre-save health-check: placeholder output detected — discarding.")
            _cleanup_temp_skill(temp_path)
            return "Could not generate a valid skill output for this task."

        _cleanup_temp_skill(new_skill)

        # ── Persist the skill ───────────────────────────────────────────────
        create_skill(new_skill)
        vec = embedder.encode([_build_embed_text(new_skill)])[0]
        add_skill_vector(vec, new_skill)
        skills.append(new_skill)
        logger.info(f"New skill saved: {new_skill['name']}")

        # Notify tool generator — needs_input from generated code, not task text
        actual_needs_input = "sys.argv" in new_skill.get("code", "")
        tool_result = on_skill_created(
            agent_instance=ctx,
            skill_name=new_skill["name"],
            description=new_skill.get("description", ""),
            tags=new_skill.get("tags", []),
            needs_input=actual_needs_input,
        )
        if tool_result and tool_result.get("success"):
            ctx.new_tool_generated = True
            ctx.new_tool_class_name = tool_result.get("class_name")

        # Final run with real input
        result, success, is_broken = _run_with_validation(
            resolve_script_path(new_skill),
            skill_input if skill_input else ""
        )
        if not success and is_broken:
            logger.warning(f"Skill '{new_skill['name']}' failed post-save test — removing.")
            _delete_skill(new_skill)
            return "The generated skill failed to produce output."
        return result

    except Exception as e:
        logger.error(f"Skill generation error: {e}")
        return f"Error generating skill: {str(e)}"


def run_task(task: str) -> dict:
    """Main task runner — mirrors agent.py's while True loop logic."""
    ctx = _RunContext()

    # Direct skill match
    skill, score = select_skill(task, skills)
    if skill and score >= SKILL_MATCH_THRESHOLD:
        logger.info(f"Direct skill match: {skill['name']} (score: {score:.2f})")
        ctx.skill_used = skill["name"]
        needs_input = _needs_input(task, skill)
        skill_input = extract_skill_input(task, task) if needs_input else ""
        if needs_input and not skill_input:
            skill_input = task

        result, success, is_broken = _run_with_validation(resolve_script_path(skill), skill_input)
        if success:
            return {"result": result, "skill_used": ctx.skill_used,
                    "new_tool_generated": False, "new_tool_class_name": None}
        if is_broken:
            logger.warning(f"Skill '{skill['name']}' broken — removing.")
            _delete_skill(skill)

    # Simple task — skip planner
    if is_simple_task(task):
        logger.info("Simple task — skipping planner.")
        result = execute_or_create_skill(task, task, ctx)
        return {"result": result, "skill_used": ctx.skill_used,
                "new_tool_generated": ctx.new_tool_generated,
                "new_tool_class_name": ctx.new_tool_class_name}

    # Complex task — plan then execute
    logger.info("Complex task — planning...")
    steps = plan(llm, task, skills)
    logger.info(f"Plan: {steps}")

    results = []
    for step in steps:
        logger.info(f"Executing step: {step}")
        step_result = execute_or_create_skill(step, task, ctx)
        results.append(step_result)

    combined = "\n".join(r for r in results if r)
    return {
        "result": combined,
        "skill_used": ctx.skill_used,
        "new_tool_generated": ctx.new_tool_generated,
        "new_tool_class_name": ctx.new_tool_class_name,
    }


# ── API endpoints ─────────────────────────────────────────────────────────────
# Laravel timeout notes:
#   /run        — synchronous, blocks until complete. Raise Laravel HTTP timeout to 120s.
#   /run/async  — returns a job_id immediately; poll /run/status/{job_id} for result.
#                 Use this for complex multi-step tasks to avoid cURL timeout 28.

import threading
import uuid
import time

_jobs: dict = {}  # job_id → {"status": "pending"|"done"|"error", "result": dict}


class RunRequest(BaseModel):
    task: str


class RunResponse(BaseModel):
    result: str
    skill_used: Optional[str] = None
    new_tool_generated: bool = False
    new_tool_class_name: Optional[str] = None
    error: Optional[str] = None


class AsyncRunResponse(BaseModel):
    job_id: str
    status: str = "pending"
    message: str = "Task accepted. Poll /run/status/{job_id} for result."


class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # pending | done | error
    result: Optional[RunResponse] = None


@app.get("/health")
def health():
    return {
        "status": "ok",
        "agent": "AgentGeneral",
        "skills_loaded": len(skills),
        "faiss_vectors": index.ntotal,
    }


@app.get("/skills")
def list_skills():
    """List all loaded skills — useful for debugging FAISS state."""
    return {
        "count": len(skills),
        "skills": [{"name": s["name"], "description": s.get("description", "")} for s in skills]
    }


@app.post("/run", response_model=RunResponse)
def run(request: RunRequest):
    """
    Synchronous endpoint. Blocks until complete.
    Raise your Laravel HTTP client timeout to 120s for complex tasks:
      Http::timeout(120)->post(...)
    """
    task = request.task.strip()
    if not task:
        raise HTTPException(status_code=400, detail="task cannot be empty")

    logger.info(f"Task received: {task}")
    try:
        result = run_task(task)
        return RunResponse(**result)
    except Exception as e:
        logger.error(f"Run error: {e}")
        return RunResponse(result="An error occurred.", error=str(e))


@app.post("/run/async", response_model=AsyncRunResponse)
def run_async(request: RunRequest):
    """
    Async endpoint — returns a job_id immediately (< 10ms).
    Use this for complex tasks to avoid Laravel cURL timeout 28.

    Laravel usage:
      $resp = Http::post('/run/async', ['task' => $task]);
      $jobId = $resp['job_id'];
      // Poll every 2s:
      $status = Http::get("/run/status/{$jobId}");
    """
    task = request.task.strip()
    if not task:
        raise HTTPException(status_code=400, detail="task cannot be empty")

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "pending", "result": None}

    def _worker():
        try:
            result = run_task(task)
            _jobs[job_id] = {"status": "done", "result": result}
        except Exception as e:
            logger.error(f"Async job {job_id} error: {e}")
            _jobs[job_id] = {
                "status": "error",
                "result": {"result": f"Error: {str(e)}", "skill_used": None,
                           "new_tool_generated": False, "new_tool_class_name": None}
            }

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    logger.info(f"Async job {job_id} started for task: {task}")

    return AsyncRunResponse(job_id=job_id)


@app.get("/run/status/{job_id}", response_model=JobStatusResponse)
def run_status(job_id: str):
    """Poll for async job result."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job = _jobs[job_id]
    if job["status"] == "done":
        # Clean up after retrieval to prevent memory leak
        result_data = _jobs.pop(job_id)
        return JobStatusResponse(
            job_id=job_id,
            status="done",
            result=RunResponse(**result_data["result"])
        )
    if job["status"] == "error":
        result_data = _jobs.pop(job_id)
        return JobStatusResponse(
            job_id=job_id,
            status="error",
            result=RunResponse(**result_data["result"])
        )
    return JobStatusResponse(job_id=job_id, status="pending")