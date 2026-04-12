"use strict";

const TimeManager = (() => {
  const tg = window.Telegram.WebApp;

  const state = {
    events:    [],
    loading:   false,
    editingId: null,
    userTZ:    Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    view:      "list"
  };

  // ==================== RENDER SCHEDULER ====================
  // [E-05] جلوگیری از renderList های اضافه — max یک بار در هر frame
  let _renderPending = false;
  function scheduleRender() {
    if (_renderPending) return;
    _renderPending = true;
    requestAnimationFrame(() => {
      UI.renderList();
      _renderPending = false;
    });
  }

  // ==================== JALALI CONVERTER ====================
  // [C-04] fromGregorian حذف شد — dead code بود + const reassignment crash
  const Jalali = {
    _MONTH_DAYS: [31,31,31,31,31,31,30,30,30,30,30,29],

    toGregorian(jy, jm, jd) {
      jy = parseInt(jy); jm = parseInt(jm); jd = parseInt(jd);
      let gy = jy <= 979 ? 1600 : 1996;
      jy -= jy <= 979 ? 0 : 979;
      let days = 365 * jy + Math.floor(jy / 33) * 8 + Math.floor((jy % 33 + 3) / 4);
      for (let i = 0; i < jm - 1; i++) days += this._MONTH_DAYS[i];
      days += jd - 1;
      let gy2 = Math.floor(days / 365.2425) + gy;
      let gd  = days - Math.floor(365.25 * (gy2 - 1)) + 1;
      const months = [0,31,28+((gy2%4===0&&gy2%100!==0)||gy2%400===0?1:0),31,30,31,30,31,31,30,31,30,31];
      let gm = 0;
      for (let i = 1; i <= 12; i++) {
        if (gd <= months[i]) { gm = i; break; }
        gd -= months[i];
      }
      return `${gy2}-${String(gm).padStart(2,"0")}-${String(gd).padStart(2,"0")}`;
    },

    _j2(gy, gm, gd) {
      const g_days_in_month = [31,28,31,30,31,30,31,31,30,31,30,31];
      const j_days_in_month = [31,31,31,31,31,31,30,30,30,30,30,29];
      let jy, jm, jd, g_day_no, j_day_no, j_np, i;
      gy -= 1600; gm -= 1; gd -= 1;
      g_day_no = 365*gy + Math.floor((gy+3)/4) - Math.floor((gy+99)/100) + Math.floor((gy+399)/400);
      for (i=0; i<gm; ++i) g_day_no += g_days_in_month[i];
      if (gm>1 && ((gy+1601)%4===0 && ((gy+1601)%100!==0 || (gy+1601)%400===0))) ++g_day_no;
      g_day_no += gd;
      j_day_no = g_day_no - 79;
      j_np = Math.floor(j_day_no/12053); j_day_no %= 12053;
      jy = 979 + 33*j_np + 4*Math.floor(j_day_no/1461);
      j_day_no %= 1461;
      if (j_day_no >= 366) { jy += Math.floor((j_day_no-1)/365); j_day_no = (j_day_no-1)%365; }
      for (i=0; i<11 && j_day_no >= j_days_in_month[i]; ++i) j_day_no -= j_days_in_month[i];
      jm = i+1; jd = j_day_no+1;
      return `${jy}/${String(jm).padStart(2,"0")}/${String(jd).padStart(2,"0")}`;
    },

    parse(str) {
      str = str.trim().replace(/[\.\,\-]/g, "/");
      const parts = str.split("/");
      if (parts.length !== 3) return null;
      const [jy, jm, jd] = parts.map(Number);
      if (!jy || !jm || !jd || jm < 1 || jm > 12 || jd < 1 || jd > 31) return null;
      // [I-06] فقط سال‌های معتبر شمسی — جلوگیری از قبول تاریخ میلادی
      if (jy < 1300 || jy > 1500) return null;
      try { return this.toGregorian(jy, jm, jd); } catch { return null; }
    },

    display(iso) {
      if (!iso) return "";
      try {
        const [y, m, d] = iso.split("-").map(Number);
        return this._j2(y, m, d);
      } catch { return iso; }
    }
  };

  // ==================== URGENCY ====================
  function getUrgency(dateIso) {
    if (!dateIso) return "green";
    const now   = new Date(); now.setHours(0,0,0,0);
    const event = new Date(dateIso + "T00:00:00");
    const diff  = Math.floor((event - now) / 86400000);
    if (diff < 0)    return "past";
    if (diff <= 7)   return "red";
    if (diff <= 30)  return "orange";
    if (diff <= 182) return "purple"; // [I-01] yellow → purple
    return "green";
  }

  // ==================== COUNTDOWN ====================
  function getCountdown(dateIso) {
    const now   = new Date(); now.setHours(0,0,0,0);
    const event = new Date(dateIso + "T00:00:00");
    const diff  = Math.floor((event - now) / 86400000);
    if (diff < 0)   return { days: Math.abs(diff), passed: true };
    if (diff === 0) return { days: 0, today: true };
    const weeks  = Math.floor(diff / 7);
    const months = Math.floor(diff / 30.44);
    const years  = Math.floor(diff / 365.25);
    return { days: diff, weeks, months, years, passed: false };
  }

  // ==================== API ====================
  // [C-05] کنترلر جداگانه برای هر endpoint — جلوگیری از race condition
  const API = {
    _controllers: {},
    async request(url, payload = {}) {
      this._controllers[url]?.abort();
      this._controllers[url] = new AbortController();
      const res = await fetch(url, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ initData: tg.initData, timezone: state.userTZ, ...payload }),
        signal:  this._controllers[url].signal
      });
      if (res.status === 429) throw new Error("RATE_LIMIT");
      if (res.status === 403) throw new Error("AUTH_FAILED");
      if (!res.ok)            throw new Error("API_ERROR");
      return res.json();
    }
  };

  // ==================== CACHE ====================
  const Cache = {
    KEY: "tm_events_v4",
    save(d) { try { localStorage.setItem(this.KEY, JSON.stringify(d)); } catch {} },
    load()  {
      try { const r = localStorage.getItem(this.KEY); return r ? JSON.parse(r) : []; }
      catch { localStorage.removeItem(this.KEY); return []; }
    }
  };

  // ==================== REPEAT CONFIG ====================
  const REPEAT_CONFIG = {
    none:    { label: "One-time",   icon: "⏰", color: "#8a8a8a" },
    daily:   { label: "Daily",      icon: "🔁", color: "#3390ec" },
    weekly:  { label: "Weekly",     icon: "🔁", color: "#7b61ff" },
    monthly: { label: "Monthly",    icon: "🔁", color: "#fb8c00" },
    yearly:  { label: "Every Year", icon: "🎂", color: "#e53935" }
  };

  // [C-07] whitelist برای notify_status
  const VALID_STATUSES  = new Set(["pending", "done", "failed", "processing"]);
  const STATUS_LABELS   = {
    pending:    "⏳ Waiting",
    done:       "✅ Sent",
    failed:     "❌ Failed",
    processing: "🔄 Sending…"
  };

  // ==================== UI ====================
  const UI = {

    _buildCard(e) {
      const urgency = getUrgency(e.date_iso);
      const card    = document.createElement("div");
      card.className = `card urgency-${urgency} ${e.optimistic ? "syncing" : ""}`;
      card.dataset.id = e.id;

      card.addEventListener("click", (ev) => {
        if (ev.target.closest(".card-actions")) return;
        TimeManager.showDetail(e);
      });

      const topRow = document.createElement("div");
      topRow.className = "card-top";

      const titleEl = document.createElement("div");
      titleEl.className = "card-title";
      titleEl.textContent = e.title;

      const rc    = REPEAT_CONFIG[e.repeat] || REPEAT_CONFIG.none;
      const badge = document.createElement("span");
      badge.className = "repeat-badge";
      badge.textContent = `${rc.icon} ${rc.label}`;
      badge.style.setProperty("--badge-color", rc.color);

      topRow.appendChild(titleEl);
      topRow.appendChild(badge);

      const dateRow = document.createElement("div");
      dateRow.className = "card-date-row";

      const dG = document.createElement("span");
      dG.className = "card-date";
      dG.textContent = e.date_iso || "";

      const sep = document.createElement("span");
      sep.className = "date-sep";
      sep.textContent = " • ";

      const dJ = document.createElement("span");
      dJ.className = "card-date jalali";
      dJ.textContent = e.date_jalali || Jalali.display(e.date_iso);

      dateRow.appendChild(dG);
      dateRow.appendChild(sep);
      dateRow.appendChild(dJ);

      const cd = getCountdown(e.date_iso);
      const cdEl = document.createElement("div");
      cdEl.className = "card-countdown";
      if (cd.today)             cdEl.textContent = "🎉 Today!";
      else if (cd.passed)       cdEl.textContent = `⌛ ${cd.days} days ago`;
      else if (cd.days <= 7)    cdEl.textContent = `⚡ ${cd.days} days left`;
      else if (cd.months >= 12) cdEl.textContent = `📆 ~${cd.years} yr${cd.years>1?"s":""} left`;
      else if (cd.months >= 2)  cdEl.textContent = `📆 ~${cd.months} months left`;
      else                      cdEl.textContent = `📆 ${cd.days} days left`;

      // [C-07] whitelist status
      const safeStatus = VALID_STATUSES.has(e.notify_status) ? e.notify_status : "pending";
      const statusEl = document.createElement("div");
      statusEl.className = `card-status status-${safeStatus}`;
      statusEl.textContent = STATUS_LABELS[safeStatus] || "";

      const actions = document.createElement("div");
      actions.className = "card-actions";
      if (!e.optimistic) {
        const editBtn = document.createElement("button");
        editBtn.className = "btn-icon btn-edit";
        editBtn.textContent = "✏️";
        editBtn.title = "Edit";
        editBtn.setAttribute("aria-label", "Edit event");
        editBtn.onclick = (ev) => { ev.stopPropagation(); TimeManager.startEdit(e); };

        const delBtn = document.createElement("button");
        delBtn.className = "btn-icon btn-delete";
        delBtn.textContent = "🗑️";
        delBtn.title = "Delete";
        delBtn.setAttribute("aria-label", "Delete event");
        delBtn.onclick = (ev) => { ev.stopPropagation(); TimeManager.deleteEvent(e.id); };

        actions.appendChild(editBtn);
        actions.appendChild(delBtn);
      }

      card.appendChild(topRow);
      card.appendChild(dateRow);
      card.appendChild(cdEl);
      card.appendChild(statusEl);
      card.appendChild(actions);
      return card;
    },

    renderList() {
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

    // ==================== DETAIL VIEW ====================
    // [C-06] تمام داده‌های دینامیک با textContent — بدون innerHTML ناامن
    renderDetail(e) {
      const root    = document.getElementById("list");
      root.innerHTML = "";

      const cd      = getCountdown(e.date_iso);
      const urgency = getUrgency(e.date_iso);
      const rc      = REPEAT_CONFIG[e.repeat] || REPEAT_CONFIG.none;
      const jalali  = e.date_jalali || Jalali.display(e.date_iso);

      const wrap = document.createElement("div");
      wrap.className = "detail-wrap";

      // دکمه برگشت
      const back = document.createElement("button");
      back.className = "btn-back";
      back.textContent = "← Back";
      back.onclick = () => TimeManager.showList();

      // عنوان
      const title = document.createElement("h2");
      title.className = "detail-title";
      title.textContent = e.title; // textContent — XSS safe ✅

      // تاریخ‌ها — کاملاً با createElement
      const dates = document.createElement("div");
      dates.className = "detail-dates";

      const _makeDateItem = (labelText, valueText, valueExtraClass = "") => {
        const item  = document.createElement("div");
        item.className = "detail-date-item";
        const lbl = document.createElement("span");
        lbl.className = "detail-label";
        lbl.textContent = labelText;
        const val = document.createElement("span");
        val.className = `detail-val${valueExtraClass ? " " + valueExtraClass : ""}`;
        val.textContent = valueText; // textContent — XSS safe ✅
        item.appendChild(lbl);
        item.appendChild(val);
        return item;
      };

      dates.appendChild(_makeDateItem("📅 Gregorian", e.date_iso));
      dates.appendChild(_makeDateItem("📅 Jalali", jalali, "jalali"));

      // Countdown بزرگ
      const cdBox = document.createElement("div");
      cdBox.className = `countdown-box urgency-bg-${urgency}`;

      if (cd.today) {
        const cdMain = document.createElement("div");
        cdMain.className = "cd-main";
        cdMain.textContent = "🎉";
        const cdLabel = document.createElement("div");
        cdLabel.className = "cd-label";
        cdLabel.textContent = "Today is the day!";
        cdBox.appendChild(cdMain);
        cdBox.appendChild(cdLabel);

      } else if (cd.passed) {
        const cdMain = document.createElement("div");
        cdMain.className = "cd-main";
        cdMain.textContent = cd.days;
        const cdLabel = document.createElement("div");
        cdLabel.className = "cd-label";
        cdLabel.textContent = "days ago";
        cdBox.appendChild(cdMain);
        cdBox.appendChild(cdLabel);

      } else {
        const cdTitle = document.createElement("div");
        cdTitle.className = "cd-title";
        cdTitle.textContent = "Time remaining";

        const cdGrid = document.createElement("div");
        cdGrid.className = "cd-grid";

        const _addRow = (num, unit) => {
          const row    = document.createElement("div");
          row.className = "cd-row";
          const numEl  = document.createElement("span");
          numEl.className = "cd-num";
          numEl.textContent = num;
          const unitEl = document.createElement("span");
          unitEl.className = "cd-unit";
          unitEl.textContent = unit;
          row.appendChild(numEl);
          row.appendChild(unitEl);
          cdGrid.appendChild(row);
        };

        _addRow(cd.days, "days");
        if (cd.weeks  > 0) _addRow(cd.weeks,  "weeks");
        if (cd.months > 0) _addRow(cd.months, "months");
        if (cd.years  > 0) _addRow(cd.years,  "years");

        cdBox.appendChild(cdTitle);
        cdBox.appendChild(cdGrid);
      }

      // Meta — [C-07] whitelist برای notify_status
      const safeStatus = VALID_STATUSES.has(e.notify_status) ? e.notify_status : "pending";

      const meta = document.createElement("div");
      meta.className = "detail-meta";

      const _makeMetaItem = (valueEl, labelText) => {
        const item  = document.createElement("div");
        item.className = "meta-item";
        const lbl = document.createElement("span");
        lbl.className = "meta-label";
        lbl.textContent = labelText;
        item.appendChild(valueEl);
        item.appendChild(lbl);
        return item;
      };

      const repeatVal = document.createElement("span");
      repeatVal.textContent = `${rc.icon} ${rc.label}`;

      const statusVal = document.createElement("span");
      statusVal.className = `status-${safeStatus}`; // safe — از whitelist آمده ✅
      statusVal.textContent = STATUS_LABELS[safeStatus] || "";

      meta.appendChild(_makeMetaItem(repeatVal, "Repeat"));
      meta.appendChild(_makeMetaItem(statusVal, "Notification"));

      wrap.appendChild(back);
      wrap.appendChild(title);
      wrap.appendChild(dates);
      wrap.appendChild(cdBox);
      wrap.appendChild(meta);
      root.appendChild(wrap);
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
      const titleEl   = document.getElementById("title");
      const dateEl    = document.getElementById("date");
      const jalaliEl  = document.getElementById("date-jalali");
      const repeatEl  = document.getElementById("repeat");
      const addBtn    = document.getElementById("addBtn");
      const cancelBtn = document.getElementById("cancelBtn");
      if (event) {
        titleEl.value  = event.title;
        dateEl.value   = event.date_iso;
        if (jalaliEl) jalaliEl.value = event.date_jalali || Jalali.display(event.date_iso);
        if (repeatEl) repeatEl.value = event.repeat || "none";
        addBtn.textContent      = "💾 Save";
        cancelBtn.style.display = "block";
        titleEl.focus();
        state.editingId = event.id;
      } else {
        titleEl.value  = "";
        dateEl.value   = "";
        if (jalaliEl) jalaliEl.value = "";
        if (repeatEl) repeatEl.value = "none";
        addBtn.textContent      = "＋ Add";
        cancelBtn.style.display = "none";
        state.editingId = null;
      }
    }
  };

  // ==================== INPUT JALALI SYNC ====================
  function _syncJalaliToGregorian(jalaliStr) {
    const iso    = Jalali.parse(jalaliStr);
    const dateEl = document.getElementById("date");
    if (iso && dateEl) {
      dateEl.value = iso;
      dateEl.style.borderColor = "var(--success)";
    } else if (jalaliStr && dateEl) {
      dateEl.style.borderColor = "var(--danger)";
    }
  }

  function _syncGregorianToJalali(isoStr) {
    const jalaliEl = document.getElementById("date-jalali");
    if (jalaliEl && isoStr) jalaliEl.value = Jalali.display(isoStr);
  }

  function _validateDate(s) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
    return !isNaN(new Date(s + "T00:00:00").getTime());
  }

  // ==================== PUBLIC ====================
  return {

    init() {
      tg.expand(); tg.ready();
      this._applyTheme();
      tg.onEvent("themeChanged", () => this._applyTheme());

      // cache DOM refs
      const jalaliInput = document.getElementById("date-jalali");
      const gregInput   = document.getElementById("date");
      const addBtn      = document.getElementById("addBtn");
      const cancelBtn   = document.getElementById("cancelBtn");
      const titleEl     = document.getElementById("title");
      const repeatEl    = document.getElementById("repeat");

      // [I-08] debounce 350ms روی input شمسی
      let _jalaliDbt;
      if (jalaliInput) {
        jalaliInput.addEventListener("input", () => {
          clearTimeout(_jalaliDbt);
          _jalaliDbt = setTimeout(() => _syncJalaliToGregorian(jalaliInput.value), 350);
        });
      }

      if (gregInput) {
        gregInput.addEventListener("change", () => _syncGregorianToJalali(gregInput.value));
      }

      // [E-04] event listener به‌جای onclick inline در HTML
      if (addBtn) {
        addBtn.addEventListener("click", () => {
          this.add(titleEl.value, gregInput.value, repeatEl.value);
        });
      }

      if (cancelBtn) {
        cancelBtn.addEventListener("click", () => this.cancelEdit());
      }

      // Enter key برای submit
      if (titleEl) {
        titleEl.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter") this.add(titleEl.value, gregInput.value, repeatEl.value);
        });
      }

      state.events = Cache.load();
      scheduleRender();
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
      scheduleRender(); // [E-05] به‌جای renderList مستقیم
      try {
        const res = await API.request("/api/list", {});
        if (res.success) { state.events = res.targets; Cache.save(state.events); }
      } catch (e) {
        // [I-05] e.name به‌جای e.message
        if (e.name !== "AbortError") console.warn("Sync:", e.message);
      }
      state.loading = false;
      scheduleRender(); // [E-05]
    },

    showDetail(e) {
      state.view = "detail";
      document.querySelector(".input-container").style.display = "none";
      UI.renderDetail(e);
      tg.HapticFeedback.impactOccurred("light");
    },

    showList() {
      state.view = "list";
      document.querySelector(".input-container").style.display = "flex";
      scheduleRender(); // [E-05]
    },

    async add(title, date, repeat) {
      title  = (title  || "").trim();
      date   = (date   || "").trim();
      repeat = (repeat || "none").trim();

      if (!title) { UI.showToast("⚠️ Enter a title.", "error"); return; }
      if (!_validateDate(date)) { UI.showToast("⚠️ Invalid date.", "error"); return; }
      if (title.length > 200)  { UI.showToast("⚠️ Title too long.", "error"); return; }

      if (state.editingId) return this.saveEdit(title, date, repeat);

      // [I-07] disable دکمه حین ارسال — جلوگیری از double-submit
      const addBtn = document.getElementById("addBtn");
      addBtn.disabled = true;

      const tempId = "tmp_" + Date.now();
      state.events.unshift({
        id: tempId, title, date_iso: date,
        date_jalali: Jalali.display(date),
        repeat, optimistic: true, notify_status: "pending"
      });
      scheduleRender(); // [E-05]
      tg.HapticFeedback.impactOccurred("medium");

      try {
        const res = await API.request("/api/add", { title, date, repeat });
        if (res.success) {
          UI.setEditMode(null);
          UI.showToast("✅ Added!");
          await this.sync();
        }
      } catch (e) {
        state.events = state.events.filter(ev => ev.id !== tempId);
        scheduleRender(); // [E-05]
        tg.HapticFeedback.notificationOccurred("error");
        UI.showToast(e.message === "RATE_LIMIT" ? "⚠️ Too many requests." : "❌ Failed.", "error");
      } finally {
        addBtn.disabled = false; // [I-07] همیشه re-enable می‌شود
      }
    },

    startEdit(event) {
      this.showList();
      UI.setEditMode(event);
      tg.HapticFeedback.impactOccurred("light");
      document.querySelector(".input-container").scrollIntoView({ behavior: "smooth" });
    },

    cancelEdit() { UI.setEditMode(null); tg.HapticFeedback.impactOccurred("light"); },

    async saveEdit(title, date, repeat) {
      const eventId = state.editingId;
      if (!eventId) return;

      // [I-07] disable دکمه حین ارسال
      const addBtn = document.getElementById("addBtn");
      addBtn.disabled = true;
      tg.HapticFeedback.impactOccurred("medium");

      try {
        const res = await API.request("/api/edit", { event_id: eventId, title, date, repeat });
        if (res.success) {
          UI.setEditMode(null);
          UI.showToast("✅ Updated!");
          await this.sync();
        }
      } catch {
        tg.HapticFeedback.notificationOccurred("error");
        UI.showToast("❌ Failed.", "error");
      } finally {
        addBtn.disabled = false; // [I-07]
      }
    },

    deleteEvent(eventId) {
      tg.showPopup({
        title: "Delete", message: "Delete this event?",
        buttons: [
          { id: "yes", type: "destructive", text: "Delete" },
          { id: "no",  type: "cancel" }
        ]
      }, async (btn) => {
        if (btn !== "yes") return;
        tg.HapticFeedback.notificationOccurred("warning");
        const backup = [...state.events];
        state.events = state.events.filter(e => e.id !== eventId);
        scheduleRender(); // [E-05]
        try {
          await API.request("/api/delete", { event_id: eventId });
          Cache.save(state.events);
          UI.showToast("🗑️ Deleted.");
        } catch {
          state.events = backup;
          scheduleRender(); // [E-05]
          UI.showToast("❌ Failed.", "error");
        }
      });
    }
  };
})();

window.addEventListener("load", () => TimeManager.init());
