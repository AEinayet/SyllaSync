"""Grade calculation and what-if simulation.

Weighting is resolved in this order:
  1. weightPct on the tasks themselves (from the syllabus)
  2. category weights supplied by the user, split evenly within each category
  3. even split across every task
The chosen source is reported back so the UI can tell the student which one
was used instead of quietly presenting a guess as fact.
"""

from typing import Any, Dict, List, Tuple

from .models import CategoryWeight, GradeBreakdownRow, GradeResult, SimulationInput

LETTER_CUTOFFS: List[Tuple[float, str]] = [
    (93, "A"), (90, "A-"), (87, "B+"), (83, "B"), (80, "B-"),
    (77, "C+"), (73, "C"), (70, "C-"), (67, "D+"), (63, "D"), (60, "D-"),
]


def to_letter(pct: float | None) -> str | None:
    if pct is None:
        return None
    for cutoff, letter in LETTER_CUTOFFS:
        if pct >= cutoff:
            return letter
    return "F"


def _score_pct(task: Dict[str, Any]) -> float | None:
    """A task's actual score as a percentage, or None if it isn't graded yet."""
    score = task.get("score")
    if score is None:
        return None
    out_of = task.get("scoreOutOf") or task.get("points") or 100.0
    if not out_of:
        return None
    return max(0.0, (float(score) / float(out_of)) * 100.0)


def resolve_weights(
    tasks: List[Dict[str, Any]], category_weights: List[CategoryWeight]
) -> Tuple[Dict[str, float], str, List[str]]:
    """Return (taskId -> weightPct, source, warnings), normalised to sum to 100."""
    warnings: List[str] = []
    gradable = [t for t in tasks if t.get("type") != "READING"]
    if not gradable:
        return {}, "even", ["No gradable tasks found for this course."]

    from_syllabus = {
        str(t["id"]): float(t["weightPct"])
        for t in gradable
        if t.get("weightPct") is not None
    }

    if from_syllabus and len(from_syllabus) == len(gradable):
        weights, source = from_syllabus, "syllabus"
    elif category_weights:
        by_type: Dict[str, List[str]] = {}
        for t in gradable:
            by_type.setdefault(t.get("type") or "OTHER", []).append(str(t["id"]))
        weights, source = {}, "categories"
        for cw in category_weights:
            ids = by_type.get(cw.type, [])
            if not ids:
                warnings.append(f"No {cw.type} tasks, so its {cw.weightPct}% was redistributed.")
                continue
            for task_id in ids:
                weights[task_id] = cw.weightPct / len(ids)
        uncovered = [
            str(t["id"]) for t in gradable if str(t["id"]) not in weights
        ]
        if uncovered:
            warnings.append(
                f"{len(uncovered)} task(s) had no category weight and were left out."
            )
    else:
        even = 100.0 / len(gradable)
        weights = {str(t["id"]): even for t in gradable}
        source = "even"
        warnings.append(
            "The syllabus didn't give weights, so every task is counted equally. "
            "Set category weights for a real estimate."
        )

    total = sum(weights.values())
    if total <= 0:
        return {}, source, warnings + ["Weights summed to zero."]
    if abs(total - 100.0) > 0.5:
        warnings.append(f"Weights summed to {total:.1f}%, so they were scaled to 100%.")
        weights = {k: v * 100.0 / total for k, v in weights.items()}
    return weights, source, warnings


def compute(tasks: List[Dict[str, Any]], sim: SimulationInput) -> GradeResult:
    weights, source, warnings = resolve_weights(tasks, sim.categoryWeights)
    if not weights:
        return GradeResult(weightSource=source, warnings=warnings)

    rows: List[GradeBreakdownRow] = []
    earned_weighted = 0.0   # actual scores only
    graded_weight = 0.0
    projected_weighted = 0.0  # actual + assumed
    projected_weight = 0.0
    remaining_weight = 0.0

    for task in tasks:
        task_id = str(task["id"])
        weight = weights.get(task_id)
        if weight is None:
            continue

        actual = _score_pct(task)
        assumed = sim.assumedScores.get(task_id)
        if assumed is None and actual is None:
            assumed = sim.assumedRemainingPct

        if actual is not None:
            earned_weighted += weight * actual / 100.0
            graded_weight += weight
            projected_weighted += weight * actual / 100.0
            projected_weight += weight
            row_pct, row_source = actual, "actual"
        elif assumed is not None:
            projected_weighted += weight * assumed / 100.0
            projected_weight += weight
            remaining_weight += weight
            row_pct, row_source = assumed, "assumed"
        else:
            remaining_weight += weight
            row_pct, row_source = None, "ungraded"

        rows.append(
            GradeBreakdownRow(
                taskId=task_id,
                title=task.get("title") or "(untitled)",
                type=task.get("type") or "OTHER",
                weightPct=round(weight, 2),
                scorePct=None if row_pct is None else round(row_pct, 2),
                source=row_source,
            )
        )

    current = (earned_weighted / graded_weight * 100.0) if graded_weight > 0 else None
    projected = (projected_weighted / projected_weight * 100.0) if projected_weight > 0 else None

    needed = None
    reachable = None
    if sim.targetPct is not None:
        if remaining_weight <= 0:
            needed = None
            reachable = current is not None and current >= sim.targetPct
        else:
            # target = earned_weighted + remaining_weight * (needed/100)
            needed = (sim.targetPct - earned_weighted) / remaining_weight * 100.0
            reachable = needed <= 100.0
            needed = round(max(0.0, needed), 2)

    rows.sort(key=lambda r: -r.weightPct)
    return GradeResult(
        currentPct=None if current is None else round(current, 2),
        currentLetter=to_letter(current),
        projectedPct=None if projected is None else round(projected, 2),
        projectedLetter=to_letter(projected),
        gradedWeightPct=round(graded_weight, 2),
        remainingWeightPct=round(remaining_weight, 2),
        neededOnRemainingPct=needed,
        targetReachable=reachable,
        weightSource=source,
        warnings=warnings,
        breakdown=rows,
    )
