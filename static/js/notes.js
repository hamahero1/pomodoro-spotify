/* Floating "Take Notes" button -> overlay with saved-files sidebar + Markdown editor. */

const Notes = {
  notes: [],
  activeId: null,
  dirty: false,

  init() {
    this.fab = document.getElementById("notes-fab");
    this.overlay = document.getElementById("notes-overlay");
    this.closeBtn = document.getElementById("notes-close");
    this.newBtn = document.getElementById("notes-new");
    this.listEl = document.getElementById("notes-file-list");
    this.titleInput = document.getElementById("notes-title-input");
    this.contentArea = document.getElementById("notes-content");
    this.saveBtn = document.getElementById("notes-save");
    this.saveStatus = document.getElementById("notes-save-status");

    this.fab.addEventListener("click", () => this.open());
    this.closeBtn.addEventListener("click", () => this.close());
    this.overlay.addEventListener("click", (e) => {
      if (e.target === this.overlay) this.close();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !this.overlay.classList.contains("hidden")) this.close();
      if ((e.ctrlKey || e.metaKey) && e.key === "s" && !this.overlay.classList.contains("hidden")) {
        e.preventDefault();
        this.save();
      }
    });

    this.newBtn.addEventListener("click", () => this.createNew());
    this.saveBtn.addEventListener("click", () => this.save());
    this.titleInput.addEventListener("input", () => this.markDirty());
    this.contentArea.addEventListener("input", () => this.markDirty());
  },

  async open() {
    this.overlay.classList.remove("hidden");
    await this.loadList();
    if (!this.activeId && this.notes.length > 0) {
      this.selectNote(this.notes[0].id);
    } else if (this.notes.length === 0) {
      this.showEmptyEditor();
    }
  },

  close() {
    if (this.dirty) this.save();
    this.overlay.classList.add("hidden");
  },

  async loadList() {
    try {
      this.notes = await apiFetch("/api/notes");
      this.renderList();
    } catch (e) {
      showToast("Couldn't load notes: " + e.message, true);
    }
  },

  renderList() {
    this.listEl.innerHTML = "";
    this.notes.forEach((note) => {
      const li = document.createElement("li");
      li.className = "notes-file-item" + (note.id === this.activeId ? " active" : "");
      li.textContent = note.title;
      li.title = note.title;
      li.addEventListener("click", () => this.selectNote(note.id));
      this.listEl.appendChild(li);
    });
  },

  showEmptyEditor() {
    this.activeId = null;
    this.titleInput.value = "";
    this.contentArea.value = "";
    this.contentArea.placeholder = "Write anything… (click + New note to start, or just start typing then Save)";
    this.dirty = false;
    this.saveStatus.textContent = "";
  },

  async selectNote(id) {
    try {
      const note = await apiFetch(`/api/notes/${id}`);
      this.activeId = note.id;
      this.titleInput.value = note.title;
      this.contentArea.value = note.content;
      this.dirty = false;
      this.saveStatus.textContent = "Saved";
      this.renderList();
    } catch (e) {
      showToast("Couldn't open note: " + e.message, true);
    }
  },

  async createNew() {
    try {
      const note = await apiFetch("/api/notes", {
        method: "POST",
        body: JSON.stringify({ title: "Untitled note", content: "" }),
      });
      await this.loadList();
      this.selectNote(note.id);
    } catch (e) {
      showToast("Couldn't create note: " + e.message, true);
    }
  },

  markDirty() {
    this.dirty = true;
    this.saveStatus.textContent = "Unsaved changes…";
  },

  async save() {
    const title = this.titleInput.value.trim() || "Untitled note";
    const content = this.contentArea.value;

    if (!this.activeId) {
      try {
        const note = await apiFetch("/api/notes", {
          method: "POST",
          body: JSON.stringify({ title, content }),
        });
        this.activeId = note.id;
        this.dirty = false;
        this.saveStatus.textContent = "Saved";
        await this.loadList();
      } catch (e) {
        showToast("Couldn't save note: " + e.message, true);
      }
      return;
    }

    try {
      await apiFetch(`/api/notes/${this.activeId}`, {
        method: "PUT",
        body: JSON.stringify({ title, content }),
      });
      this.dirty = false;
      this.saveStatus.textContent = "Saved";
      await this.loadList();
    } catch (e) {
      showToast("Couldn't save note: " + e.message, true);
    }
  },
};

document.addEventListener("DOMContentLoaded", () => Notes.init());
