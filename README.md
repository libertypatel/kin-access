# KIN Access

**AI-powered switch access for people with severe motor disabilities like ALS.**

Traditional switch scanning steps through every item on screen one press at a time. KIN Access uses Meta's Muse Spark to predict the 4 most likely next actions, so tasks take a few presses instead of dozens.

Built for the Meta Global AI Developer Hackathon 2026 (Indie Developer track, Push the Frontier).

## The problem

Many people with ALS, spinal cord injuries, or cerebral palsy control a computer with a single switch, pressed with a cheek, head, hand, or foot. The standard method, switch scanning, highlights every item on screen one by one until the user presses. Simple tasks like replying to an email can take dozens of presses, and every press costs time and effort.

## How it works

1. KIN Access captures the current screen and the list of available actions.
2. Muse Spark predicts the 4 most likely next actions and returns them as structured JSON.
3. The backend validates every suggestion against a registry of allowed actions.
4. The 4 choices are highlighted one at a time. A single switch press selects one.
5. Risky actions (send, delete) require a confirmation press before they run.
6. If none of the 4 fit, "Something else" falls back to traditional scanning.

> The spacebar stands in for an accessibility switch. Most real switches connect to a computer as a keyboard key, so KIN Access works with them without extra hardware.

## Results

| Task | Traditional scanning (presses) | KIN Access (presses) |
|---|---|---|
| [Reply to an email] | [ ] | [ ] |
| [Delete a spam email] | [ ] | [ ] |
| ... | | |

[Summary: average presses saved, task success rate, % of AI suggestions that passed validation]

## Architecture

[Diagram: Frontend (React) → Backend (FastAPI) → Muse Spark → Validator → Action executor]

- **Frontend:** React, TypeScript, Vite
- **Backend:** Python, FastAPI, Pydantic
- **AI:** Meta Muse Spark (muse-spark-1.3) through the Meta Model API
- **Testing:** pytest

## Safety design

- The AI only suggests actions. Ordinary code decides what is allowed to run.
- Every suggestion is validated against an allowed-actions list.
- Risky actions always require a confirmation press.
- KIN Access is an accessibility tool for computer control. It gives no medical advice and makes no health decisions.

## Running it locally

```bash
# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Add MODEL_API_KEY to backend/.env
uvicorn main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## Built during the hackathon

All code in this repository was written during the hackathon building period (Oct 27 to Nov 4, 2026).

## Demo video

[Link to 3-minute demo]

## What's next

- Support for real desktop apps beyond the browser demo
- Learning each user's habits to improve suggestions
- Testing with switch users and accessibility specialists

## License

MIT
