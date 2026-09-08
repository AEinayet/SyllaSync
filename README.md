# SyllaSync

Upload a course syllabus, get every deadline extracted into a calendar you can
subscribe to, and see what you need on what's left to hit the grade you want.

Built by six students; currently a local demo with no accounts.

## What it does

- **Extracts deadlines.** Upload a PDF, DOCX, or text syllabus. The middle tier
  pulls the text, sends it to an LLM with a fixed JSON schema, and stores the
  course plus every graded item in MongoDB.
- **Shows a real calendar.** The dashboard reads from the API — week and month
  views, dots on days with deadlines, and an upcoming list across all courses.
- **Syncs to your calendar app.** `GET /calendar.ics` is a subscribable feed.
  Paste it into Google, Apple, or Outlook Calendar and deadlines appear there,
  each with a one-day-ahead reminder.
- **Simulates grades.** Record what you scored, then ask what you need on the
  rest to finish at a target percentage.

## Running it

You need Docker and an OpenAI API key.

```bash
git clone https://github.com/AEinayet/SyllaSync.git
cd SyllaSync
cp middle-tier-api/app/.env.example middle-tier-api/app/.env
# open that .env and paste in your OPENAI_API_KEY
docker compose up --build
```

Then open:

| What | Where |
| :--- | :--- |
| The app | http://localhost:8080/title.html |
| API docs (Swagger) | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |

`/health` reports whether Mongo is reachable and whether the OpenAI key is set.
Check it first if the dashboard shows a connection error.

### Without Docker

```bash
cd middle-tier-api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp app/.env.example app/.env    # add your key
uvicorn app.main:app --reload

# in a second terminal
cd frontend-app && python -m http.server 8080
```

Opening the HTML files directly with `file://` will not work — the browser
blocks the API calls. Serve them over http.

## Architecture

Two tiers, not three. The original separate `backend-api` was folded into the
middle tier in February.

```
frontend-app/ (static HTML/CSS/JS)
      |  fetch
      v
middle-tier-api/ (FastAPI)
      |                 \
      v                  v
  MongoDB          OpenAI API
```

| Folder | What's in it |
| :--- | :--- |
| `frontend-app/` | Dashboard, upload page, grade simulator. No build step. |
| `middle-tier-api/app/` | `main.py` routes, `extraction.py` LLM, `grades.py` math, `ics_feed.py` calendar |
| `documentation/` | Design notes and the API contract |

Point the frontend at a different API by editing the one line in
`frontend-app/config.js`.

## API

Full interactive docs at `/docs`. The main ones:

| Method | Path | Purpose |
| :--- | :--- | :--- |
| `POST` | `/upload-syllabus/` | Upload a file; stores the course and its tasks |
| `GET` | `/syllabi` | Every uploaded course |
| `GET` | `/tasks` | Every deadline, due-date order, with course attached |
| `PUT` | `/tasks/{id}/score` | Record what you scored |
| `GET` | `/syllabi/{id}/grade` | Where you stand now |
| `POST` | `/syllabi/{id}/grade/simulate` | What-if projection and target math |
| `GET` | `/calendar.ics` | Subscribable feed of all deadlines |

## Known limits

- **No accounts.** Everything is stored under a single `demo` user. Adding auth
  means threading a real user id where `DEMO_USER_ID` is used in `main.py`.
- **Scanned PDFs don't work.** Text extraction needs selectable text, not an
  image. The upload page says so and the API returns a clear 400.
- **Extraction quality varies by syllabus.** When a syllabus states category
  weights instead of per-item weights, the grade simulator falls back to an
  even split and tells you it did.
