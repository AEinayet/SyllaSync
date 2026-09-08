// Dashboard + upload behaviour. Everything shown comes from the API; there is
// no simulated data and no fake success path.

window.addEventListener("DOMContentLoaded", () => {
  const pad2 = (n) => String(n).padStart(2, "0");
  const toKey = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
  const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const mondayIndex = (d) => (d.getDay() + 6) % 7;

  const monthNames = ["January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"];
  const weekdayShort = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  const TASK_ICONS = {
    HOMEWORK: "fa-book", PROJECT: "fa-diagram-project", EXAM: "fa-file-pen",
    QUIZ: "fa-clipboard-question", READING: "fa-book-open", OTHER: "fa-list-check",
  };

  const escapeHtml = (s) => String(s ?? "").replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const dayKeyOf = (task) => (task.dueAt ? task.dueAt.slice(0, 10) : null);

  const formatDue = (iso) => {
    if (!iso) return "No due date";
    const due = new Date(iso.length === 10 ? `${iso}T23:59:59` : iso);
    if (Number.isNaN(due.getTime())) return iso;
    const days = Math.round((startOfDay(due) - startOfDay(new Date())) / 86400000);
    const time = due.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    if (days === 0) return `Due today, ${time}`;
    if (days === 1) return `Due tomorrow, ${time}`;
    if (days < 0) return `Past due ${Math.abs(days)}d ago`;
    if (days <= 7) return `Due in ${days} days`;
    return `Due ${due.toLocaleDateString([], { month: "short", day: "numeric" })}`;
  };

  const urgencyOf = (iso) => {
    if (!iso) return "";
    const days = Math.round(
      (startOfDay(new Date(iso.length === 10 ? `${iso}T23:59:59` : iso)) - startOfDay(new Date()))
      / 86400000
    );
    if (days < 0) return "Overdue";
    if (days === 0) return "Urgent";
    if (days <= 2) return "Soon";
    return "";
  };

  // ------------------------------------------------------------- dashboard

  const monthLabel = document.getElementById("monthLabel");
  const weekView = document.getElementById("weekView");
  const monthView = document.getElementById("monthView");
  const dayPanel = document.getElementById("day-panel");
  const dayPanelTitle = document.getElementById("day-panel-title");
  const dayPanelBody = document.getElementById("day-panel-body");
  const courseStrip = document.getElementById("course-strip");
  const assignmentList = document.getElementById("assignment-list");
  const assignmentCount = document.getElementById("assignment-count");
  const banner = document.getElementById("banner");

  const isDashboard = Boolean(weekView && monthView);

  let allTasks = [];
  let tasksByDay = new Map();
  let selected = startOfDay(new Date());

  const showBanner = (message, kind = "error") => {
    if (!banner) return;
    banner.className = `banner ${kind}`;
    banner.innerHTML = `<i class="fa-solid ${kind === "error" ? "fa-triangle-exclamation" : "fa-circle-info"}"></i><span>${escapeHtml(message)}</span>`;
    banner.style.display = "flex";
  };
  const hideBanner = () => { if (banner) banner.style.display = "none"; };

  const indexTasks = (tasks) => {
    const map = new Map();
    tasks.forEach((t) => {
      const key = dayKeyOf(t);
      if (!key) return;
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(t);
    });
    return map;
  };

  const renderWeek = () => {
    const monday = new Date(selected);
    monday.setDate(selected.getDate() - mondayIndex(selected));
    weekView.innerHTML = "";

    for (let i = 0; i < 7; i++) {
      const d = new Date(monday);
      d.setDate(monday.getDate() + i);
      const key = toKey(d);

      const capsule = document.createElement("div");
      capsule.className = `day-capsule${key === toKey(selected) ? " active" : ""}${tasksByDay.has(key) ? " has-event" : ""}`;
      capsule.dataset.date = key;
      capsule.innerHTML = `<span class="day-name">${weekdayShort[i]}</span>
        <span class="date-num">${d.getDate()}</span><div class="has-class-dot"></div>`;
      capsule.addEventListener("click", () => selectDay(d));
      weekView.appendChild(capsule);
    }
  };

  const renderMonth = () => {
    const year = selected.getFullYear();
    const month = selected.getMonth();
    if (monthLabel) monthLabel.textContent = `${monthNames[month]} ${year}`;

    const firstOfMonth = new Date(year, month, 1);
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const leading = mondayIndex(firstOfMonth);
    const totalCells = Math.ceil((leading + daysInMonth) / 7) * 7;
    const gridStart = new Date(year, month, 1 - leading);

    monthView.innerHTML = `<div class="week-days-header">
      <span>M</span><span>T</span><span>W</span><span>T</span><span>F</span><span>S</span><span>S</span>
    </div><div class="month-grid"></div>`;
    const grid = monthView.querySelector(".month-grid");

    for (let i = 0; i < totalCells; i++) {
      const d = new Date(gridStart);
      d.setDate(gridStart.getDate() + i);
      const key = toKey(d);
      const inThisMonth = d.getMonth() === month;
      const hasEvent = tasksByDay.has(key);

      const cell = document.createElement("div");
      cell.className = `month-day${inThisMonth ? "" : " other-month"}${hasEvent ? " has-event" : ""}${key === toKey(selected) ? " active" : ""}`;
      cell.dataset.date = key;
      cell.innerHTML = `${d.getDate()}${hasEvent ? '<div class="dot"></div>' : ""}`;
      cell.addEventListener("click", () => selectDay(d));
      grid.appendChild(cell);
    }
  };

  const renderDayPanel = () => {
    if (!dayPanel) return;
    const key = toKey(selected);
    const items = tasksByDay.get(key) || [];
    const isToday = key === toKey(new Date());

    dayPanelTitle.textContent = isToday
      ? "Due today"
      : `Due ${selected.toLocaleDateString([], { weekday: "long", month: "short", day: "numeric" })}`;

    if (!items.length) {
      dayPanelBody.innerHTML = `<div class="event-card empty">Nothing due this day</div>`;
      return;
    }

    dayPanelBody.innerHTML = items.map((t) => {
      const time = t.dueAt && t.dueAt.length > 10
        ? new Date(t.dueAt).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
        : "11:59 PM";
      const cardClass = t.type === "EXAM" || t.type === "QUIZ" ? "lab" : "lecture";
      return `<div class="timeline-item">
          <div class="time-col">${escapeHtml(time)}</div>
          <div class="event-card ${cardClass}">
            <div class="event-title">${escapeHtml(t.title)}</div>
            <div class="event-meta">
              <span><i class="fa-solid fa-graduation-cap"></i> ${escapeHtml(t.courseCode || "Course")}</span>
              ${t.weightPct != null ? `<span><i class="fa-solid fa-percent"></i> ${t.weightPct}% of grade</span>` : ""}
            </div>
          </div>
        </div>`;
    }).join("");
  };

  const selectDay = (date) => {
    selected = startOfDay(date);
    renderWeek();
    renderMonth();
    renderDayPanel();
  };

  const renderCourses = (syllabi) => {
    if (!courseStrip) return;
    if (!syllabi.length) {
      courseStrip.innerHTML = `<a href="pdfSubmission.html" class="course-chip add">
        <i class="fa-solid fa-plus"></i> Add your first syllabus</a>`;
      return;
    }
    courseStrip.innerHTML = syllabi.map((s) => {
      const label = s.course.code || s.course.title || s.filename || "Untitled course";
      return `<a class="course-chip" href="grades.html?syllabus=${encodeURIComponent(s.id)}">
        <span class="course-chip-code">${escapeHtml(label)}</span>
        <span class="course-chip-meta">${s.taskCount} deadline${s.taskCount === 1 ? "" : "s"}</span>
      </a>`;
    }).join("") + `<a href="pdfSubmission.html" class="course-chip add"><i class="fa-solid fa-plus"></i> Add</a>`;
  };

  const renderAssignments = () => {
    if (!assignmentList) return;
    const today = toKey(new Date());
    const upcoming = allTasks
      .filter((t) => t.dueAt && t.dueAt.slice(0, 10) >= today && t.type !== "READING")
      .slice(0, 6);

    if (assignmentCount) {
      assignmentCount.textContent = `${upcoming.length} upcoming`;
    }

    if (!upcoming.length) {
      assignmentList.innerHTML = `<div class="event-card empty">
        No upcoming deadlines. Upload a syllabus to fill this in.</div>`;
      return;
    }

    assignmentList.innerHTML = upcoming.map((t) => {
      const urgency = urgencyOf(t.dueAt);
      return `<div class="assignment-row">
        <div class="assign-icon"><i class="fa-solid ${TASK_ICONS[t.type] || TASK_ICONS.OTHER}"></i></div>
        <div class="assign-info">
          <h4>${escapeHtml(t.title)}</h4>
          <p>${escapeHtml(t.courseCode || "Course")} &middot; ${escapeHtml(formatDue(t.dueAt))}</p>
        </div>
        ${urgency ? `<div class="assign-status ${urgency.toLowerCase()}">${urgency}</div>` : ""}
      </div>`;
    }).join("");
  };

  const loadDashboard = async () => {
    try {
      const [syllabi, tasks] = await Promise.all([API.listSyllabi(), API.listTasks()]);
      hideBanner();
      allTasks = tasks;
      tasksByDay = indexTasks(tasks);

      const failed = syllabi.filter((s) => s.extractionError);
      if (failed.length) {
        showBanner(`${failed.length} syllabus upload didn't extract cleanly. Open the course to add its deadlines by hand.`, "warn");
      }

      renderCourses(syllabi);
      renderAssignments();
      selectDay(selected);
    } catch (err) {
      showBanner(err.message);
      renderCourses([]);
      renderAssignments();
      selectDay(selected);
    }
  };

  if (isDashboard) {
    loadDashboard();

    const toggleBtn = document.getElementById("viewToggleBtn");
    if (toggleBtn) {
      let isMonthView = false;
      toggleBtn.addEventListener("click", () => {
        isMonthView = !isMonthView;
        weekView.style.display = isMonthView ? "none" : "flex";
        monthView.style.display = isMonthView ? "block" : "none";
        toggleBtn.textContent = isMonthView ? "View week" : "View month";
      });
    }

    const syncBtn = document.getElementById("syncBtn");
    const syncSheet = document.getElementById("sync-sheet");
    if (syncBtn && syncSheet) {
      const urlField = document.getElementById("sync-url");
      const downloadLink = document.getElementById("sync-download");
      syncBtn.addEventListener("click", () => {
        urlField.value = API.calendarUrl();
        downloadLink.href = API.calendarUrl();
        syncSheet.style.display = "flex";
      });
      document.getElementById("sync-close")?.addEventListener("click", () => {
        syncSheet.style.display = "none";
      });
      document.getElementById("sync-copy")?.addEventListener("click", async () => {
        await navigator.clipboard.writeText(urlField.value);
        const btn = document.getElementById("sync-copy");
        btn.textContent = "Copied";
        setTimeout(() => { btn.textContent = "Copy link"; }, 1500);
      });
    }

    // Keep the calendar honest across midnight without a full reload.
    const scheduleMidnightRefresh = () => {
      const now = new Date();
      const next = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 0, 0, 5);
      setTimeout(() => { loadDashboard(); scheduleMidnightRefresh(); }, next - now);
    };
    scheduleMidnightRefresh();
  }

  // ---------------------------------------------------------------- upload

  const fileInput = document.getElementById("file-input");
  const filePreview = document.getElementById("file-preview");
  const fileName = document.getElementById("file-name");
  const submitBtn = document.getElementById("submit-btn");
  const uploadStatus = document.getElementById("upload-status");

  if (fileInput && submitBtn) {
    const setStatus = (message, kind) => {
      if (!uploadStatus) return;
      uploadStatus.className = `upload-status ${kind}`;
      uploadStatus.textContent = message;
      uploadStatus.style.display = message ? "block" : "none";
    };

    fileInput.addEventListener("change", function () {
      const file = this.files?.[0];
      if (!file) return;
      fileName.textContent = file.name;
      filePreview.style.display = "flex";
      submitBtn.classList.add("active");
      setStatus("", "");
    });

    submitBtn.addEventListener("click", async () => {
      const file = fileInput.files?.[0];
      if (!file) {
        setStatus("Choose a syllabus file first.", "error");
        return;
      }

      submitBtn.textContent = "Reading your syllabus…";
      submitBtn.disabled = true;
      setStatus("This takes a few seconds while the deadlines are extracted.", "info");

      try {
        const result = await API.upload(file);
        const course = result.course?.code || result.course?.title || file.name;
        setStatus(`Found ${result.taskCount} deadlines in ${course}. Opening your calendar…`, "success");
        setTimeout(() => { window.location.href = "mainScreen.html"; }, 900);
      } catch (err) {
        // No fallback. If it failed, the student needs to know it failed.
        setStatus(err.message, "error");
        submitBtn.textContent = "Try again";
        submitBtn.disabled = false;
      }
    });
  }
});
