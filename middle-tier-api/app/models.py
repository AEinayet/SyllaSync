"""Pydantic models.

One shape per concept. The old SQL-era User/Syllabus/Tasks models were removed:
they described a Postgres schema the app never used, and they were the cause of
the GET /syllabi/{id} validation failure.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

TaskType = Literal["HOMEWORK", "PROJECT", "EXAM", "QUIZ", "READING", "OTHER"]


# ---------------------------------------------------------------- course/task


class Course(BaseModel):
    code: Optional[str] = None
    title: Optional[str] = None
    term: Optional[str] = None
    instructor: Optional[str] = None
    meeting: Optional[str] = None


class TaskWindow(BaseModel):
    """Optional time window, used for exams and quizzes."""

    start: Optional[str] = None  # ISO 8601 datetime string
    end: Optional[str] = None


class TaskCreate(BaseModel):
    """One task. Used for LLM output and for manual entry."""

    type: TaskType = "OTHER"
    title: str
    dueAt: Optional[str] = None  # YYYY-MM-DD or YYYY-MM-DDTHH:mm:ssZ
    window: Optional[TaskWindow] = None
    points: Optional[float] = None
    weightPct: Optional[float] = None
    description: Optional[str] = None
    sourceText: Optional[str] = None


class TaskUpdate(BaseModel):
    """Partial update. Only the fields you send are changed."""

    type: Optional[TaskType] = None
    title: Optional[str] = None
    dueAt: Optional[str] = None
    window: Optional[TaskWindow] = None
    points: Optional[float] = None
    weightPct: Optional[float] = None
    description: Optional[str] = None
    sourceText: Optional[str] = None
    score: Optional[float] = None
    scoreOutOf: Optional[float] = None


class TaskOut(BaseModel):
    id: str
    syllabusId: str
    type: str = "OTHER"
    title: str
    dueAt: Optional[str] = None
    window: Optional[TaskWindow] = None
    points: Optional[float] = None
    weightPct: Optional[float] = None
    description: Optional[str] = None
    sourceText: Optional[str] = None
    score: Optional[float] = None
    scoreOutOf: Optional[float] = None
    # denormalised for the dashboard, so it doesn't need a second request
    courseCode: Optional[str] = None
    courseTitle: Optional[str] = None


class ScoreUpdate(BaseModel):
    """Record what a student actually got on a task."""

    score: Optional[float] = Field(None, description="Points earned, or null to clear")
    scoreOutOf: Optional[float] = Field(
        None, description="Points possible. Defaults to the task's points, then 100."
    )


# ------------------------------------------------------------------- syllabus


class SyllabusOut(BaseModel):
    id: str
    userId: str
    filename: Optional[str] = None
    contentType: Optional[str] = None
    course: Course = Course()
    taskCount: int = 0
    uploadedAt: Optional[str] = None
    extractionError: Optional[str] = None


class UploadResult(BaseModel):
    id: str
    course: Course
    taskCount: int
    tasks: List[TaskOut] = []
    topics: List[Dict[str, Any]] = []
    uploadedAt: str


# --------------------------------------------------------------- grade models


class CategoryWeight(BaseModel):
    type: TaskType
    weightPct: float


class SimulationInput(BaseModel):
    """What-if input for the grade simulator.

    - `assumedScores` maps a task id to a percentage (0-100) to pretend you got.
    - `assumedRemainingPct` applies to every remaining ungraded task that isn't
      named in `assumedScores`.
    - `categoryWeights` is a fallback for syllabi where the LLM found no
      per-task weights. Weight is split evenly across tasks in each category.
    """

    assumedScores: Dict[str, float] = {}
    assumedRemainingPct: Optional[float] = None
    categoryWeights: List[CategoryWeight] = []
    targetPct: Optional[float] = None


class GradeBreakdownRow(BaseModel):
    taskId: str
    title: str
    type: str
    weightPct: float
    scorePct: Optional[float] = None
    source: Literal["actual", "assumed", "ungraded"] = "ungraded"


class GradeResult(BaseModel):
    currentPct: Optional[float] = None
    currentLetter: Optional[str] = None
    projectedPct: Optional[float] = None
    projectedLetter: Optional[str] = None
    gradedWeightPct: float = 0.0
    remainingWeightPct: float = 0.0
    neededOnRemainingPct: Optional[float] = None
    targetReachable: Optional[bool] = None
    weightSource: Literal["syllabus", "categories", "even"] = "even"
    warnings: List[str] = []
    breakdown: List[GradeBreakdownRow] = []
