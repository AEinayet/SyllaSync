// Grade page: record scores, see where you stand, and run what-if scenarios.

window.addEventListener("DOMContentLoaded", () => {
  const syllabusId = new URLSearchParams(location.search).get("syllabus");
  const el = (id) => document.getElementById(id);
  const escapeHtml = (s) => String(s ?? "").replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const showBanner = (message, kind = "error") => {
    const banner = el("banner");
    banner.className = `banner ${kind}`;
    banner.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i><span>${escapeHtml(message)}</span>`;
    banner.style.display = "flex";
  };

  if (!syllabusId) {
    showBanner("No course selected. Pick one from the dashboard.");
    return;
  }

  let tasks = [];
  let debounce;

  const renderGrade = (result) => {
    el("grade-letter").textContent = result.currentLetter || "–";
    el("grade-pct").textContent = result.currentPct == null
      ? "Enter a score below to see where you stand"
      : `${result.currentPct}% on ${result.gradedWeightPct}% of the grade`;

    el("grade-bar-fill").style.width = `${Math.min(100, result.gradedWeightPct)}%`;

    const notes = [...result.warnings];
    if (result.weightSource === "syllabus") {
      notes.unshift("Weights came from your syllabus.");
    }
    el("grade-legend").innerHTML = notes.map((n) => `<p>${escapeHtml(n)}</p>`).join("");
  };

  const renderSimulation = (result) => {
    const parts = [];
    if (result.projectedPct != null) {
      parts.push(`<strong>${result.projectedPct}% (${result.projectedLetter})</strong> if the rest goes as assumed.`);
    }
    if (result.neededOnRemainingPct != null) {
      parts.push(result.targetReachable
        ? `You need <strong>${result.neededOnRemainingPct}%</strong> on the remaining ${result.remainingWeightPct}% to hit your target.`
        : `That target needs <strong>${result.neededOnRemainingPct}%</strong> on what's left, which is out of reach.`);
    } else if (result.targetReachable === false) {
      parts.push("Nothing is left to grade, so that target is locked in already.");
    }
    el("sim-result").innerHTML = parts.join(" ") || "Record a score to start projecting.";
  };

  const renderTasks = () => {
    el("task-scores").innerHTML = tasks.map((t) => {
      const outOf = t.scoreOutOf || t.points || 100;
      return `<div class="assignment-row score-row">
        <div class="assign-info">
          <h4>${escapeHtml(t.title)}</h4>
          <p>${escapeHtml(t.type)}${t.weightPct != null ? ` &middot; ${t.weightPct}% of grade` : ""}</p>
        </div>
        <div class="score-input">
          <input type="number" min="0" step="any" data-task="${t.id}"
                 value="${t.score ?? ""}" placeholder="–">
          <span>/ ${outOf}</span>
        </div>
      </div>`;
    }).join("") || `<div class="event-card empty">This course has no graded items yet.</div>`;

    document.querySelectorAll(".score-input input").forEach((input) => {
      input.addEventListener("change", async () => {
        const raw = input.value.trim();
        try {
          await API.setScore(input.dataset.task, raw === "" ? null : Number(raw));
          await refresh();
        } catch (err) {
          showBanner(err.message);
        }
      });
    });
  };

  const runSimulation = async () => {
    const assumed = Number(el("assumed").value);
    const target = Number(el("target").value);
    try {
      const result = await API.simulate(syllabusId, {
        assumedRemainingPct: Number.isFinite(assumed) ? assumed : null,
        targetPct: Number.isFinite(target) ? target : null,
      });
      renderSimulation(result);
    } catch (err) {
      showBanner(err.message);
    }
  };

  const refresh = async () => {
    const [fresh, grade] = await Promise.all([
      API.tasksForSyllabus(syllabusId),
      API.grade(syllabusId),
    ]);
    tasks = fresh;
    renderTasks();
    renderGrade(grade);
    await runSimulation();
  };

  const load = async () => {
    try {
      const syllabi = await API.listSyllabi();
      const course = syllabi.find((s) => s.id === syllabusId);
      if (course) {
        el("course-title").textContent =
          course.course.code || course.course.title || "Grades";
      }
      el("course-ics").href = API.courseCalendarUrl(syllabusId);
      await refresh();
    } catch (err) {
      showBanner(err.message);
    }
  };

  ["assumed", "target"].forEach((id) => {
    el(id).addEventListener("input", () => {
      clearTimeout(debounce);
      debounce = setTimeout(runSimulation, 250);
    });
  });

  load();
});
