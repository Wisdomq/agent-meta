import re


# Tasks matching these patterns are simple enough to skip planning entirely
_SIMPLE_PATTERNS = [
    r"^(create|make|build|write|add|generate)\s+(a\s+)?(new\s+)?skill\b",  # always simple — direct creation
    r"^what (is|are|was|were) the (time|date|day|month|year|current)\b",
    r"^what (is|are) (today|the current|the)\b.*(time|date|day)\b",
    r"^(get|show|print|display) (the )?(current )?(time|date|day)\b",
    r"^(what is the |whats the )?(current )?(date and time|time and date|date|time|day)\b",
    r"^(calculate|compute) .{0,30} of \d+\b",
    r"^convert \S+ to \S+\b",
    r"^count (lines|words|chars) in \S+\b",
    r"^translate \b",
    r"^format \b",
]

# Tasks with these patterns are complex — always send to planner
_COMPLEX_KEYWORDS = [
    r"\b(restaurants?|hotels?|flights?|attractions?|places?|activities)\b",
    r"\b(plan|schedule|itinerary|trip|travel|visit|tour)\b",
    r"\b(top|best|recommend)\b.{0,30}\b(in|for|near|around)\b",
    r"\b(compare|analyze|summarize|report|generate)\b",
]


def is_simple_task(task: str) -> bool:
    """
    Returns True only if the task is genuinely simple and single-step.
    Conservative — when in doubt, sends to planner.
    """
    task_lower = task.lower().strip()

    # Explicitly complex — never skip planner
    for pattern in _COMPLEX_KEYWORDS:
        if re.search(pattern, task_lower):
            return False

    # Very short (5 words or fewer) — almost always single step
    if len(task_lower.split()) <= 5:
        return True

    # Known simple patterns
    for pattern in _SIMPLE_PATTERNS:
        if re.search(pattern, task_lower):
            return True

    return False


def plan(llm, task, skills=None):

    skill_context = ""
    if skills:
        skill_lines = "\n".join(
            f"- {s['name']}: {s.get('description', '')}" for s in skills
        )
        skill_context = f"""AVAILABLE SKILLS (reuse these where possible — phrase steps to match skill names):
{skill_lines}

"""

    prompt = f"""You are a task planner for an autonomous AI agent.

Break the user request into the MINIMUM number of executable steps.

{skill_context}STRICT RULES:

1. RULE ZERO — If the task can be done in ONE step, return ONE step only
2. Each step must be a SINGLE clear action
3. Steps must be GENERIC and REUSABLE — do NOT include specific numbers, durations,
   or quantities in the step description. The agent will extract those from context.
4. Do NOT include steps like "close the application" or "close the interface"
5. Do NOT reference skill names in steps
6. Do NOT number steps
7. Do NOT add explanations
8. Maximum 3 steps
9. Plain text only, one step per line

GOOD examples:

Request: Plan a 7 day trip to Kenya
Output:
Find top attractions in Kenya
Find hotels in Kenya
Create an itinerary for Kenya

Request: Plan a 3 day trip to Tokyo
Output:
Find top attractions in Tokyo
Find hotels in Tokyo
Create an itinerary for Tokyo

Request: count lines in test.txt
Output:
Count lines in test.txt

BAD examples (never do this):
- Find hotels in Kenya for 7 days   <- don't include duration
- Find a 3-day itinerary            <- don't include day count in step
- Create a 7-day itinerary for Kenya  <- too specific
- Initialize a counter variable     <- implementation detail
- Close the command line interface  <- cleanup step

User request:
{task}

Output:
"""

    response = llm.invoke(prompt)
    text = response.content.strip()

    bad_patterns = [
        r"\bclose\b.{0,30}\b(interface|application|browser|webpage|cli|terminal)\b",
        r"\b(initialize|instantiate|import|loop|iterate|return|define)\b",
        r"\bfor\s+\d+\s*(day|week|hour|night)s?\b",   # strips "for 7 days" steps
        r"\b\d+[\s-]day\b",                            # strips "3-day itinerary" steps
        r"\b(save|store|write|export)\b.{0,30}\b(result|output|data|file)s?\b",  # no storage steps
        r"\b(review|later|afterward|next time)\b",       # no deferred action steps
        r"^(test|validate|verify|check|assert)\b",        # meta-programming steps the agent can't fulfil
        r"^(implement|define|declare|instantiate)\b",     # programming instructions not skill steps
    ]

    steps = []
    for line in text.split("\n"):
        line = line.strip("- ").strip()
        if not line:
            continue
        # Strip leading numbers e.g. "2. Step text" or "3) Step text"
        line = re.sub(r"^\d+[\.)\s]\s*", "", line).strip()
        # Clean duration phrases and parenthetical metadata
        line = re.sub(r"\s+for\s+\d+\s*(day|week|night|hour)s?\b", "", line, flags=re.I).strip()
        line = re.sub(r"\b\d+[\s-](day|week|night|hour)s?\b", "", line, flags=re.I).strip()
        line = re.sub(r"\s*\(.*?\)\s*$", "", line).strip()
        # Strip specific location names from step text so steps stay generic.
        # The destination will be passed as sys.argv[1] at execution time —
        # it must NOT be baked into the step string (causes skill bloat).
        # e.g. "Find hotels in Australia" → "Find hotels for destination"
        _PLACE_RE = re.compile(
            r"\b(in|for|at|near|to|around)\s+(australia|kenya|japan|france|germany|india|"
            r"china|usa|uk|brazil|canada|mexico|italy|spain|thailand|indonesia|nigeria|egypt|"
            r"peru|argentina|colombia|chile|vietnam|malaysia|singapore|nairobi|sydney|"
            r"melbourne|tokyo|paris|london|berlin|dubai|cairo|toronto|miami|amsterdam|"
            r"barcelona|rome|madrid|lisbon|new\s+york|los\s+angeles|chicago)\b",
            re.IGNORECASE
        )
        if _PLACE_RE.search(line):
            line = _PLACE_RE.sub(r"\1 destination", line).strip()
        # Skip steps that are too short to be meaningful (single words, conjunctions)
        if len(line.split()) < 3:
            continue

        skip = False
        for pat in bad_patterns:
            if re.search(pat, line.lower()):
                skip = True
                break
        if not skip and line:
            steps.append(line)

    return steps[:3]