# Data model

MongoDB, two collections. The Postgres DDL that used to be in this file
described a schema the application never used.

## `syllabi`

One document per uploaded file.

| Field | Type | Notes |
| :--- | :--- | :--- |
| `_id` | ObjectId | Exposed to clients as the string `id` |
| `userId` | string | Always `"demo"` in v1; the seam for real accounts |
| `filename` | string | As uploaded |
| `contentType` | string | MIME type from the upload |
| `rawText` | string | Full extracted text, kept for re-processing |
| `course` | object | `{ code, title, term, instructor, meeting }` |
| `topics` | array | `{ week, title, readings[] }` from the LLM |
| `uploadedAt` | datetime | UTC |
| `extractionError` | string \| null | Set when the LLM call failed |

## `tasks`

One document per graded item. Written by the upload endpoint and by manual entry.

| Field | Type | Notes |
| :--- | :--- | :--- |
| `_id` | ObjectId | Exposed as `id` |
| `syllabusId` | string | The parent syllabus `_id` as a string |
| `userId` | string | Denormalised for cross-course queries |
| `type` | string | `HOMEWORK`, `PROJECT`, `EXAM`, `QUIZ`, `READING`, `OTHER` |
| `title` | string | |
| `dueAt` | string \| null | ISO 8601, or `YYYY-MM-DD` for date-only |
| `window` | object \| null | `{ start, end }` for exams with a sitting time |
| `points` | number \| null | Points possible |
| `weightPct` | number \| null | Percent of the final grade |
| `description` | string \| null | |
| `sourceText` | string \| null | The syllabus line this came from |
| `score` | number \| null | What the student actually got |
| `scoreOutOf` | number \| null | Denominator for `score` |

Dates are stored as strings exactly as the LLM returns them, so the source is
never lost to a parsing guess. Parsing happens at the edges, in `ics_feed.py`
and in the frontend.

## Indexes

Created on startup by `ensure_indexes()`:

- `tasks`: `(syllabusId, dueAt)` and `(dueAt)`
- `syllabi`: `(userId, uploadedAt)`
