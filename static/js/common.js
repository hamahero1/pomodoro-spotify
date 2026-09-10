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

/**
 * Approximates an image's dominant color by downscaling it onto a tiny
 * canvas (the browser's own scaling does the averaging for us) and
 * averaging the resulting pixels, skipping near-white/near-black ones so
 * album art with plain-color borders/backgrounds doesn't wash out the
 * result. Resolves to an "r, g, b" string, or null if extraction wasn't
 * possible (CORS-blocked image, load failure, etc.) — callers should treat
 * null as "keep whatever color is already showing."
 */
function extractDominantColor(imageUrl) {
  return new Promise((resolve) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      try {
        const size = 24;
        const canvas = document.createElement("canvas");
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0, size, size);
        const { data } = ctx.getImageData(0, 0, size, size);

        let r = 0, g = 0, b = 0, count = 0;
        for (let i = 0; i < data.length; i += 4) {
          if (data[i + 3] < 200) continue; // skip transparent pixels
          const rr = data[i], gg = data[i + 1], bb = data[i + 2];
          const luminance = 0.299 * rr + 0.587 * gg + 0.114 * bb;
          if (luminance < 20 || luminance > 235) continue; // skip near-black/white
          r += rr; g += gg; b += bb; count++;
        }
        if (count === 0) {
          resolve(null);
          return;
        }
        resolve(`${Math.round(r / count)}, ${Math.round(g / count)}, ${Math.round(b / count)}`);
      } catch (e) {
        resolve(null); // canvas tainted by a non-CORS image, or similar
      }
    };
    img.onerror = () => resolve(null);
    img.src = imageUrl;
  });
}

// Live wall-clock in the topbar (the real current time — distinct from the
// Pomodoro countdown and the song's own timeline, both shown elsewhere).
(function startTopbarClock() {
  const el = document.getElementById("topbar-clock");
  if (!el) return;
  const render = () => {
    el.textContent = new Date().toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit",
      second: "2-digit",
    });
  };
  render();
  setInterval(render, 1000);
})();
