/* Spotify panel: connect flow, now-playing display, lyrics (with icon fallback). */

const SpotifyPanel = {
  connected: false,
  pollTimer: null,

  init() {
    this.connectView = document.getElementById("spotify-connect");
    this.nowPlayingView = document.getElementById("spotify-now-playing");
    this.art = document.getElementById("np-art");
    this.title = document.getElementById("np-title");
    this.artist = document.getElementById("np-artist");
    this.lyricsBox = document.getElementById("lyrics-box");
    this.playPauseBtn = document.getElementById("np-play-pause");
    this.nextBtn = document.getElementById("np-next");
    this.prevBtn = document.getElementById("np-prev");
    this.isPlaying = false;

    document.getElementById("spotify-connect-btn").addEventListener("click", () => {
      window.location.href = "/spotify/login";
    });

    this.playPauseBtn.addEventListener("click", () => this.controlPlayback(this.isPlaying ? "pause" : "play"));
    this.nextBtn.addEventListener("click", () => this.controlPlayback("next"));
    this.prevBtn.addEventListener("click", () => this.controlPlayback("previous"));

    this.checkStatus();
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
      this.title.textContent = "Nothing playing";
      this.artist.textContent = "Press play on Spotify to get started";
      this.art.innerHTML = this.musicIconSVG();
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

    if (data.found && data.lyrics && data.lyrics.plain_lyrics) {
      this.lyricsBox.classList.remove("lyrics-empty");
      this.lyricsBox.textContent = data.lyrics.plain_lyrics;
    } else {
      const reason = data.lyrics && data.lyrics.instrumental ? "This track is instrumental." : "No lyrics found for this track.";
      this.lyricsBox.innerHTML = this.emptyLyricsHTML(reason);
    }
  },

  emptyLyricsHTML(message) {
    return `<div class="lyrics-empty">${this.musicIconSVG(true)}<span>${escapeHtml(message)}</span></div>`;
  },

  musicIconSVG(standalone = false) {
    return `<svg viewBox="0 0 24 24"${standalone ? "" : ' style="width:24px;height:24px;"'}><path fill="currentColor" d="M12 3v10.55A4 4 0 1 0 14 17V7h4V3h-6z"/></svg>`;
  },
};

document.addEventListener("DOMContentLoaded", () => SpotifyPanel.init());
