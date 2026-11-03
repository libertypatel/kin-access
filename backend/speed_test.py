import os
import time

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(base_url="https://api.meta.ai/v1", api_key=os.environ["MODEL_API_KEY"])

PROMPT = (
    "A user on an email inbox can: open_email_mom, open_email_work, compose, "
    "delete_spam, scroll_down. Reply with only the 4 most likely element ids, comma-separated."
)

tests = [
    ("muse-spark-1.3", {}),
    ("muse-spark-1.3", {"reasoning_effort": "low"}),
    ("muse-spark-1.2", {}),
    ("muse-spark-1.1", {}),
]

for model, extra in tests:
    start = time.time()
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": PROMPT}],
            **extra,
        )
        answer = r.choices[0].message.content.strip()[:60]
        print(f"{model} {extra}: {time.time() - start:.1f}s -> {answer}")
    except Exception as e:
        print(f"{model} {extra}: ERROR {str(e)[:80]}")