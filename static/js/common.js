/* Shared helpers used by every panel: fetch wrapper, toast, time formatting. */

/**
 * Wrapper around fetch() for our own JSON API.
 * Always sends X-Requested-With so the backend's same-origin check
 * (app.py) can tell this apart from a cross-site request.
 */
async function apiFetch(path, options = {}) {
  const opts = {
    ...options,
    headers: {
      "X-Requested-With": "fetch",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  };
  const resp = await fetch(path, opts);
  let data = null;
  try {
    data = await resp.json();
  } catch (e) {
    data = null;
  }
  if (!resp.ok) {
    const message = (data && (data.message || data.error)) || `Request failed (${resp.status})`;
    const err = new Error(message);
    err.code = data && data.error; // e.g. "insufficient_scope", "not_connected"
    err.data = data || {};
    throw err;
  }
  return data;
}

function showToast(message, isError = false) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = message;
  el.classList.toggle("error", isError);
  el.classList.add("show");
  clearTimeout(showToast._t);
  // Errors stay up until dismissed (click) — easy to miss a 2.6s toast.
  if (isError) {
    el.onclick = () => el.classList.remove("show");
    return;
  }
  showToast._t = setTimeout(() => el.classList.remove("show"), 2600);
}

function formatDuration(totalSeconds) {
  totalSeconds = Math.max(0, Math.floor(totalSeconds || 0));
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m`;
  if (m > 0) return `${m}m ${String(s).padStart(2, "0")}s`;
  return `${s}s`;
}

function formatClock(totalSeconds) {
  totalSeconds = Math.max(0, Math.floor(totalSeconds || 0));
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function todayISO() {
  const d = new Date();
  const tzOffset = d.getTimezoneOffset() * 60000;
  return new Date(d - tzOffset).toISOString().slice(0, 10);
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}
