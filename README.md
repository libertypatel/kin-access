# KIN Access

**AI-powered switch access for people with severe motor disabilities like ALS.**

Traditional switch scanning steps through every item on screen one press at a time. KIN Access uses Meta's Muse Spark to predict the 4 most likely next actions, so tasks take a few presses instead of dozens.

Built for the Meta Global AI Developer Hackathon 2026 (Indie Developer track, Push the Frontier).

**Headline result:** in an automated evaluation of 24 runs with the real Muse Spark model, KIN Access needed **60% fewer presses** than the best possible traditional scanning, and beat it in 23 of 24 runs.

## The problem

Many people with ALS, spinal cord injuries, or cerebral palsy control a computer with a single switch, triggered by a small movement like a cheek twitch, head tilt, or sip-and-puff. The standard method, switch scanning, highlights every item on screen one by one until the user presses. Replying to one email can take dozens of presses, and for someone who can move only one muscle, every press costs time and energy.

## How it works

1. KIN Access sends Muse Spark a description of the current screen and the list of available actions.
2. Muse Spark returns the 4 most likely next actions as structured JSON.
3. The backend validates every suggestion against the actions that actually exist on screen.
4. The 4 choices, plus "Something else," appear in a panel. **Space** moves the highlight and **Enter** selects (standard two-switch scanning).
5. Risky actions (send, delete) require a confirmation step, with **Cancel** highlighted first so a stray press can never send or delete.
6. "Something else" falls back to traditional scanning of the whole screen, so the user is never stuck.

> The spacebar and Enter key stand in for accessibility switches. Most real switches connect to a computer as keyboard keys, so KIN Access works with them without extra hardware.

## Results

### Automated evaluation (headline)

To measure the AI alone, without human mistakes, I built an evaluation harness that plays a **perfect switch user**. At each step it picks the first Muse Spark suggestion that gets closer to finishing the task, or uses "Something else" and scans the whole screen if none does. Presses are counted exactly as in the live interface. Every run makes fresh calls to Muse Spark (no caching), so the results show real run-to-run variation.

| Task | Traditional minimum | KIN runs (presses) | KIN average | Presses saved | Top pick right |
|---|---|---|---|---|---|
| Reply "Yes" to Mom's dinner email | 23 | 5, 5, 5 | 5.0 | 78% | 100% |
| Tell Mom you can't make it | 24 | 6, 6, 6 | 6.0 | 75% | 67% |
| Delete the spam email | 13 | 5, 5, 5 | 5.0 | 62% | 0% |
| Tell Work the report is coming Friday | 24 | 6, 6, 6 | 6.0 | 75% | 67% |
| Ask Work to talk tomorrow | 25 | 7, 7, 7 | 7.0 | 72% | 33% |
| Archive the Work email | 17 | 5, 5, 5 | 5.0 | 71% | 0% |
| Send Mom "Thinking of you!" | 26 | 19, 19, 19 | 19.0 | 27% | 67% |
| Tell Work you're running late | 27 | 9, 27, 20 | 18.7 | 31% | 22% |
| **Total (24 runs)** | **537** | **215** | | **60% fewer** | **51%** |

**KIN Access beat traditional scanning in 23 of 24 runs and tied in the other one.**

**The key insight:** Muse Spark's *first* suggestion was right only 51% of the time, yet KIN still saved 60% of presses. The AI doesn't have to be perfect. It only has to put the right action somewhere in its top 4, and moving down that short list costs one press per item, compared with scanning a whole screen.

### Manual runs (supporting evidence)

Before building the harness, I ran each task twice by hand with the real model. Totals: **74 and 81 presses vs 179** (59% and 55% fewer). These numbers include my own occasional extra presses, which is why I built the automated harness: it removes human error from the measurement.

### How the baseline is calculated

