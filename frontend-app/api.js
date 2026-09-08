// Thin wrapper around the middle tier. Every call either returns data or
// throws with a message worth showing to a student.

const API = (() => {
  const base = () => window.SYLLASYNC_API || "http://127.0.0.1:8000";

  async function request(path, options = {}) {
    let response;
    try {
      response = await fetch(base() + path, options);
    } catch (err) {
      throw new Error("Can't reach the SyllaSync API. Is it running on " + base() + "?");
    }

    if (!response.ok) {
      let detail = `Request failed (${response.status})`;
      try {
        const body = await response.json();
        if (typeof body.detail === "string") detail = body.detail;
        else if (body.detail?.message) detail = body.detail.message;
      } catch (_) { /* non-JSON error body */ }
      throw new Error(detail);
    }

    return response.status === 204 ? null : response.json();
  }

  return {
    base,
    health: () => request("/health"),
    listSyllabi: () => request("/syllabi"),
    listTasks: (upcomingOnly = false) =>
      request(`/tasks${upcomingOnly ? "?upcomingOnly=true" : ""}`),
    tasksForSyllabus: (id) => request(`/syllabi/${id}/tasks`),
    deleteSyllabus: (id) => request(`/syllabi/${id}`, { method: "DELETE" }),
    setScore: (taskId, score) =>
      request(`/tasks/${taskId}/score`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ score }),
      }),
    grade: (id) => request(`/syllabi/${id}/grade`),
    simulate: (id, payload) =>
      request(`/syllabi/${id}/grade/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }),
    upload: (file) => {
      const form = new FormData();
      form.append("file", file);
      return request("/upload-syllabus/", { method: "POST", body: form });
    },
    calendarUrl: () => base() + "/calendar.ics",
    courseCalendarUrl: (id) => `${base()}/syllabi/${id}/calendar.ics`,
  };
})();

window.API = API;
