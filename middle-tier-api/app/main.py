"""SyllaSync middle tier.

Frontend -> this service -> (OpenAI for extraction, MongoDB for storage).

v1 has no accounts. Every document is written under DEMO_USER_ID so that adding
real auth later means threading a real id through, not reshaping the data.
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from dotenv import load_dotenv
from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from . import extraction, grades
from .database import ensure_indexes, syllabi_collection, tasks_collection
from .ics_feed import build_feed
from .models import (
    Course,
    GradeResult,
    ScoreUpdate,
    SimulationInput,
    SyllabusOut,
    TaskCreate,
    TaskOut,
    TaskUpdate,
    UploadResult,
)

load_dotenv()

DEMO_USER_ID = "demo"

app = FastAPI(
    title="SyllaSync Middle Tier",
    description="Syllabus upload, LLM extraction, deadlines, grades, and calendar feeds.",
    version="1.0.0",
)

# Explicit origins. "*" plus allow_credentials is rejected by browsers, which is
# why the old config silently failed.
allowed_origins = [
    o.strip()
    for o in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:8080,http://127.0.0.1:8080,http://localhost:5500,http://127.0.0.1:5500",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        ensure_indexes()
    except Exception as exc:  # noqa: BLE001 - the API still works without indexes
        print(f"[startup] index creation skipped: {exc}")
    yield


app.router.lifespan_context = lifespan


# ------------------------------------------------------------------- helpers


def _oid(value: str, label: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid {label} id: {value}")


def _iso(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat()
    return value


def _task_out(doc: Dict[str, Any], course: Dict[str, Any] | None = None) -> TaskOut:
    course = course or {}
    return TaskOut(
        id=str(doc["_id"]),
        syllabusId=str(doc.get("syllabusId", "")),
        type=doc.get("type") or "OTHER",
        title=doc.get("title") or "(untitled)",
        dueAt=doc.get("dueAt"),
        window=doc.get("window"),
        points=doc.get("points"),
        weightPct=doc.get("weightPct"),
        description=doc.get("description"),
        sourceText=doc.get("sourceText"),
        score=doc.get("score"),
        scoreOutOf=doc.get("scoreOutOf"),
        courseCode=course.get("code"),
        courseTitle=course.get("title"),
    )


def _syllabus_or_404(syllabus_id: str) -> Dict[str, Any]:
    doc = syllabi_collection.find_one({"_id": _oid(syllabus_id, "syllabus")})
    if not doc:
        raise HTTPException(status_code=404, detail="No syllabus with that id.")
    return doc


def _tasks_with_course(query: Dict[str, Any]) -> List[TaskOut]:
    """Load tasks and attach their course info in one pass."""
    task_docs = list(tasks_collection.find(query))
    syllabus_ids = {t.get("syllabusId") for t in task_docs if t.get("syllabusId")}
    courses: Dict[str, Dict[str, Any]] = {}
    for sid in syllabus_ids:
        try:
            doc = syllabi_collection.find_one({"_id": ObjectId(sid)}, {"course": 1})
        except (InvalidId, TypeError):
            continue
        if doc:
            courses[sid] = doc.get("course") or {}

    out = [_task_out(t, courses.get(t.get("syllabusId"))) for t in task_docs]
    # Undated tasks sort last rather than blocking the list.
    out.sort(key=lambda t: (t.dueAt is None, t.dueAt or ""))
    return out


# -------------------------------------------------------------------- health


@app.get("/health")
def health() -> Dict[str, Any]:
    """Used by the frontend to show an honest 'API offline' state."""
    try:
        syllabi_collection.database.client.admin.command("ping")
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "database": db_ok,
        "llmConfigured": bool(os.getenv("OPENAI_API_KEY")),
    }


# -------------------------------------------------------------------- upload


@app.post("/upload-syllabus/", response_model=UploadResult)
async def upload_syllabus(file: UploadFile = File(...)) -> UploadResult:
    """Upload a syllabus, extract its deadlines, and store both in one call.

    The old version stored the syllabus but never the tasks, so the tasks
    collection stayed empty in the real flow. This writes both.
    """
    contents = await file.read()
    if len(contents) > extraction.MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File is over the {extraction.MAX_FILE_BYTES // (1024 * 1024)}MB limit.",
        )

    try:
        raw_text = extraction.extract_text(contents, file.filename, file.content_type)
    except extraction.ExtractionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    structured, error = extraction.structure_syllabus(raw_text)
    uploaded_at = datetime.now(timezone.utc)
    course = structured.get("course") or {}

    syllabus_doc = {
        "userId": DEMO_USER_ID,
        "filename": file.filename,
        "contentType": file.content_type,
        "rawText": raw_text,
        "course": course,
        "topics": structured.get("topics") or [],
        "uploadedAt": uploaded_at,
        "extractionError": error,
    }

    try:
        syllabus_id = str(syllabi_collection.insert_one(syllabus_doc).inserted_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Could not reach the database: {exc}")

    task_docs = [
        {
            "syllabusId": syllabus_id,
            "userId": DEMO_USER_ID,
            "type": t.get("type") or "OTHER",
            "title": t.get("title") or "(untitled)",
            "dueAt": t.get("dueAt"),
            "window": t.get("window"),
            "points": t.get("points"),
            "weightPct": t.get("weightPct"),
            "description": t.get("description"),
            "sourceText": t.get("sourceText"),
            "score": None,
            "scoreOutOf": None,
        }
        for t in structured.get("tasks") or []
    ]
    if task_docs:
        tasks_collection.insert_many(task_docs)

    if error:
        # Surface the failure instead of returning 200 with an empty result.
        raise HTTPException(
            status_code=502,
            detail={"message": error, "syllabusId": syllabus_id},
        )

    return UploadResult(
        id=syllabus_id,
        course=Course(**course),
        taskCount=len(task_docs),
        tasks=_tasks_with_course({"syllabusId": syllabus_id}),
        topics=structured.get("topics") or [],
        uploadedAt=uploaded_at.isoformat(),
    )


# ------------------------------------------------------------------ syllabi


@app.get("/syllabi", response_model=List[SyllabusOut])
def list_syllabi() -> List[SyllabusOut]:
    """Every course the student has uploaded. Drives the dashboard."""
    out = []
    for doc in syllabi_collection.find({"userId": DEMO_USER_ID}).sort("uploadedAt", -1):
        sid = str(doc["_id"])
        out.append(
            SyllabusOut(
                id=sid,
                userId=doc.get("userId", DEMO_USER_ID),
                filename=doc.get("filename"),
                contentType=doc.get("contentType"),
                course=Course(**(doc.get("course") or {})),
                taskCount=tasks_collection.count_documents({"syllabusId": sid}),
                uploadedAt=_iso(doc.get("uploadedAt")),
                extractionError=doc.get("extractionError"),
            )
        )
    return out


@app.get("/syllabi/{syllabus_id}", response_model=SyllabusOut)
def get_syllabus(syllabus_id: str) -> SyllabusOut:
    doc = _syllabus_or_404(syllabus_id)
    return SyllabusOut(
        id=str(doc["_id"]),
        userId=doc.get("userId", DEMO_USER_ID),
        filename=doc.get("filename"),
        contentType=doc.get("contentType"),
        course=Course(**(doc.get("course") or {})),
        taskCount=tasks_collection.count_documents({"syllabusId": syllabus_id}),
        uploadedAt=_iso(doc.get("uploadedAt")),
        extractionError=doc.get("extractionError"),
    )


@app.delete("/syllabi/{syllabus_id}")
def delete_syllabus(syllabus_id: str) -> Dict[str, Any]:
    """Remove a course and everything extracted from it."""
    _syllabus_or_404(syllabus_id)
    removed = tasks_collection.delete_many({"syllabusId": syllabus_id}).deleted_count
    syllabi_collection.delete_one({"_id": _oid(syllabus_id, "syllabus")})
    return {"id": syllabus_id, "deletedTasks": removed}


# -------------------------------------------------------------------- tasks


@app.get("/tasks", response_model=List[TaskOut])
def list_all_tasks(
    upcomingOnly: bool = Query(False, description="Hide anything already past due"),
) -> List[TaskOut]:
    """Every deadline across every course, in due-date order."""
    tasks = _tasks_with_course({"userId": DEMO_USER_ID})
    if upcomingOnly:
        today = datetime.now(timezone.utc).date().isoformat()
        tasks = [t for t in tasks if t.dueAt and t.dueAt[:10] >= today]
    return tasks


@app.get("/syllabi/{syllabus_id}/tasks", response_model=List[TaskOut])
def list_tasks_for_syllabus(syllabus_id: str) -> List[TaskOut]:
    _syllabus_or_404(syllabus_id)
    return _tasks_with_course({"syllabusId": syllabus_id})


@app.post("/syllabi/{syllabus_id}/tasks", response_model=TaskOut, status_code=201)
def add_task(syllabus_id: str, task: TaskCreate) -> TaskOut:
    """Add a deadline the syllabus left out."""
    syllabus = _syllabus_or_404(syllabus_id)
    doc = task.model_dump()
    doc.update({
        "syllabusId": syllabus_id,
        "userId": DEMO_USER_ID,
        "score": None,
        "scoreOutOf": None,
    })
    doc["_id"] = tasks_collection.insert_one(doc).inserted_id
    return _task_out(doc, syllabus.get("course"))


@app.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: str, task: TaskUpdate) -> TaskOut:
    oid = _oid(task_id, "task")
    if not tasks_collection.find_one({"_id": oid}):
        raise HTTPException(status_code=404, detail="No task with that id.")
    changes = task.model_dump(exclude_unset=True)
    if changes:
        tasks_collection.update_one({"_id": oid}, {"$set": changes})
    doc = tasks_collection.find_one({"_id": oid})
    course = syllabi_collection.find_one(
        {"_id": _oid(doc["syllabusId"], "syllabus")}, {"course": 1}
    ) or {}
    return _task_out(doc, course.get("course"))


@app.put("/tasks/{task_id}/score", response_model=TaskOut)
def set_score(task_id: str, score: ScoreUpdate) -> TaskOut:
    """Record what you actually got. This is what feeds the grade simulator."""
    oid = _oid(task_id, "task")
    doc = tasks_collection.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="No task with that id.")

    out_of = score.scoreOutOf or doc.get("points") or 100.0
    if score.score is not None and score.score < 0:
        raise HTTPException(status_code=400, detail="Score cannot be negative.")

    tasks_collection.update_one(
        {"_id": oid},
        {"$set": {"score": score.score, "scoreOutOf": None if score.score is None else out_of}},
    )
    updated = tasks_collection.find_one({"_id": oid})
    course = syllabi_collection.find_one(
        {"_id": _oid(updated["syllabusId"], "syllabus")}, {"course": 1}
    ) or {}
    return _task_out(updated, course.get("course"))


@app.delete("/tasks/{task_id}")
def delete_task(task_id: str) -> Dict[str, Any]:
    result = tasks_collection.delete_one({"_id": _oid(task_id, "task")})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="No task with that id.")
    return {"id": task_id, "deleted": 1}


# -------------------------------------------------------------------- grades


@app.get("/syllabi/{syllabus_id}/grade", response_model=GradeResult)
def current_grade(syllabus_id: str) -> GradeResult:
    """Where the student stands right now, using recorded scores only."""
    _syllabus_or_404(syllabus_id)
    tasks = [t.model_dump() for t in _tasks_with_course({"syllabusId": syllabus_id})]
    return grades.compute(tasks, SimulationInput())


@app.post("/syllabi/{syllabus_id}/grade/simulate", response_model=GradeResult)
def simulate_grade(
    syllabus_id: str, sim: SimulationInput = Body(default=SimulationInput())
) -> GradeResult:
    """What-if: assume scores on what's left, or ask what you need for a target."""
    _syllabus_or_404(syllabus_id)
    tasks = [t.model_dump() for t in _tasks_with_course({"syllabusId": syllabus_id})]
    return grades.compute(tasks, sim)


# ------------------------------------------------------------------ calendar


def _ics_response(tasks: List[TaskOut], name: str, filename: str) -> Response:
    body = build_feed([t.model_dump() for t in tasks], calendar_name=name)
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/calendar.ics")
def calendar_feed() -> Response:
    """Subscribe to this URL from Google, Apple, or Outlook Calendar."""
    return _ics_response(_tasks_with_course({"userId": DEMO_USER_ID}), "SyllaSync", "syllasync.ics")


@app.get("/syllabi/{syllabus_id}/calendar.ics")
def syllabus_calendar_feed(syllabus_id: str) -> Response:
    """One course's deadlines, so students can subscribe per class."""
    doc = _syllabus_or_404(syllabus_id)
    course = doc.get("course") or {}
    name = course.get("code") or course.get("title") or "SyllaSync"
    return _ics_response(
        _tasks_with_course({"syllabusId": syllabus_id}), name, f"{name.replace(' ', '_')}.ics"
    )
