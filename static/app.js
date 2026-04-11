"use strict";

const TimeManager = (() => {
  const tg = window.Telegram.WebApp;

  // ==================== STATE ====================
  const state = {
    events:    [],
    loading:   false,
    editingId: null,
    userTZ:    Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"
  };

  // ==================== API ====================
  const API = {
    _ctrl: null,
    async request(url, payload = {}) {
      if (this._ctrl) this._ctrl.abort();
      this._ctrl = new AbortController();
      const res  = await fetch(url, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ initData: tg.initData, timezone: state.userTZ, ...payload }),
        signal:  this._ctrl.signal
      });
      if (res.status === 429) throw new Error("RATE_LIMIT");
      if (res.status === 403) throw new Error("AUTH_FAILED");
      if (!res.ok)            throw new Error("API_ERROR");
      return res.json();
    }
  };

  // ==================== CACHE ====================
  const Cache = {
    KEY: "tm_events_v3",
    save(d)  { try { localStorage.setItem(this.KEY, JSON.stringify(d)); } catch {} },
    load()   {
      try { const r = localStorage.getItem(this.KEY); return r ? JSON.parse(r) : []; }
      catch { localStorage.removeItem(this.KEY); return []; }
    }
  };

  // ==================== REPEAT CONFIG ====================
  const REPEAT_CONFIG = {
    none:    { label: "One-time",     icon: "⏰", color: "#8a8a8a" },
    daily:   { label: "Daily",        icon: "🔁", color: "#3390ec" },
    weekly:  { label: "Weekly",       icon: "🔁", color: "#7b61ff" },
    monthly: { label: "Monthly",      icon: "🔁", color: "#fb8c00" },
    yearly:  { label: "Every Year",   icon: "🎂", color: "#e53935" }
  };

  // ==================== UI ====================
  const UI = {

    _buildCard(e) {
      const card = document.createElement("div");
      card.className = `card ${e.optimistic ? "syncing" : ""}`;
      card.dataset.id = e.id;

      // ردیف بالا: عنوان + badge تکرار
      const topRow = document.createElement("div");
      topRow.className = "card-top";

      const titleEl = document.createElement("div");
      titleEl.className = "card-title";
      titleEl.textContent = e.title;         // XSS safe

      const rc = REPEAT_CONFIG[e.repeat] || REPEAT_CONFIG.none;
      const badge = document.createElement("span");
      badge.className = "repeat-badge";
      badge.textContent = `${rc.icon} ${rc.label}`;
      badge.style.setProperty("--badge-color", rc.color);

      topRow.appendChild(titleEl);
      topRow.appendChild(badge);

      // ردیف وسط: تاریخ میلادی + شمسی
      const dateRow = document.createElement("div");
      dateRow.className = "card-date-row";

      const dateG = document.createElement("span");
      dateG.className = "card-date";
      dateG.textContent = e.date_iso || "";

      const dateSep = document.createElement("span");
      dateSep.className = "date-sep";
      dateSep.textContent = " • ";

      const dateJ = document.createElement("span");
      dateJ.className = "card-date jalali";
      dateJ.textContent = e.date_jalali || "";

      dateRow.appendChild(dateG);
      dateRow.appendChild(dateSep);
      dateRow.appendChild(dateJ);

      // وضعیت نوتیف
      const statusEl = document.createElement("div");
      statusEl.className = `card-status status-${e.notify_status || "pending"}`;
      const statusMap = {
        pending:    "⏳ Waiting",
        done:       "✅ Sent",
        failed:     "❌ Failed",
        processing: "🔄 Sending…"
      };
      statusEl.textContent = statusMap[e.notify_status] || "";

      // دکمه‌های action
      const actions = document.createElement("div");
      actions.className = "card-actions";

      if (!e.optimistic) {
        const editBtn = document.createElement("button");
        editBtn.className = "btn-icon btn-edit";
        editBtn.textContent = "✏️";
        editBtn.title = "Edit";
        editBtn.onclick = () => TimeManager.startEdit(e);

        const delBtn = document.createElement("button");
        delBtn.className = "btn-icon btn-delete";
        delBtn.textContent = "🗑️";
        delBtn.title = "Delete";
        delBtn.onclick = () => TimeManager.deleteEvent(e.id);

        actions.appendChild(editBtn);
        actions.appendChild(delBtn);
      }

      card.appendChild(topRow);
      card.appendChild(dateRow);
      card.appendChild(statusEl);
      card.appendChild(actions);
      return card;
    },

    render() {
      const root = document.getElementById("list");
      root.innerHTML = "";

      if (state.loading && state.events.length === 0) {
        root.innerHTML = '<div class="loader"><span class="spinner"></span> Syncing…</div>';
        return;
      }
      if (state.events.length === 0) {
        root.innerHTML = '<div class="empty">📅 No events yet.<br><small>Add one below!</small></div>';
        return;
      }

      const frag = document.createDocumentFragment();
      state.events.forEach(e => frag.appendChild(this._buildCard(e)));
      root.appendChild(frag);
    },

    showToast(msg, type = "success") {
      let t = document.getElementById("toast");
      if (!t) { t = document.createElement("div"); t.id = "toast"; document.body.appendChild(t); }
      t.textContent = msg;
      t.className = `toast toast-${type} show`;
      clearTimeout(t._tid);
      t._tid = setTimeout(() => t.classList.remove("show"), 2800);
    },

    setEditMode(event = null) {
      const titleEl  = document.getElementById("title");
      const dateEl   = document.getElementById("date");
      const repeatEl = document.getElementById("repeat");
      const addBtn   = document.getElementById("addBtn");
      const cancelBtn = document.getElementById("cancelBtn");

      if (event) {
        titleEl.value  = event.title;
        dateEl.value   = event.date_iso;
        if (repeatEl) repeatEl.value = event.repeat || "none";
        addBtn.textContent    = "💾 Save Changes";
        cancelBtn.style.display = "block";
        titleEl.focus();
        state.editingId = event.id;
      } else {
        titleEl.value  = "";
        dateEl.value   = "";
        if (repeatEl) repeatEl.value = "none";
        addBtn.textContent    = "＋ Add Event";
        cancelBtn.style.display = "none";
        state.editingId = null;
      }
    }
  };

  // ==================== VALIDATION ====================
  function _validateDate(s) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
    return !isNaN(new Date(s + "T00:00:00").getTime());
  }

  // ==================== PUBLIC ====================
  return {

    init() {
      tg.expand();
      tg.ready();
      this._applyTheme();
      tg.onEvent("themeChanged", () => this._applyTheme());

      state.events = Cache.load();
      UI.render();
      this.sync();
    },

    _applyTheme() {
      document.documentElement.setAttribute("data-theme", tg.colorScheme || "light");
      const p = tg.themeParams || {};
      if (p.bg_color)     document.documentElement.style.setProperty("--tg-bg",   p.bg_color);
      if (p.text_color)   document.documentElement.style.setProperty("--tg-text", p.text_color);
      if (p.hint_color)   document.documentElement.style.setProperty("--tg-hint", p.hint_color);
      if (p.button_color) document.documentElement.style.setProperty("--accent",  p.button_color);
    },

    async sync() {
      state.loading = true;
      UI.render();
      try {
        const res = await API.request("/api/list", {});
        if (res.success) { state.events = res.targets; Cache.save(state.events); }
      } catch (e) { if (e.message !== "AbortError") console.warn("Sync failed:", e.message); }
      state.loading = false;
      UI.render();
    },

    async add(title, date, repeat) {
      title  = (title  || "").trim();
      date   = (date   || "").trim();
      repeat = (repeat || "none").trim();

      if (!title) { UI.showToast("⚠️ Enter a title.", "error"); return; }
      if (!_validateDate(date)) { UI.showToast("⚠️ Use YYYY-MM-DD format.", "error"); return; }
      if (title.length > 200)  { UI.showToast("⚠️ Title too long.", "error"); return; }

      if (state.editingId) return this.saveEdit(title, date, repeat);

      const tempId = "tmp_" + Date.now();
      state.events.unshift({ id: tempId, title, date_iso: date, date_jalali: "", repeat, optimistic: true, notify_status: "pending" });
      UI.render();
      tg.HapticFeedback.impactOccurred("medium");

      try {
        const res = await API.request("/api/add", { title, date, repeat });
        if (res.success) {
          UI.setEditMode(null);
          UI.showToast("✅ Event added!");
          await this.sync();
        }
      } catch (e) {
        state.events = state.events.filter(ev => ev.id !== tempId);
        UI.render();
        tg.HapticFeedback.notificationOccurred("error");
        UI.showToast(e.message === "RATE_LIMIT" ? "⚠️ Too many requests." : "❌ Failed to save.", "error");
      }
    },

    startEdit(event) {
      UI.setEditMode(event);
      tg.HapticFeedback.impactOccurred("light");
      document.querySelector(".input-container").scrollIntoView({ behavior: "smooth" });
    },

    cancelEdit() {
      UI.setEditMode(null);
      tg.HapticFeedback.impactOccurred("light");
    },

    async saveEdit(title, date, repeat) {
      const eventId = state.editingId;
      if (!eventId) return;
      tg.HapticFeedback.impactOccurred("medium");
      try {
        const res = await API.request("/api/edit", { event_id: eventId, title, date, repeat });
        if (res.success) { UI.setEditMode(null); UI.showToast("✅ Updated!"); await this.sync(); }
      } catch (e) {
        tg.HapticFeedback.notificationOccurred("error");
        UI.showToast("❌ Failed to update.", "error");
      }
    },

    deleteEvent(eventId) {
      tg.showPopup({
        title:   "Delete Event",
        message: "Are you sure?",
        buttons: [
          { id: "yes", type: "destructive", text: "Delete" },
          { id: "no",  type: "cancel" }
        ]
      }, async (btn) => {
        if (btn !== "yes") return;
        tg.HapticFeedback.notificationOccurred("warning");
        const backup = [...state.events];
        state.events = state.events.filter(e => e.id !== eventId);
        UI.render();
        try {
          await API.request("/api/delete", { event_id: eventId });
          Cache.save(state.events);
          UI.showToast("🗑️ Deleted.");
        } catch {
          state.events = backup;
          UI.render();
          UI.showToast("❌ Failed to delete.", "error");
        }
      });
    }
  };
})();

window.addEventListener("load", () => TimeManager.init());
