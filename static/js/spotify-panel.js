/* Spotify panel: connect flow, now-playing display, synced/plain lyrics
 * (with album-art fallback), and a playlist browser. */

const SpotifyPanel = {
  connected: false,
  pollTimer: null,
  tickerId: null,

  isPlaying: false,
  currentTrackId: null,
  syncedLines: null, // [{timeMs, text}] or null if this track has no synced lyrics
  activeLineIndex: -1,
  progressAtSync: 0,
  lastSyncAt: 0,

  init() {
    this.connectView = document.getElementById("spotify-connect");
    this.nowPlayingView = document.getElementById("spotify-now-playing");
    this.trackRow = document.querySelector("#spotify-now-playing .np-track");
    this.controlsRow = document.querySelector("#spotify-now-playing .np-controls");
    this.art = document.getElementById("np-art");
    this.title = document.getElementById("np-title");
    this.artist = document.getElementById("np-artist");
    this.lyricsBox = document.getElementById("lyrics-box");
    this.playPauseBtn = document.getElementById("np-play-pause");
    this.nextBtn = document.getElementById("np-next");
    this.prevBtn = document.getElementById("np-prev");
    this.playlistsBtn = document.getElementById("np-playlists-toggle");

    this.browser = document.getElementById("spotify-browser");
    this.browserTitle = document.getElementById("browser-title");
    this.browserList = document.getElementById("browser-list");
    this.browserBackBtn = document.getElementById("browser-back");
    this.browserCloseBtn = document.getElementById("browser-close");

    document.getElementById("spotify-connect-btn").addEventListener("click", () => {
      window.location.href = "/spotify/login";
    });

    this.playPauseBtn.addEventListener("click", () => this.controlPlayback(this.isPlaying ? "pause" : "play"));
    this.nextBtn.addEventListener("click", () => this.controlPlayback("next"));
    this.prevBtn.addEventListener("click", () => this.controlPlayback("previous"));

    this.playlistsBtn.addEventListener("click", () => this.openBrowser());
    this.browserCloseBtn.addEventListener("click", () => this.closeBrowser());
    this.browserBackBtn.addEventListener("click", () => this.showPlaylists());

    this.checkStatus();
    this.tickerId = setInterval(() => this.tickLyrics(), 400);
  },

  async checkStatus() {
    try {
      const data = await apiFetch("/api/spotify/status");
      this.connected = data.connected;
    } catch (e) {
      this.connected = false;
    }
    this.render();
    if (this.connected) {
      this.pollNowPlaying();
      clearInterval(this.pollTimer);
      this.pollTimer = setInterval(() => this.pollNowPlaying(), 6000);
    }
  },

  render() {
    this.connectView.classList.toggle("hidden", this.connected);
    this.nowPlayingView.classList.toggle("hidden", !this.connected);
  },

  async controlPlayback(action) {
    try {
      await apiFetch(`/api/spotify/player/${action}`, { method: "PUT" });
      setTimeout(() => this.pollNowPlaying(), 400);
    } catch (e) {
      showToast("Playback control failed — is Spotify open on a device?", true);
    }
  },

  async pollNowPlaying() {
    try {
      const data = await apiFetch("/api/lyrics/current");
      this.renderTrack(data);
    } catch (e) {
      if (e.message.includes("not_connected")) {
        this.connected = false;
        this.render();
        clearInterval(this.pollTimer);
      }
    }
  },

  renderTrack(data) {
    const track = data.track;
    if (!track) {
      this.currentTrackId = null;
      this.syncedLines = null;
      this.title.textContent = "Nothing playing";
      this.artist.textContent = "Press play on Spotify to get started";
      this.art.innerHTML = this.musicIconSVG();
      this.lyricsBox.classList.remove("lyrics-synced");
      this.lyricsBox.innerHTML = this.emptyLyricsHTML("Nothing playing right now.");
      this.isPlaying = false;
      this.playPauseBtn.textContent = "▶";
      return;
    }

    this.isPlaying = track.is_playing;
    this.playPauseBtn.textContent = track.is_playing ? "⏸" : "▶";
    this.title.textContent = track.title;
    this.artist.textContent = track.artist;

    if (track.album_art_url) {
      this.art.innerHTML = `<img src="${track.album_art_url}" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:inherit;">`;
    } else {
      this.art.innerHTML = this.musicIconSVG();
    }

    // Keep the lyrics view in sync with real playback position, even
    // though we only poll every few seconds (tickLyrics interpolates
    // between polls using elapsed wall-clock time).
    this.progressAtSync = track.progress_ms || 0;
    this.lastSyncAt = Date.now();

    const trackChanged = track.track_id !== this.currentTrackId;
    this.currentTrackId = track.track_id;

    if (!trackChanged) return; // don't rebuild the DOM every poll for the same track

    this.activeLineIndex = -1;

    if (data.lyrics && data.lyrics.synced_lyrics) {
      this.syncedLines = this.parseSyncedLyrics(data.lyrics.synced_lyrics);
      this.renderSyncedLyricsLines();
    } else if (data.found && data.lyrics && data.lyrics.plain_lyrics) {
      this.syncedLines = null;
      this.lyricsBox.classList.remove("lyrics-synced");
      this.lyricsBox.textContent = data.lyrics.plain_lyrics;
    } else {
      this.syncedLines = null;
      this.lyricsBox.classList.remove("lyrics-synced");
      const reason = data.lyrics && data.lyrics.instrumental ? "This track is instrumental." : "No lyrics found for this track.";
      // No lyrics at all for this track — show the album art large instead
      // of just a small icon, since there's nothing else to look at.
      this.lyricsBox.innerHTML = this.noLyricsFallbackHTML(track.album_art_url, reason);
    }
  },

  parseSyncedLyrics(lrcText) {
    const lineRegex = /\[(\d{1,2}):(\d{2}(?:\.\d{1,2})?)\]/g;
    const lines = [];
    lrcText.split("\n").forEach((raw) => {
      const matches = [...raw.matchAll(lineRegex)];
      if (matches.length === 0) return;
      const text = raw.replace(lineRegex, "").trim();
      if (!text) return;
      matches.forEach((m) => {
        const minutes = parseInt(m[1], 10);
        const seconds = parseFloat(m[2]);
        lines.push({ timeMs: (minutes * 60 + seconds) * 1000, text });
      });
    });
    return lines.sort((a, b) => a.timeMs - b.timeMs);
  },

  renderSyncedLyricsLines() {
    this.lyricsBox.classList.add("lyrics-synced");
    this.lyricsBox.innerHTML = "";
    this._activeWordEl = null;
    this.syncedLines.forEach((line) => {
      const div = document.createElement("div");
      div.className = "lyric-line";
      // Split into words (keeping whitespace as plain text nodes, so spacing
      // is preserved) — this lets us highlight just the current WORD rather
      // than lighting up the entire line as one solid block.
      line.text.split(/(\s+)/).forEach((token) => {
        if (token.trim() === "") {
          div.appendChild(document.createTextNode(token));
        } else {
          const span = document.createElement("span");
          span.className = "lyric-word";
          span.textContent = token;
          div.appendChild(span);
        }
      });
      this.lyricsBox.appendChild(div);
    });
  },

  tickLyrics() {
    if (!this.syncedLines || this.syncedLines.length === 0 || !this.isPlaying) return;
    const estimatedMs = this.progressAtSync + (Date.now() - this.lastSyncAt);

    let idx = -1;
    for (let i = 0; i < this.syncedLines.length; i++) {
      if (this.syncedLines[i].timeMs <= estimatedMs) idx = i;
      else break;
    }
    if (idx < 0) return;

    const lines = this.lyricsBox.children;
    if (idx !== this.activeLineIndex) {
      this.activeLineIndex = idx;
      for (let i = 0; i < lines.length; i++) {
        lines[i].classList.toggle("current-line", i === idx);
      }
      if (lines[idx]) lines[idx].scrollIntoView({ block: "center", behavior: "smooth" });
    }

    // lrclib only gives one timestamp per LINE, not per word — so we
    // estimate the current word by assuming words are evenly spaced across
    // the time until the next line starts (a common karaoke approximation
    // when word-level timing isn't available).
    const lineEl = lines[idx];
    if (!lineEl) return;
    const words = lineEl.querySelectorAll(".lyric-word");
    if (words.length === 0) return;

    const lineStart = this.syncedLines[idx].timeMs;
    const lineEnd = idx + 1 < this.syncedLines.length ? this.syncedLines[idx + 1].timeMs : lineStart + 4000;
    const fraction = Math.max(0, Math.min(1, (estimatedMs - lineStart) / Math.max(1, lineEnd - lineStart)));
    const activeWordIdx = Math.min(words.length - 1, Math.floor(fraction * words.length));
    const activeWordEl = words[activeWordIdx];

    if (activeWordEl === this._activeWordEl) return;
    if (this._activeWordEl) this._activeWordEl.classList.remove("active-word");
    activeWordEl.classList.add("active-word");
    this._activeWordEl = activeWordEl;
  },

  emptyLyricsHTML(message) {
    return `<div class="lyrics-empty">${this.musicIconSVG(true)}<span>${escapeHtml(message)}</span></div>`;
  },

  noLyricsFallbackHTML(albumArtUrl, reason) {
    if (albumArtUrl) {
      return `
        <div class="lyrics-empty lyrics-empty-photo">
          <img src="${albumArtUrl}" alt="Album art" class="lyrics-fallback-art">
          <span>${escapeHtml(reason)}</span>
        </div>`;
    }
    return this.emptyLyricsHTML(reason);
  },

  musicIconSVG(standalone = false) {
    return `<svg viewBox="0 0 24 24"${standalone ? "" : ' style="width:24px;height:24px;"'}><path fill="currentColor" d="M12 3v10.55A4 4 0 1 0 14 17V7h4V3h-6z"/></svg>`;
  },

  // ---- Playlist browser ---------------------------------------------

  openBrowser() {
    this.trackRow.classList.add("hidden");
    this.controlsRow.classList.add("hidden");
    this.lyricsBox.classList.add("hidden");
    this.browser.classList.remove("hidden");
    this.showPlaylists();
  },

  closeBrowser() {
    this.browser.classList.add("hidden");
    this.trackRow.classList.remove("hidden");
    this.controlsRow.classList.remove("hidden");
    this.lyricsBox.classList.remove("hidden");
  },

  async showPlaylists() {
    this.browserTitle.textContent = "Your Playlists";
    this.browserBackBtn.style.display = "none";
    this.browserList.innerHTML = '<li class="browser-loading">Loading…</li>';
    try {
      const data = await apiFetch("/api/spotify/playlists");
      this.renderPlaylistList(data.playlists);
    } catch (e) {
      this.renderBrowserError(e);
    }
  },

  renderBrowserError(e) {
    if (e.code === "insufficient_scope") {
      this.browserList.innerHTML = `
        <li class="browser-loading">
          This needs permissions your current session doesn't have yet.
          <button id="browser-reconnect" class="btn btn-primary" type="button" style="margin-top:0.6rem;">Reconnect Spotify</button>
        </li>`;
      document.getElementById("browser-reconnect").addEventListener("click", () => {
        // Force Spotify's consent screen so the new (playlist) scope is
        // actually re-prompted, instead of possibly reusing an old grant.
        window.location.href = "/spotify/login?show_dialog=true";
      });
      return;
    }
    this.browserList.innerHTML = `<li class="browser-loading">Couldn't load this: ${escapeHtml(e.message)}</li>`;
  },

  renderPlaylistList(playlists) {
    this.browserList.innerHTML = "";
    if (playlists.length === 0) {
      this.browserList.innerHTML = '<li class="browser-loading">No playlists found.</li>';
      return;
    }
    playlists.forEach((pl) => {
      const li = document.createElement("li");
      li.className = "browser-item";
      li.innerHTML = `
        ${pl.image_url ? `<img src="${pl.image_url}" alt="">` : `<span class="browser-item-icon">${this.musicIconSVG()}</span>`}
        <span>
          <div class="bi-title">${escapeHtml(pl.name)}</div>
          <div class="bi-sub">${pl.track_count} song${pl.track_count === 1 ? "" : "s"}</div>
        </span>`;
      li.addEventListener("click", () => this.showTracks(pl.id, pl.name));
      this.browserList.appendChild(li);
    });
  },

  async showTracks(playlistId, playlistName) {
    this.browserTitle.textContent = playlistName;
    this.browserBackBtn.style.display = "";
    this.browserList.innerHTML = '<li class="browser-loading">Loading…</li>';
    try {
      const data = await apiFetch(`/api/spotify/playlists/${encodeURIComponent(playlistId)}/tracks`);
      this.renderTrackList(data.tracks);
    } catch (e) {
      this.renderBrowserError(e);
    }
  },

  renderTrackList(tracks) {
    this.browserList.innerHTML = "";
    if (tracks.length === 0) {
      this.browserList.innerHTML = '<li class="browser-loading">No playable songs in this playlist.</li>';
      return;
    }
    tracks.forEach((t) => {
      const li = document.createElement("li");
      li.className = "browser-item";
      li.innerHTML = `
        ${t.album_art_url ? `<img src="${t.album_art_url}" alt="">` : `<span class="browser-item-icon">${this.musicIconSVG()}</span>`}
        <span>
          <div class="bi-title">${escapeHtml(t.title)}</div>
          <div class="bi-sub">${escapeHtml(t.artist)}</div>
        </span>`;
      li.addEventListener("click", () => this.playTrack(t.uri));
      this.browserList.appendChild(li);
    });
  },

  async playTrack(uri) {
    try {
      await apiFetch("/api/spotify/player/play-track", {
        method: "PUT",
        body: JSON.stringify({
          uri,
          device_id: typeof SpotifyPlayer !== "undefined" ? SpotifyPlayer.deviceId : null,
        }),
      });
      this.closeBrowser();
      setTimeout(() => this.pollNowPlaying(), 500);
    } catch (e) {
      showToast("Couldn't play that song — is Spotify open on a device? " + e.message, true);
    }
  },
};

document.addEventListener("DOMContentLoaded", () => SpotifyPanel.init());
