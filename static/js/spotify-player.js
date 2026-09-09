/* Spotify Web Playback SDK: makes this browser tab a controllable Spotify
 * Connect device (Premium required). Optional — "now playing" + lyrics work
 * without it, this just lets you stream audio through the browser itself. */

const SpotifyPlayer = {
  player: null,
  deviceId: null,

  async init() {
    this.transferBtn = document.getElementById("np-play-in-browser");
    if (!this.transferBtn) return;

    let status;
    try {
      status = await apiFetch("/api/spotify/status");
    } catch (e) {
      return;
    }
    if (!status.connected) return;

    this.transferBtn.addEventListener("click", () => this.transferHere());
    this.loadSDK();
  },

  loadSDK() {
    if (document.getElementById("spotify-sdk-script")) return;
    const script = document.createElement("script");
    script.id = "spotify-sdk-script";
    script.src = "https://sdk.scdn.co/spotify-player.js";
    document.head.appendChild(script);

    window.onSpotifyWebPlaybackSDKReady = () => this.createPlayer();
  },

  createPlayer() {
    this.player = new Spotify.Player({
      name: "Pomodoro Spotify (browser)",
      getOAuthToken: async (callback) => {
        try {
          const data = await apiFetch("/api/spotify/token");
          callback(data.access_token);
        } catch (e) {
          console.error("Could not get Spotify token", e);
        }
      },
      volume: 0.6,
    });

    this.player.addListener("ready", ({ device_id }) => {
      this.deviceId = device_id;
      this.transferBtn.disabled = false;
    });

    this.player.addListener("not_ready", () => {
      this.deviceId = null;
    });

    this.player.addListener("initialization_error", ({ message }) => console.warn("Spotify init error:", message));
    this.player.addListener("authentication_error", ({ message }) => console.warn("Spotify auth error:", message));
    this.player.addListener("account_error", ({ message }) =>
      console.warn("Spotify account error (Premium required for in-browser playback):", message)
    );

    this.player.connect();
  },

  async transferHere() {
    if (!this.deviceId) {
      showToast("Browser player isn't ready yet — try again in a moment.", true);
      return;
    }
    try {
      await apiFetch("/api/spotify/player/transfer", {
        method: "PUT",
        body: JSON.stringify({ device_id: this.deviceId }),
      });
      showToast("Playing in this browser tab");
    } catch (e) {
      showToast("Couldn't switch playback here: " + e.message, true);
    }
  },
};

document.addEventListener("DOMContentLoaded", () => SpotifyPlayer.init());
