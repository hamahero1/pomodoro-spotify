/* Pomodoro timer: presets, custom duration, auto-cycling work/break. */

const SHORT_BREAK_MIN = 5;
const LONG_BREAK_MIN = 15;
const CYCLES_BEFORE_LONG_BREAK = 4;
const RING_RADIUS = 86;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

window.AppState = window.AppState || { activeTaskId: null };

const Timer = {
  mode: "work", // "work" | "break"
  workMinutes: 25,
  totalSeconds: 25 * 60,
  remainingSeconds: 25 * 60,
  running: false,
  intervalId: null,
  cyclesCompleted: 0,

  els: {},

  init() {
    this.els.time = document.getElementById("timer-time");
    this.els.phase = document.getElementById("timer-phase");
    this.els.cycles = document.getElementById("timer-cycles");
    this.els.ring = document.getElementById("timer-ring-progress");
    this.els.startBtn = document.getElementById("timer-start");
    this.els.pauseBtn = document.getElementById("timer-pause");
    this.els.resetBtn = document.getElementById("timer-reset");
    this.els.customInput = document.getElementById("timer-custom-minutes");
    this.els.linkedTask = document.getElementById("timer-linked-task");

    this.els.ring.style.strokeDasharray = `${RING_CIRCUMFERENCE}`;

    document.querySelectorAll(".preset-row .btn[data-minutes]").forEach((btn) => {
      btn.addEventListener("click", () => this.selectPreset(Number(btn.dataset.minutes), btn));
    });
    document.getElementById("timer-custom-apply").addEventListener("click", () => {
      const minutes = Number(this.els.customInput.value);
      if (minutes > 0 && minutes <= 300) {
        this.selectPreset(minutes, null);
      } else {
        showToast("Enter a duration between 1 and 300 minutes", true);
      }
    });

    this.els.startBtn.addEventListener("click", () => this.start());
    this.els.pauseBtn.addEventListener("click", () => this.pause());
    this.els.resetBtn.addEventListener("click", () => this.reset());

    this.render();
    this.updateLinkedTaskLabel();
    setInterval(() => this.updateLinkedTaskLabel(), 2000);
  },

  updateLinkedTaskLabel() {
    if (!this.els.linkedTask) return;
    const title = window.AppState.activeTaskTitle;
    this.els.linkedTask.textContent = title
      ? `Linked to task: ${title}`
      : "Not linked to a task (run standalone, or start a task to link it)";
  },

  selectPreset(minutes, btnEl) {
    if (this.running) this.pause();
    this.mode = "work";
    this.workMinutes = minutes;
    this.totalSeconds = minutes * 60;
    this.remainingSeconds = this.totalSeconds;
    document.querySelectorAll(".preset-row .btn[data-minutes]").forEach((b) => b.classList.remove("active"));
    if (btnEl) btnEl.classList.add("active");
    this.render();
  },

  start() {
    if (this.running) return;
    this.running = true;
    this.els.startBtn.disabled = true;
    this.els.pauseBtn.disabled = false;
    this.intervalId = setInterval(() => this.tick(), 1000);
  },

  pause() {
    this.running = false;
    clearInterval(this.intervalId);
    this.els.startBtn.disabled = false;
    this.els.pauseBtn.disabled = true;
  },

  reset() {
    this.pause();
    this.mode = "work";
    this.totalSeconds = this.workMinutes * 60;
    this.remainingSeconds = this.totalSeconds;
    this.render();
  },

  tick() {
    this.remainingSeconds -= 1;
    if (this.remainingSeconds <= 0) {
      this.completePhase();
      return;
    }
    this.render();
  },

  async completePhase() {
    const finishedMode = this.mode;
    const durationSeconds = this.totalSeconds;
    this.pause();

    this.notifyPhaseEnd(finishedMode);

    try {
      await apiFetch("/api/timer/session", {
        method: "POST",
        body: JSON.stringify({
          kind: finishedMode === "work" ? "pomodoro_work" : "pomodoro_break",
          duration_seconds: durationSeconds,
          task_id: finishedMode === "work" ? window.AppState.activeTaskId : null,
        }),
      });
    } catch (e) {
      // Non-fatal: the timer itself keeps working even if logging fails
      // (e.g. offline). We just won't see it on the dashboard.
    }

    if (finishedMode === "work") {
      this.cyclesCompleted += 1;
      const isLongBreak = this.cyclesCompleted % CYCLES_BEFORE_LONG_BREAK === 0;
      this.mode = "break";
      this.totalSeconds = (isLongBreak ? LONG_BREAK_MIN : SHORT_BREAK_MIN) * 60;
    } else {
      this.mode = "work";
      this.totalSeconds = this.workMinutes * 60;
    }
    this.remainingSeconds = this.totalSeconds;
    this.render();
    this.start();

    if (typeof Dashboard !== "undefined") Dashboard.refresh();
  },

  notifyPhaseEnd(finishedMode) {
    const label = finishedMode === "work" ? "Work session done — take a break!" : "Break's over — back to work.";
    showToast(label);
    try {
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.frequency.value = finishedMode === "work" ? 880 : 660;
      gain.gain.setValueAtTime(0.15, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.6);
      osc.start();
      osc.stop(audioCtx.currentTime + 0.6);
    } catch (e) {
      /* audio not available — silently skip */
    }
    if ("Notification" in window) {
      if (Notification.permission === "granted") {
        new Notification("Pomodoro Spotify", { body: label });
      } else if (Notification.permission !== "denied") {
        Notification.requestPermission();
      }
    }
  },

  render() {
    this.els.time.textContent = formatClock(this.remainingSeconds);
    this.els.phase.textContent = this.mode === "work" ? "Focus" : "Break";
    this.els.phase.classList.toggle("break", this.mode === "break");
    this.els.cycles.textContent = `${this.cyclesCompleted} session${this.cyclesCompleted === 1 ? "" : "s"} completed`;

    const progress = 1 - this.remainingSeconds / this.totalSeconds;
    const offset = RING_CIRCUMFERENCE * (1 - progress);
    this.els.ring.style.strokeDashoffset = `${offset}`;
  },
};

document.addEventListener("DOMContentLoaded", () => Timer.init());
