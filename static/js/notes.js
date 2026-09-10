/* Floating "Take Notes" button -> overlay with saved-files sidebar + Markdown editor. */

const ROOT_FOLDER_VALUE = "__root__";

const Notes = {
  notes: [],
  folders: [],
  currentFolder: "", // "" = All Notes, "__root__" = no folder, or a folder name
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
    this.folderSelect = document.getElementById("notes-folder-select");
    this.newFolderBtn = document.getElementById("notes-new-folder");

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

    this.folderSelect.addEventListener("change", () => {
      this.currentFolder = this.folderSelect.value;
      this.loadList();
    });
    this.newFolderBtn.addEventListener("click", () => this.createFolder());
  },

  async open() {
    this.overlay.classList.remove("hidden");
    await this.loadFolders();
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

  async loadFolders() {
    try {
      this.folders = await apiFetch("/api/notes/folders");
    } catch (e) {
      this.folders = [];
    }
    const keepValue = this.folderSelect.value || this.currentFolder;
    this.folderSelect.innerHTML = "";
    const options = [
      { value: "", label: "All Notes" },
      { value: ROOT_FOLDER_VALUE, label: "(No folder)" },
      ...this.folders.map((f) => ({ value: f.name, label: "📁 " + f.name })),
    ];
    options.forEach((opt) => {
      const el = document.createElement("option");
      el.value = opt.value;
      el.textContent = opt.label;
      this.folderSelect.appendChild(el);
    });
    // Keep whatever was selected if it still exists, else fall back to All Notes.
    const stillExists = options.some((o) => o.value === keepValue);
    this.folderSelect.value = stillExists ? keepValue : "";
    this.currentFolder = this.folderSelect.value;
  },

  async createFolder() {
    const name = prompt("New folder name:");
    if (!name || !name.trim()) return;
    try {
      const folder = await apiFetch("/api/notes/folders", {
        method: "POST",
        body: JSON.stringify({ name: name.trim() }),
      });
      await this.loadFolders();
      this.folderSelect.value = folder.name;
      this.currentFolder = folder.name;
      await this.loadList();
    } catch (e) {
      showToast("Couldn't create folder: " + e.message, true);
    }
  },

  async loadList() {
    try {
      const query = this.currentFolder ? `?folder=${encodeURIComponent(this.currentFolder)}` : "";
      this.notes = await apiFetch(`/api/notes${query}`);
      this.renderList();
    } catch (e) {
      showToast("Couldn't load notes: " + e.message, true);
    }
  },

  renderList() {
    this.listEl.innerHTML = "";
    // In "All Notes" view, tag each entry with its folder so it's clear
    // where it lives; redundant (and omitted) when already filtered to one.
    const showFolderTags = this.currentFolder === "";
    this.notes.forEach((note) => {
      const li = document.createElement("li");
      li.className = "notes-file-item" + (note.id === this.activeId ? " active" : "");
      li.title = note.title;
      li.textContent = note.title;
      if (showFolderTags) {
        const tag = document.createElement("span");
        tag.className = "nfi-folder-tag";
        tag.textContent = note.folder ? `— ${note.folder}` : "";
        li.appendChild(tag);
      }
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

  // A note's folder is whichever real folder is currently selected in the
  // dropdown — "All Notes" or "(No folder)" both mean root (null).
  targetFolder() {
    return this.currentFolder && this.currentFolder !== ROOT_FOLDER_VALUE ? this.currentFolder : null;
  },

  async createNew() {
    try {
      const note = await apiFetch("/api/notes", {
        method: "POST",
        body: JSON.stringify({ title: "Untitled note", content: "", folder: this.targetFolder() }),
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
          body: JSON.stringify({ title, content, folder: this.targetFolder() }),
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
      const saved = await apiFetch(`/api/notes/${this.activeId}`, {
        method: "PUT",
        body: JSON.stringify({ title, content }),
      });
      this.dirty = false;
      // The title may have come back auto-renamed (e.g. "note 1") if it
      // collided with another note in the same folder — reflect that.
      this.titleInput.value = saved.title;
      this.saveStatus.textContent = "Saved";
      await this.loadList();
    } catch (e) {
      showToast("Couldn't save note: " + e.message, true);
    }
  },
};

document.addEventListener("DOMContentLoaded", () => Notes.init());
