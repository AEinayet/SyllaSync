# Architecture

Two tiers. The separate `backend-api` service described in earlier versions of
this document was removed in February 2026 and its work moved into the middle
tier, which now talks to MongoDB directly via a connection string.

```
frontend-app/          Static HTML, CSS, JS. No framework, no build step.
      |
      | fetch (JSON, multipart for uploads)
      v
middle-tier-api/       FastAPI. All application logic lives here.
      |            \
      | pymongo     \ https
      v              v
  MongoDB         OpenAI API
```

## What each part owns

**Frontend** renders the dashboard, upload flow, and grade simulator. It holds
no application logic and no cached data — every screen is drawn from an API
response. `config.js` holds the one line that points it at an API.

**Middle tier** receives uploads, extracts text, prompts the LLM for structured
JSON, persists to Mongo, and serves the calendar feed and grade math.

| Module | Responsibility |
| :--- | :--- |
| `main.py` | HTTP routes and request validation only |
| `extraction.py` | File text extraction and the LLM prompt |
| `grades.py` | Weight resolution, current grade, what-if projection |
| `ics_feed.py` | iCalendar generation |
| `database.py` | Mongo client, collections, indexes |
| `models.py` | Pydantic request and response shapes |

**MongoDB** stores two collections, `syllabi` and `tasks`.

## Upload path

1. The upload page posts the file to `POST /upload-syllabus/`.
2. The middle tier extracts text (PyPDF2, python-docx, or UTF-8 decode).
3. It sends the text plus a fixed schema prompt to the LLM.
4. It writes one `syllabi` document and one `tasks` document per graded item,
   in the same request. Nothing is left for the client to persist.
5. It returns the course, the task count, and the tasks.

If the LLM call fails, the raw upload is still saved with an `extractionError`
recorded, and the endpoint returns 502 with the reason. It never returns a
success that isn't one.
