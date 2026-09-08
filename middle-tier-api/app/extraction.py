"""Text extraction from uploaded files, and the LLM call that structures it."""

import io
import json
import os
import re
from typing import Any, Dict, Tuple

import PyPDF2
from docx import Document
from openai import OpenAI
from PyPDF2.errors import PdfReadError

MAX_FILE_BYTES = 10 * 1024 * 1024  # keep in sync with the copy on the upload page
MAX_PROMPT_CHARS = 12_000
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

EXTRACTION_SYSTEM = "You extract structured academic deadlines from syllabus text."

EXTRACTION_PROMPT = """Extract the course info and every graded item from the syllabus below.

Return JSON with exactly this shape:

{
  "course": {
    "code": "string|null",
    "title": "string|null",
    "term": "string|null",
    "instructor": "string|null",
    "meeting": "string|null"
  },
  "tasks": [
    {
      "type": "HOMEWORK|PROJECT|EXAM|QUIZ|READING|OTHER",
      "title": "string",
      "dueAt": "YYYY-MM-DDTHH:mm:ssZ|null",
      "window": {"start": "YYYY-MM-DDTHH:mm:ssZ|null", "end": "YYYY-MM-DDTHH:mm:ssZ|null"},
      "points": number|null,
      "weightPct": number|null,
      "description": "string|null",
      "sourceText": "string"
    }
  ],
  "topics": [
    {"week": number|null, "title": "string", "readings": ["string"]}
  ]
}

Rules:
- weightPct is the percentage of the final grade, as a number (15, not "15%").
  If the syllabus gives a category weight (e.g. "Homework: 30%") and lists N
  homework items, put the category total on each item's weightPct divided by N.
- If a date has no time, use 23:59:59Z.
- Infer the year from the term when the syllabus writes dates without one.
- Never invent a task that is not in the text. sourceText must quote the line
  the task came from.

Syllabus text:
"""


class ExtractionError(Exception):
    """Raised when a file can't be read at all."""


def extract_text(contents: bytes, filename: str | None, content_type: str | None) -> str:
    """Pull raw text out of a PDF, DOCX, or plain text upload."""
    name = (filename or "").lower()

    try:
        if content_type == "application/pdf" or name.endswith(".pdf"):
            reader = PyPDF2.PdfReader(io.BytesIO(contents))
            text = "".join(page.extract_text() or "" for page in reader.pages)
        elif name.endswith(".docx"):
            doc = Document(io.BytesIO(contents))
            text = "\n".join(p.text for p in doc.paragraphs)
        else:
            text = contents.decode("utf-8")
    except PdfReadError as exc:
        raise ExtractionError(f"That PDF couldn't be opened: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ExtractionError(f"That file isn't a PDF, DOCX, or UTF-8 text: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - surfaced to the user as a 400
        raise ExtractionError(f"Couldn't read that file: {exc}") from exc

    text = text.strip()
    if not text:
        raise ExtractionError(
            "No text found in that file. If it's a scanned PDF, it needs OCR first."
        )
    return text


def parse_llm_json(raw: str) -> Dict[str, Any]:
    """Parse the model's reply, tolerating ```json fences."""
    cleaned = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model did not return valid JSON: {exc}") from exc


def structure_syllabus(raw_text: str) -> Tuple[Dict[str, Any], str | None]:
    """Send syllabus text to the LLM.

    Returns (structured_data, error). On failure the structured data is an empty
    skeleton and `error` explains why, so the caller can still store the raw
    upload and tell the user honestly that extraction failed.
    """
    empty: Dict[str, Any] = {"course": {}, "tasks": [], "topics": []}

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return empty, "OPENAI_API_KEY is not set. Add it to middle-tier-api/app/.env."

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM},
                {"role": "user", "content": EXTRACTION_PROMPT + raw_text[:MAX_PROMPT_CHARS]},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        data = parse_llm_json(response.choices[0].message.content or "")
    except Exception as exc:  # noqa: BLE001 - reported to the user, not swallowed
        return empty, f"Extraction failed: {exc}"

    data.setdefault("course", {})
    data.setdefault("tasks", [])
    data.setdefault("topics", [])
    return data, None
