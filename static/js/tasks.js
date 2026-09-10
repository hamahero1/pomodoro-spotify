/* Task manager: add/start/stop/complete tasks, with subtasks. */

const Tasks = {
  list: [],

  init() {
    this.listEl = document.getElementById("task-list");
    this.formEl = document.getElementById("task-add-form");
    this.titleInput = document.getElementById("task-title-input");
    this.minutesInput = document.getElementById("task-minutes-input");
    this.dateInput = document.getElementById("task-date-input");

    this.formEl.addEventListener("submit", (e) => {
      e.preventDefault();
      this.createTask();
    });

    TaskDatePicker.init(this.dateInput);

    this.refresh();
  },

  async refresh() {
    try {
      this.list = await apiFetch("/api/tasks");
      this.render();
    } catch (e) {
      showToast("Couldn't load tasks: " + e.message, true);
    }
  },

  async createTask() {
    const title = this.titleInput.value.trim();
    if (!title) return;
    const estimated_minutes = this.minutesInput.value ? Number(this.minutesInput.value) : null;
    const date = this.dateInput.value || null;
    try {
      await apiFetch("/api/tasks", {
        method: "POST",
        body: JSON.stringify({ title, estimated_minutes, date }),
      });
      this.titleInput.value = "";
      this.minutesInput.value = "";
      TaskDatePicker.clear();
      await this.refresh();
      if (typeof Dashboard !== "undefined") Dashboard.refresh();
    } catch (e) {
      showToast("Couldn't add task: " + e.message, true);
    }
  },

  async createSubtask(parentId, title) {
    if (!title.trim()) return;
    try {
      await apiFetch("/api/tasks", {
        method: "POST",
        body: JSON.stringify({ title: title.trim(), parent_task_id: parentId }),
      });
      await this.refresh();
    } catch (e) {
      showToast("Couldn't add subtask: " + e.message, true);
    }
  },

  async startTask(id, title) {
    try {
      await apiFetch(`/api/tasks/${id}/start`, { method: "POST" });
      window.AppState.activeTaskId = id;
      window.AppState.activeTaskTitle = title;
      await this.refresh();
    } catch (e) {
      showToast("Couldn't start task: " + e.message, true);
    }
  },

  async stopTask(id) {
    try {
      await apiFetch(`/api/tasks/${id}/stop`, { method: "POST" });
      if (window.AppState.activeTaskId === id) {
        window.AppState.activeTaskId = null;
        window.AppState.activeTaskTitle = null;
      }
      await this.refresh();
    } catch (e) {
      showToast("Couldn't stop task: " + e.message, true);
    }
  },

  async completeTask(id) {
    try {
      await apiFetch(`/api/tasks/${id}/complete`, { method: "POST" });
      if (window.AppState.activeTaskId === id) {
        window.AppState.activeTaskId = null;
        window.AppState.activeTaskTitle = null;
      }
      await this.refresh();
      if (typeof Dashboard !== "undefined") Dashboard.refresh();
    } catch (e) {
      showToast("Couldn't complete task: " + e.message, true);
    }
  },

  async deleteTask(id) {
    if (!confirm("Delete this task and all its subtasks?")) return;
    try {
      await apiFetch(`/api/tasks/${id}`, { method: "DELETE" });
      await this.refresh();
    } catch (e) {
      showToast("Couldn't delete task: " + e.message, true);
    }
  },

  render() {
    this.listEl.innerHTML = "";
    if (this.list.length === 0) {
      this.listEl.innerHTML = '<li class="task-empty" style="color:var(--text-faint);font-size:0.85rem;">No tasks yet — add one above.</li>';
      return;
    }
    this.list.forEach((task) => this.listEl.appendChild(this.renderTask(task)));
  },

  renderTask(task, isSubtask = false) {
    const li = document.createElement("li");
    li.className = "task-item";

    const row = document.createElement("div");
    row.className = "task-row";

    const title = document.createElement("span");
    title.className = "task-title" + (task.status === "done" ? " done" : "");
    title.textContent = task.title;
    title.title = task.title;

    const time = document.createElement("span");
    time.className = "task-time";
    time.textContent = formatDuration(task.total_logged_seconds);

    const badge = document.createElement("span");
    badge.className = "status-badge " + task.status;
    badge.textContent = task.status.replace("_", " ");

    const actions = document.createElement("div");
    actions.className = "task-actions";

    if (task.status !== "done") {
      if (task.status === "in_progress") {
        actions.appendChild(this.actionButton("Stop", () => this.stopTask(task.id)));
      } else {
        actions.appendChild(this.actionButton("Start", () => this.startTask(task.id, task.title)));
      }
      actions.appendChild(this.actionButton("Done", () => this.completeTask(task.id)));
    }
    actions.appendChild(this.actionButton("✕", () => this.deleteTask(task.id), "btn-danger"));

    row.append(title, time, badge, actions);
    li.appendChild(row);

    if (!isSubtask && task.subtasks && task.subtasks.length > 0) {
      const subList = document.createElement("ul");
      subList.className = "subtask-list";
      task.subtasks.forEach((sub) => subList.appendChild(this.renderTask(sub, true)));
      li.appendChild(subList);
    }

    if (!isSubtask) {
      const addRow = document.createElement("div");
      addRow.className = "add-subtask-row";
      const input = document.createElement("input");
      input.type = "text";
      input.placeholder = "+ Add subtask";
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          this.createSubtask(task.id, input.value);
          input.value = "";
        }
      });
      addRow.appendChild(input);
      li.appendChild(addRow);
    }

    return li;
  },

  actionButton(label, onClick, extraClass = "") {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn " + extraClass;
    btn.textContent = label;
    btn.addEventListener("click", onClick);
    return btn;
  },
};

