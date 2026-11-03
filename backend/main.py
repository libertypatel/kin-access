import json
import os
from pathlib import Path
from fastapi.responses import FileResponse

from dotenv import load_dotenv
from fastapi import FastAPI
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()

client = OpenAI(
    base_url="https://api.meta.ai/v1",
    api_key=os.environ["MODEL_API_KEY"],
    timeout=20,
    max_retries=1,
)

MODEL = "muse-spark-1.1"

app = FastAPI(title="KIN Access")


# ---------- Data shapes ----------

class ScreenElement(BaseModel):
    id: str            # e.g. "open_email_mom"
    label: str         # e.g. "Open email from Mom"
    risky: bool = False  # send/delete/buy need confirmation


class ScreenState(BaseModel):
    screen: str                 # e.g. "inbox"
    description: str            # what the user is looking at
    elements: list[ScreenElement]
    recent_actions: list[str] = []


class Suggestion(BaseModel):
    element_id: str
    label: str
    risky: bool


class SuggestResponse(BaseModel):
    suggestions: list[Suggestion]
    rejected_count: int   # how many AI picks failed validation
    used_fallback: bool   # True if the AI call failed


# ---------- What we ask the model for ----------

RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "next_actions",
        "schema": {
            "type": "object",
            "properties": {
                "suggestions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "element_id": {"type": "string"},
                            "reason": {"type": "string"},
                        },
                        "required": ["element_id", "reason"],
                    },
                }
            },
            "required": ["suggestions"],
        },
    },
}

SYSTEM_PROMPT = """You help a person with a severe motor disability use a computer
with a single switch. Each press costs them real effort, so your job is to predict
the 4 actions they most likely want next, most likely first.
When there are several possible replies or messages, include each of them so the
user can choose. Favor actions that move the current task forward over general
navigation or settings.
Only choose element_id values from the provided list. Never invent new ones."""

# ---------- Safety: validate the AI's choices ----------

def validate_suggestions(raw_ids: list[str], screen: ScreenState) -> tuple[list[Suggestion], int]:
    """Keep only real, unique elements. Labels and risk come from OUR data, not the AI."""
    allowed = {el.id: el for el in screen.elements}
    valid: list[Suggestion] = []
    rejected = 0

    for element_id in raw_ids:
        if element_id not in allowed or any(s.element_id == element_id for s in valid):
            rejected += 1
            continue
        el = allowed[element_id]
        valid.append(Suggestion(element_id=el.id, label=el.label, risky=el.risky))
        if len(valid) == 4:
            break

    return valid, rejected


def fallback_suggestions(screen: ScreenState) -> list[Suggestion]:
    """If the AI fails, offer the first 4 elements so the user is never stuck."""
    return [Suggestion(element_id=el.id, label=el.label, risky=el.risky)
            for el in screen.elements[:4]]


# ---------- The endpoint ----------

@app.post("/suggest", response_model=SuggestResponse)
def suggest(screen: ScreenState) -> SuggestResponse:
    element_list = "\n".join(f"- {el.id}: {el.label}" for el in screen.elements)
    user_message = (
        f"Screen: {screen.screen}\n"
        f"What the user sees: {screen.description}\n"
        f"Recent actions: {', '.join(screen.recent_actions) or 'none'}\n"
        f"Available elements:\n{element_list}"
    )

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            response_format=RESPONSE_SCHEMA,
        )
        data = json.loads(response.choices[0].message.content)
        raw_ids = [s["element_id"] for s in data.get("suggestions", [])]
    except Exception as error:
        print(f"AI call failed: {error}")
        return SuggestResponse(
            suggestions=fallback_suggestions(screen),
            rejected_count=0,
            used_fallback=True,
        )

    valid, rejected = validate_suggestions(raw_ids, screen)
    return SuggestResponse(suggestions=valid, rejected_count=rejected, used_fallback=False)

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html")