The "traditional minimum" is the fewest presses traditional scanning could possibly need, assuming **zero mistakes**. The code searches every path through the email app (Dijkstra's shortest-path algorithm), where reaching item number *i* costs *i* presses to move plus one to select, and risky actions add the confirmation step. This makes the comparison as generous to traditional scanning as possible. Real users, who make mistakes and scan more slowly, would save more.

### Honest limitations

- **Results vary between runs.** In "Tell Work you're running late," the three runs took 9, 27, and 20 presses. In the 27-press run, Muse Spark missed the right action and the fallback cost as much as scanning.
- **The fallback is expensive.** When none of the 4 suggestions fit, "Something else" scans the whole screen from the start. Two tasks (sending a new email) relied on it and saved only about 30%.
- **The harness is strict.** It only counts an action as progress if it lies on a shortest path to the goal, so it may slightly undercount KIN's benefit.
- **A mock app.** KIN Access controls a purpose-built email app in the browser, not a real computer.
- **Not yet tested with switch users.** These results come from simulated tasks, not from people who use switches day to day.

## Engineering decisions

**Choosing a model by measuring it.** I benchmarked four Muse Spark configurations on the same ranking task. All gave sensible rankings, but `muse-spark-1.1` answered in 3.6s versus 9.4s for `muse-spark-1.3` (and 11.2s for 1.3 with low reasoning effort). A switch user waits on every step, so latency matters more than raw capability here. KIN Access uses `muse-spark-1.1`.

**Prefetching.** While the user reads their choices, KIN quietly asks Muse Spark about the screens each choice leads to. When the user selects, the next suggestions are usually ready. This cut the average wait for choices to about 2 seconds while the model averaged about 8 seconds per call.

**The AI suggests, ordinary code decides.** Muse Spark returns only element IDs. The labels shown to the user, and whether an action is risky, come from the app's own data, so the model can't present a harmless-looking button that secretly deletes something. Any ID that isn't on screen is rejected and counted.

**Never leave the user stuck.** Every AI call has a timeout (15 seconds in the browser, 20 on the server). If a call fails, KIN shows backup choices instead of freezing. This came from a real bug: during testing, one stalled call froze the page.

### Iteration

- **An automated evaluation harness.** My manual runs mixed AI mistakes with my own extra presses. Rather than rerun only the tasks that looked bad (which would be cherry-picking), I built a simulated perfect user that runs every task 3 times and counts presses exactly like the interface. That isolates the AI's performance and makes the results reproducible.
- **Prompt refinement.** In manual run 1, "Ask Work to talk tomorrow" took 24 presses, barely better than scanning, because Muse Spark offered only one of the two possible replies. I updated the prompt to include every reply option, and the task dropped to 12 presses in manual run 2 and 7 presses in the automated evaluation.
- **Catching a bug through the stats.** The results panel tracks fallbacks. After one edit, it showed 9 fallbacks and a 0.03s response time, which revealed that every AI call was failing. The cause was a stray comma that turned the API client into a tuple. Without the fallback counter, the app would have looked like it worked while the AI was silently off.

## Architecture

```
Browser (HTML/JS)                 Backend (FastAPI)                 Meta Model API
switch scanning UI   --screen-->  /suggest endpoint   --prompt-->   Muse Spark 1.1
task tracking        <--4 IDs---  Pydantic validation <--JSON-----  structured output
prefetch cache                    safe fallback
```

- **Frontend:** HTML, CSS, JavaScript
- **Backend:** Python, FastAPI, Pydantic
- **AI:** Meta Muse Spark (`muse-spark-1.1`) through the Meta Model API, with JSON-schema structured output

## Safety design

- The AI only suggests. Ordinary code validates and decides what runs.
- Risky actions always need a confirmation step, and the safe choice is highlighted first.
- Timeouts and fallbacks mean the user always has choices.
- **KIN Access is an accessibility tool for computer control. It gives no medical advice and makes no health decisions.**
- Meets WCAG AA color contrast, offers a Large text mode, and respects the system “Reduce motion” setting.

## Running it locally

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
echo "MODEL_API_KEY=your-key-here" > .env
uvicorn main:app --reload
```

Then open http://127.0.0.1:8000, pick a task, click **Start task**, and use **Space** and **Enter**.

## Built during the hackathon

All code in this repository was written during the hackathon building period (Oct 27 to Nov 4, 2026). The commit history shows each step.

## Demo video

[Link to 3-minute demo]

## What's next

- **Smarter "Something else":** scan only the items not already offered, content first, so a missed prediction costs less. This targets the two weakest tasks.
- **Consistency:** ask for rankings several times and combine them to reduce run-to-run variation.
- **Real apps:** move from the mock email app to real web pages and desktop apps.
- **Personalization:** learn each user's habits to improve predictions.
- **Testing with switch users** and accessibility specialists.

## License

MIT
