# API

Base URL `http://localhost:8000`. Interactive docs at `/docs`.

All ids are strings. There is no authentication in v1; every document belongs
to the `demo` user.

## Health

`GET /health` → `{ status, database, llmConfigured }`

Reports whether Mongo is reachable and whether `OPENAI_API_KEY` is set. The
frontend uses this to show an honest offline state.

## Upload

`POST /upload-syllabus/` — multipart, field name `file`. PDF, DOCX, or text,
under 10MB.

Stores the syllabus **and** its tasks, then returns:

```json
{
  "id": "6650...",
  "course": { "code": "STAT 3341", "title": "...", "term": "Fall 2026" },
  "taskCount": 12,
  "tasks": [ ... ],
  "topics": [ ... ],
  "uploadedAt": "2026-09-08T22:41:00+00:00"
}
```

| Status | Meaning |
| :--- | :--- |
| 400 | File unreadable, or a scanned PDF with no text layer |
| 413 | Over 10MB |
| 502 | Extraction failed; the raw upload was still saved |

## Courses and deadlines

| Method | Path | Returns |
| :--- | :--- | :--- |
| `GET` | `/syllabi` | Every course, newest first, with `taskCount` |
| `GET` | `/syllabi/{id}` | One course |
| `DELETE` | `/syllabi/{id}` | Removes the course and its tasks |
| `GET` | `/tasks?upcomingOnly=` | All deadlines, due-date order, course attached |
| `GET` | `/syllabi/{id}/tasks` | One course's deadlines |
| `POST` | `/syllabi/{id}/tasks` | Add a deadline the syllabus left out |
| `PATCH` | `/tasks/{id}` | Change any field |
| `DELETE` | `/tasks/{id}` | |

Undated tasks sort last rather than blocking the list.

## Grades

`PUT /tasks/{id}/score` with `{ "score": 92 }`. Send `null` to clear it. The
denominator defaults to the task's `points`, then to 100.

`GET /syllabi/{id}/grade` — where the student stands using recorded scores only.

`POST /syllabi/{id}/grade/simulate`:

```json
{
  "assumedRemainingPct": 85,
  "assumedScores": { "6650...": 95 },
  "categoryWeights": [ { "type": "EXAM", "weightPct": 60 } ],
  "targetPct": 90
}
```

Returns `currentPct`, `projectedPct`, both as letters, `neededOnRemainingPct`,
`targetReachable`, a per-task `breakdown`, and `weightSource` — one of
`syllabus`, `categories`, or `even`. Show `weightSource` and `warnings` in the
UI so an estimate is never presented as a fact.

## Calendar

| Method | Path | Returns |
| :--- | :--- | :--- |
| `GET` | `/calendar.ics` | All deadlines as a subscribable feed |
| `GET` | `/syllabi/{id}/calendar.ics` | One course's feed |

`text/calendar`, RFC 5545. Each event carries a one-day-ahead alarm. Deadlines
with no date are skipped. Subscribe by URL in Google, Apple, or Outlook
Calendar rather than importing, so the feed keeps updating.
