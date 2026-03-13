import os
from langchain_mistralai.chat_models import ChatMistralAI

SKILLS_FOLDER = "skills"


def load_skills():
    skills_text = ""

    for root, dirs, files in os.walk(SKILLS_FOLDER):
        for file in files:
            if file == "SKILL.md":
                with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                    skills_text += f.read() + "\n\n"

    return skills_text

skills = load_skills()

print("====== LOADED SKILLS ======")
print(skills[:1000])  # show first 1000 characters
print("====== END SKILLS ======")

llm = ChatMistralAI(
    api_key="66MKOsl3IH9hJxff8DedaimdImXCZiiq",
    model="mistral-small-latest"
)

while True:
    task = input("\nAsk the agent: ")

    prompt = f"""
You are an AI agent.

Available Skills:
{skills}

User Request:
{task}

Follow the skill instructions if applicable.
"""

    response = llm.invoke(prompt)

    print("\nAgent:\n", response.content)