/* A calendar-popup date picker for the task date field — click a day on a
 * real calendar grid instead of typing day/month/year into a native input. */
const TaskDatePicker = {
  selectedDate: null, // "YYYY-MM-DD" or null
  viewYear: new Date().getFullYear(),
  viewMonth: new Date().getMonth(),

  init(hiddenInput) {
    this.hiddenInput = hiddenInput;
    this.btn = document.getElementById("task-date-btn");
    this.popup = document.getElementById("task-date-popup");
    this.monthLabel = document.getElementById("task-date-month-label");
    this.gridEl = document.getElementById("task-date-grid");
    this.clearBtn = document.getElementById("task-date-clear");

    this.btn.addEventListener("click", (e) => {
      e.stopPropagation();
      this.popup.classList.toggle("hidden");
      if (!this.popup.classList.contains("hidden")) this.render();
    });
    document.getElementById("task-date-prev").addEventListener("click", () => this.changeMonth(-1));
    document.getElementById("task-date-next").addEventListener("click", () => this.changeMonth(1));
    this.clearBtn.addEventListener("click", () => {
      this.clear();
      this.popup.classList.add("hidden");
    });
    document.addEventListener("click", (e) => {
      if (!this.popup.contains(e.target) && e.target !== this.btn) {
        this.popup.classList.add("hidden");
      }
    });
  },

  changeMonth(delta) {
    this.viewMonth += delta;
    if (this.viewMonth < 0) {
      this.viewMonth = 11;
      this.viewYear -= 1;
    } else if (this.viewMonth > 11) {
      this.viewMonth = 0;
      this.viewYear += 1;
    }
    this.render();
  },

  select(dateStr) {
    this.selectedDate = dateStr;
    this.hiddenInput.value = dateStr;
    const d = new Date(dateStr + "T00:00:00");
    this.btn.textContent = "📅 " + d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
    this.popup.classList.add("hidden");
  },

  clear() {
    this.selectedDate = null;
    this.hiddenInput.value = "";
    this.btn.textContent = "📅 Date";
  },

  render() {
    const monthNames = [
      "January", "February", "March", "April", "May", "June",
      "July", "August", "September", "October", "November", "December",
    ];
    this.monthLabel.textContent = `${monthNames[this.viewMonth]} ${this.viewYear}`;

    this.gridEl.innerHTML = "";
    ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"].forEach((d) => {
      const el = document.createElement("div");
      el.className = "dow";
      el.textContent = d;
      this.gridEl.appendChild(el);
    });

    const firstDay = new Date(this.viewYear, this.viewMonth, 1);
    const startWeekday = firstDay.getDay();
    const daysInMonth = new Date(this.viewYear, this.viewMonth + 1, 0).getDate();
    const todayStr = todayISO();

    for (let i = 0; i < startWeekday; i++) {
      const el = document.createElement("div");
      el.className = "calendar-day empty";
      this.gridEl.appendChild(el);
    }
    for (let day = 1; day <= daysInMonth; day++) {
      const dateStr = `${this.viewYear}-${String(this.viewMonth + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
      const el = document.createElement("div");
      el.className = "calendar-day";
      if (dateStr === todayStr) el.classList.add("today");
      if (dateStr === this.selectedDate) el.classList.add("selected");
      el.textContent = day;
      el.addEventListener("click", () => this.select(dateStr));
      this.gridEl.appendChild(el);
    }
  },
};

document.addEventListener("DOMContentLoaded", () => Tasks.init());
