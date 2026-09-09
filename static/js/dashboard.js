/* Dashboard: summary stats + calendar-by-date view. */

const Dashboard = {
  viewYear: new Date().getFullYear(),
  viewMonth: new Date().getMonth(), // 0-indexed
  selectedDate: todayISO(),
  daysWithActivity: new Set(),

  init() {
    this.statCompleted = document.getElementById("stat-completed");
    this.statToday = document.getElementById("stat-today");
    this.statTotalTime = document.getElementById("stat-total-time");
    this.monthLabel = document.getElementById("calendar-month-label");
    this.gridEl = document.getElementById("calendar-grid");
    this.dayDetailEl = document.getElementById("day-detail");

    document.getElementById("calendar-prev").addEventListener("click", () => this.changeMonth(-1));
    document.getElementById("calendar-next").addEventListener("click", () => this.changeMonth(1));

    this.refresh();
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
    this.renderCalendar();
  },

  async refresh() {
    try {
      const summary = await apiFetch("/api/dashboard/summary");
      this.statCompleted.textContent = summary.completed_count;
      this.statToday.textContent = summary.completed_today;
      this.statTotalTime.textContent = formatDuration(summary.total_seconds);

      this.daysWithActivity = new Set(
        summary.last_14_days.filter((d) => d.total_seconds > 0).map((d) => d.date)
      );
    } catch (e) {
      showToast("Couldn't load dashboard: " + e.message, true);
    }
    this.renderCalendar();
    this.loadDayDetail(this.selectedDate);
  },

  renderCalendar() {
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
      if (this.daysWithActivity.has(dateStr)) {
        const dot = document.createElement("span");
        dot.className = "dot";
        el.appendChild(dot);
      }
      el.addEventListener("click", () => {
        this.selectedDate = dateStr;
        this.renderCalendar();
        this.loadDayDetail(dateStr);
      });
      this.gridEl.appendChild(el);
    }
  },

  async loadDayDetail(dateStr) {
    try {
      const data = await apiFetch(`/api/dashboard/calendar?date=${encodeURIComponent(dateStr)}`);
      const title = document.createElement("div");
      title.className = "day-detail-title";
      title.textContent = `${dateStr} — ${formatDuration(data.total_seconds)} logged`;

      this.dayDetailEl.innerHTML = "";
      this.dayDetailEl.appendChild(title);

      if (data.tasks.length === 0) {
        const empty = document.createElement("div");
        empty.textContent = "No tasks scheduled for this day.";
        this.dayDetailEl.appendChild(empty);
        return;
      }
      const ul = document.createElement("ul");
      data.tasks.forEach((t) => {
        const li = document.createElement("li");
        li.textContent = `${t.title} (${t.status.replace("_", " ")})`;
        ul.appendChild(li);
      });
      this.dayDetailEl.appendChild(ul);
    } catch (e) {
      this.dayDetailEl.textContent = "Couldn't load that day.";
    }
  },
};

document.addEventListener("DOMContentLoaded", () => Dashboard.init());
