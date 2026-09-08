"""End-to-end tests over the real routes, with an in-memory Mongo and a stubbed LLM.

Run from middle-tier-api/:   pytest
"""

import io
from unittest.mock import patch

import mongomock
import pytest
from fastapi.testclient import TestClient

FAKE_EXTRACTION = (
    {
        "course": {"code": "STAT 3341", "title": "Probability and Statistics",
                   "term": "Fall 2026", "instructor": "Dr. Guo", "meeting": "MW 11:30"},
        "tasks": [
            {"type": "HOMEWORK", "title": "HW 1", "dueAt": "2026-09-15",
             "weightPct": 10, "points": 100, "sourceText": "HW1 due 9/15"},
            {"type": "HOMEWORK", "title": "HW 2", "dueAt": "2026-09-29",
             "weightPct": 10, "points": 100, "sourceText": "HW2 due 9/29"},
            {"type": "EXAM", "title": "Midterm", "dueAt": "2026-10-14T14:00:00Z",
             "weightPct": 30, "points": 100, "sourceText": "Midterm 10/14"},
            {"type": "EXAM", "title": "Final", "dueAt": "2026-12-10T14:00:00Z",
             "weightPct": 50, "points": 100, "sourceText": "Final 12/10"},
        ],
        "topics": [],
    },
    None,
)


@pytest.fixture
def client():
    fake_db = mongomock.MongoClient()["test"]
    import app.database as database
    import app.main as main

    database.ensure_indexes = lambda: None
    for module in (database, main):
        module.syllabi_collection = fake_db["syllabi"]
        module.tasks_collection = fake_db["tasks"]

    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture
def syllabus_id(client):
    with patch("app.main.extraction.structure_syllabus", return_value=FAKE_EXTRACTION):
        response = client.post(
            "/upload-syllabus/",
            files={"file": ("syllabus.txt", io.BytesIO(b"syllabus text"), "text/plain")},
        )
    assert response.status_code == 200
    return response.json()["id"]


def test_upload_persists_tasks_not_just_the_syllabus(client, syllabus_id):
    """The original bug: the syllabus saved but the tasks collection stayed empty."""
    assert client.get(f"/syllabi/{syllabus_id}").json()["taskCount"] == 4
    assert len(client.get(f"/syllabi/{syllabus_id}/tasks").json()) == 4


def test_get_syllabus_returns_an_uploaded_syllabus(client, syllabus_id):
    """The original bug: this 500'd because the read model wanted fields the writer never set."""
    response = client.get(f"/syllabi/{syllabus_id}")
    assert response.status_code == 200
    assert response.json()["course"]["code"] == "STAT 3341"


def test_tasks_carry_their_course_and_sort_by_due_date(client, syllabus_id):
    tasks = client.get("/tasks").json()
    assert [t["title"] for t in tasks] == ["HW 1", "HW 2", "Midterm", "Final"]
    assert all(t["courseCode"] == "STAT 3341" for t in tasks)


def test_grade_uses_syllabus_weights(client, syllabus_id):
    tasks = {t["title"]: t["id"] for t in client.get("/tasks").json()}
    client.put(f"/tasks/{tasks['HW 1']}/score", json={"score": 92})
    client.put(f"/tasks/{tasks['Midterm']}/score", json={"score": 78})

    grade = client.get(f"/syllabi/{syllabus_id}/grade").json()
    # (92 * 10 + 78 * 30) / 40 = 81.5
    assert grade["currentPct"] == 81.5
    assert grade["currentLetter"] == "B-"
    assert grade["weightSource"] == "syllabus"
    assert grade["remainingWeightPct"] == 60.0


def test_simulation_answers_what_is_needed_for_a_target(client, syllabus_id):
    tasks = {t["title"]: t["id"] for t in client.get("/tasks").json()}
    client.put(f"/tasks/{tasks['HW 1']}/score", json={"score": 92})
    client.put(f"/tasks/{tasks['Midterm']}/score", json={"score": 78})

    result = client.post(
        f"/syllabi/{syllabus_id}/grade/simulate",
        json={"assumedRemainingPct": 85, "targetPct": 90},
    ).json()
    # (90 - 32.6) / 60 * 100
    assert result["neededOnRemainingPct"] == pytest.approx(95.67, abs=0.01)
    assert result["targetReachable"] is True
    assert result["projectedPct"] == pytest.approx(83.6, abs=0.01)


def test_even_weighting_warns_when_the_syllabus_gave_none(client):
    with patch("app.main.extraction.structure_syllabus", return_value=(
        {"course": {"code": "CS 1337"},
         "tasks": [{"type": "HOMEWORK", "title": "HW 1", "dueAt": "2026-09-15"},
                   {"type": "EXAM", "title": "Final", "dueAt": "2026-12-01"}],
         "topics": []}, None,
    )):
        sid = client.post("/upload-syllabus/", files={
            "file": ("s.txt", io.BytesIO(b"text"), "text/plain")}).json()["id"]

    grade = client.get(f"/syllabi/{sid}/grade").json()
    assert grade["weightSource"] == "even"
    assert grade["warnings"], "an estimate must announce itself"


def test_calendar_feed_is_valid_and_skips_undated_tasks(client, syllabus_id):
    client.post(f"/syllabi/{syllabus_id}/tasks",
                json={"type": "OTHER", "title": "No date", "dueAt": None})

    response = client.get("/calendar.ics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    assert response.text.count("BEGIN:VEVENT") == 4  # the undated one is skipped
    assert "SUMMARY:STAT 3341: Midterm" in response.text


def test_extraction_failure_is_reported_not_swallowed(client):
    """The old code returned 200 with an empty result when OpenAI failed."""
    with patch("app.main.extraction.structure_syllabus",
               return_value=({"course": {}, "tasks": [], "topics": []}, "OPENAI_API_KEY is not set.")):
        response = client.post("/upload-syllabus/", files={
            "file": ("s.txt", io.BytesIO(b"text"), "text/plain")})
    assert response.status_code == 502
    assert "OPENAI_API_KEY" in response.json()["detail"]["message"]


def test_unreadable_upload_gets_a_useful_message(client):
    response = client.post("/upload-syllabus/", files={
        "file": ("empty.txt", io.BytesIO(b"   "), "text/plain")})
    assert response.status_code == 400
    assert "No text found" in response.json()["detail"]


def test_bad_ids_are_rejected_cleanly(client):
    assert client.get("/syllabi/not-an-object-id").status_code == 400
    assert client.get("/syllabi/6650aaaaaaaaaaaaaaaaaaaa").status_code == 404
