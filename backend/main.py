import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()

client = OpenAI(
    base_url="https://api.meta.ai/v1",
    api_key=os.environ["MODEL_API_KEY"],
    timeout=20,
    max_retries=1,
)

# Text mode: the fastest model in my benchmark (3.6s vs 9.4s for 1.3).
MODEL = "muse-spark-1.1"

# Vision mode: models to try for screenshot input, in order. The first one that
# answers is remembered. If a model accepts images but describes the screen wrongly
# in the "Ask Muse Spark what it sees" test, remove it from this list.
VISION_MODELS = ["muse-spark-1.1", "muse-spark-1.3"]
working_vision_model: Optional[str] = None

app = FastAPI(title="KIN Access")


# ---------- Data shapes ----------

class ScreenElement(BaseModel):
    id: str              # e.g. "open_email_mom"
    label: str           # e.g. "Open email from Mom"
    risky: bool = False  # send/delete/buy need confirmation


class ScreenState(BaseModel):
    screen: str                       # e.g. "Inbox"
    description: str = ""             # text description (used in text mode)
    elements: list[ScreenElement]
    recent_actions: list[str] = []
    screenshot: Optional[str] = None  # data URL of a JPEG (used in vision mode)


class Suggestion(BaseModel):
    element_id: str
    label: str
    risky: bool


class SuggestResponse(BaseModel):
    suggestions: list[Suggestion]
    rejected_count: int     # how many AI picks failed validation
    used_fallback: bool     # True if every AI call failed
    vision_used: bool = False
    model_used: str = ""


class DescribeRequest(BaseModel):
    screenshot: str


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

VISION_NOTE = """
A screenshot of the user's screen is attached. Look at it to understand what the
user is reading and what they are likely trying to do."""


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


def vision_candidates() -> list[str]:
    return [working_vision_model] if working_vision_model else VISION_MODELS


# ---------- Model calls ----------

def ask_text(screen: ScreenState, element_list: str, recent: str) -> list[str]:
    user_message = (
        f"Screen: {screen.screen}\n"
        f"What the user sees: {screen.description}\n"
        f"Recent actions: {recent}\n"
        f"Available elements:\n{element_list}"
    )
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        response_format=RESPONSE_SCHEMA,
    )
    data = json.loads(response.choices[0].message.content)
    return [s["element_id"] for s in data.get("suggestions", [])]


def ask_vision(screen: ScreenState, element_list: str, recent: str) -> tuple[list[str], str]:
    """Send the screenshot instead of the text description. Returns (ids, model)."""
    global working_vision_model
    text = (
        f"Screen: {screen.screen}\n"
        f"Recent actions: {recent}\n"
        f"Available elements:\n{element_list}"
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + VISION_NOTE},
        {"role": "user", "content": [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": screen.screenshot}},
        ]},
    ]
    last_error: Exception = RuntimeError("no vision model configured")
    for model in vision_candidates():
        try:
            response = client.with_options(timeout=40).chat.completions.create(
                model=model, messages=messages, response_format=RESPONSE_SCHEMA,
            )
            data = json.loads(response.choices[0].message.content)
            working_vision_model = model
            return [s["element_id"] for s in data.get("suggestions", [])], model
        except Exception as error:
            print(f"Vision call with {model} failed: {error}")
            last_error = error
    raise last_error


# ---------- Endpoints ----------

@app.post("/suggest", response_model=SuggestResponse)
def suggest(screen: ScreenState) -> SuggestResponse:
    element_list = "\n".join(f"- {el.id}: {el.label}" for el in screen.elements)
    recent = ", ".join(screen.recent_actions) or "none"

    if screen.screenshot:
        try:
            raw_ids, model = ask_vision(screen, element_list, recent)
            valid, rejected = validate_suggestions(raw_ids, screen)
            return SuggestResponse(suggestions=valid, rejected_count=rejected, used_fallback=False,
                                   vision_used=True, model_used=model)
        except Exception:
            print("Vision failed, falling back to text mode")

    try:
        raw_ids = ask_text(screen, element_list, recent)
    except Exception as error:
        print(f"AI call failed: {error}")
        return SuggestResponse(suggestions=fallback_suggestions(screen), rejected_count=0,
                               used_fallback=True)

    valid, rejected = validate_suggestions(raw_ids, screen)
    return SuggestResponse(suggestions=valid, rejected_count=rejected, used_fallback=False,
                           vision_used=False, model_used=MODEL)


@app.post("/describe")
def describe(req: DescribeRequest):
    """Vision check: Muse Spark gets ONLY the screenshot, no text, and says what it sees."""
    global working_vision_model
    messages = [{"role": "user", "content": [
        {"type": "text", "text": "This is a screenshot of someone's screen. In one or two sentences, "
                                 "say what they are looking at and what they would most likely want to do next."},
        {"type": "image_url", "image_url": {"url": req.screenshot}},
    ]}]
    last_error = ""
    for model in vision_candidates():
        try:
            response = client.with_options(timeout=40).chat.completions.create(model=model, messages=messages)
            working_vision_model = model
            return {"text": response.choices[0].message.content, "model": model}
        except Exception as error:
            print(f"Describe with {model} failed: {error}")
            last_error = str(error)
    return {"text": f"Vision isn't available: {last_error[:200]}", "model": ""}


STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html")
