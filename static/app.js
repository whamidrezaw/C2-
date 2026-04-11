"use strict";

const TimeManager = (() => {
  const tg = window.Telegram.WebApp;

  const state = {
    events:    [],
    loading:   false,
    editingId: null,
    userTZ:    Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    view:      "list"   // "list" | "detail"
  };

  // ==================== JALALI CONVERTER ====================
  // تبدیل شمسی به میلادی (بدون کتابخانه — pure JS)
  const Jalali = {
    // جدول تبدیل ماه‌های شمسی
    _MONTH_DAYS: [31,31,31,31,31,31,30,30,30,30,30,29],

    toGregorian(jy, jm, jd) {
      jy = parseInt(jy); jm = parseInt(jm); jd = parseInt(jd);
      let gy = jy <= 979 ? 1600 : 1996;
      jy -= jy <= 979 ? 0 : 979;
      let days = 365 * jy + Math.floor(jy / 33) * 8 + Math.floor((jy % 33 + 3) / 4);
      for (let i = 0; i < jm - 1; i++) days += this._MONTH_DAYS[i];
      days += jd - 1;
      let gy2 = Math.floor(days / 365.2425) + gy;
      let gd  = days - Math.floor(365.25 * (gy2 - 1))  + 1;
      const months = [0,31,28+((gy2%4===0&&gy2%100!==0)||gy2%400===0?1:0),31,30,31,30,31,31,30,31,30,31];
      let gm = 0;
      for (let i = 1; i <= 12; i++) {
        if (gd <= months[i]) { gm = i; break; }
        gd -= months[i];
      }
      return `${gy2}-${String(gm).padStart(2,"0")}-${String(gd).padStart(2,"0")}`;
    },

    fromGregorian(gy, gm, gd) {
      gy = parseInt(gy); gm = parseInt(gm); gd = parseInt(gd);
      let jy = gy <= 1600 ? 0 : 979;
      gy -= gy <= 1600 ? 621 : 1600;
      let gy2 = gm > 2 ? gy + 1 : gy;
      let days = Math.floor(365.25 * (gy2 + 4716)) + Math.floor(30.6001 * (gm > 2 ? gm - 3 : gm + 9)) + gd - 1524;
      if (days > 2299160) {
        let a = Math.floor(days / 36524.25);
        days += 1 + a - Math.floor(a / 4);
      }
      days -= Math.floor(365.25 * (Math.floor((days - 122.1) / 365.25) - 1));
      days = Math.floor(365.25 * gy) + Math.floor(30.6001 * (gm > 2 ? gm - 2 : gm + 10)) + gd - Math.floor(365.25 * (gy - 1)) - Math.floor(30.6001 * (gm > 2 ? gm - 2 : gm + 10)) + 1;
      // ساده‌تر:
      const g_d_no = 365 * gy + Math.floor((gy + 3) / 4) - Math.floor((gy + 99) / 100) + Math.floor((gy + 399) / 400);
      const months_g = [0,31,28+((gy%4===0&&gy%100!==0)||gy%400===0?1:0),31,30,31,30,31,31,30,31,30,31];
      let g_d = g_d_no;
      for (let i = 1; i < gm; i++) g_d += months_g[i];
      g_d += gd;
      const j_d_no = g_d - 79;
      const j_np = Math.floor(j_d_no / 12053);
      const j_d2 = j_d_no % 12053;
      jy += 33 * j_np + 4 * Math.floor(j_d2 / 1461);
      const j_d3 = j_d2 % 1461;
      if (j_d3 >= 366) { jy += Math.floor((j_d3 - 1) / 365); }
      const j_d4 = (j_d3 - 1) % 365;
      const jMDays = [31,31,31,31,31,31,30,30,30,30,30,29];
      let jm = 0, jd = 0;
      for (let i = 0; i < 12; i++) {
        if (j_d4 < jMDays[i]) { jm = i + 1; jd = j_d4 + 1; break; }
        else j_d4 -= jMDays[i]; // reassign trick
      }
      // fallback ساده‌تر
      let rem = j_d_no; jy = jy; jm = 0; jd = 0;
      // استفاده از تابع ثابت‌تر
      return this._j2(gy, gm, gd);
    },

    _j2(gy, gm, gd) {
      // الگوریتم ثابت و تست‌شده
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

    // پارس ورودی شمسی: 1404/01/22 یا 1404-01-22
    parse(str) {
      str = str.trim().replace(/-/g, "/");
      const parts = str.split("/");
      if (parts.length !== 3) return null;
      const [jy, jm, jd] = parts.map(Number);
      if (!jy || !jm || !jd || jm < 1 || jm > 12 || jd < 1 || jd > 31) return null;
      try { return this.toGregorian(jy, jm, jd); } catch { return null; }
    },

    // تبدیل میلادی YYYY-MM-DD به شمسی نمایشی
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
    const diff  = Math.floor((event - now) / 86400000); // روز
    if (diff < 0)   return "past";
    if (diff <= 7)  return "red";
    if (diff <= 30) return "orange";
    if (diff <= 182)return "yellow";
    return "green";
  }

  // ==================== COUNTDOWN ====================
  function getCountdown(dateIso) {
    const now   = new Date(); now.setHours(0,0,0,0);
    const event = new Date(dateIso + "T00:00:00");
    const diff  = Math.floor((event - now) / 86400000);
    if (diff < 0)  return { days: Math.abs(diff), passed: true };
    if (diff === 0) return { days: 0, today: true };
    const weeks  = Math.floor(diff / 7);
    const months = Math.floor(diff / 30.44);
    const years  = Math.floor(diff / 365.25);
    return { days: diff, weeks, months, years, passed: false };
  }

  // ==================== API ====================
  const API = {
    _ctrl: null,
    async request(url, payload = {}) {
      if (this._ctrl) this._ctrl.abort();
      this._ctrl = new AbortController();
      const res = await fetch(url, {
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

  // ==================== UI: LIST ====================
  const UI = {

    _buildCard(e) {
      const urgency = getUrgency(e.date_iso);
      const card    = document.createElement("div");
      card.className = `card urgency-${urgency} ${e.optimistic ? "syncing" : ""}`;
      card.dataset.id = e.id;

      // کلیک روی کارت → صفحه جزئیات
      card.addEventListener("click", (ev) => {
        if (ev.target.closest(".card-actions")) return;
        TimeManager.showDetail(e);
      });

      // ردیف بالا
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

      // تاریخ
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

      // countdown خلاصه
      const cd = getCountdown(e.date_iso);
      const cdEl = document.createElement("div");
      cdEl.className = "card-countdown";
      if (cd.today)        cdEl.textContent = "🎉 Today!";
      else if (cd.passed)  cdEl.textContent = `⌛ ${cd.days} days ago`;
      else if (cd.days <= 7) cdEl.textContent = `⚡ ${cd.days} days left`;
      else if (cd.months >= 12) cdEl.textContent = `📆 ~${cd.years} yr${cd.years>1?"s":""} left`;
      else if (cd.months >= 2)  cdEl.textContent = `📆 ~${cd.months} months left`;
      else                      cdEl.textContent = `📆 ${cd.days} days left`;

      // وضعیت
      const statusEl = document.createElement("div");
      statusEl.className = `card-status status-${e.notify_status || "pending"}`;
      const sMap = { pending:"⏳ Waiting", done:"✅ Sent", failed:"❌ Failed", processing:"🔄 Sending…" };
      statusEl.textContent = sMap[e.notify_status] || "";

      // دکمه‌ها
      const actions = document.createElement("div");
      actions.className = "card-actions";
      if (!e.optimistic) {
        const editBtn = document.createElement("button");
        editBtn.className = "btn-icon btn-edit";
        editBtn.textContent = "✏️";
        editBtn.title = "Edit";
        editBtn.onclick = (ev) => { ev.stopPropagation(); TimeManager.startEdit(e); };

        const delBtn = document.createElement("button");
        delBtn.className = "btn-icon btn-delete";
        delBtn.textContent = "🗑️";
        delBtn.title = "Delete";
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

    // ==================== UI: DETAIL ====================
    renderDetail(e) {
      const root = document.getElementById("list");
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
      title.textContent = e.title;

      // تاریخ‌ها
      const dates = document.createElement("div");
      dates.className = "detail-dates";
      dates.innerHTML = `
        <div class="detail-date-item">
          <span class="detail-label">📅 Gregorian</span>
          <span class="detail-val">${e.date_iso}</span>
        </div>
        <div class="detail-date-item">
          <span class="detail-label">📅 Jalali</span>
          <span class="detail-val jalali">${jalali}</span>
        </div>
      `;

      // countdown بزرگ
      const cdBox = document.createElement("div");
      cdBox.className = `countdown-box urgency-bg-${urgency}`;

      if (cd.today) {
        cdBox.innerHTML = `<div class="cd-main">🎉</div><div class="cd-label">Today is the day!</div>`;
      } else if (cd.passed) {
        cdBox.innerHTML = `
          <div class="cd-main">${cd.days}</div>
          <div class="cd-label">days ago</div>
        `;
      } else {
        // ساخت ردیف‌های countdown
        const rows = [];
        rows.push(`<div class="cd-row"><span class="cd-num">${cd.days}</span><span class="cd-unit">days</span></div>`);
        if (cd.weeks > 0)
          rows.push(`<div class="cd-row"><span class="cd-num">${cd.weeks}</span><span class="cd-unit">weeks</span></div>`);
        if (cd.months > 0)
          rows.push(`<div class="cd-row"><span class="cd-num">${cd.months}</span><span class="cd-unit">months</span></div>`);
        if (cd.years > 0)
          rows.push(`<div class="cd-row"><span class="cd-num">${cd.years}</span><span class="cd-unit">years</span></div>`);

        cdBox.innerHTML = `
          <div class="cd-title">Time remaining</div>
          <div class="cd-grid">${rows.join("")}</div>
        `;
      }

      // اطلاعات تکرار و وضعیت
      const meta = document.createElement("div");
      meta.className = "detail-meta";
      meta.innerHTML = `
        <div class="meta-item">
          <span>${rc.icon} ${rc.label}</span>
          <span class="meta-label">Repeat</span>
        </div>
        <div class="meta-item">
          <span class="status-${e.notify_status}">${{pending:"⏳ Waiting",done:"✅ Sent",failed:"❌ Failed",processing:"🔄 Sending"}[e.notify_status]||""}</span>
          <span class="meta-label">Notification</span>
        </div>
      `;

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
    const iso = Jalali.parse(jalaliStr);
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

      // sync تاریخ شمسی ↔ میلادی
      const jalaliInput = document.getElementById("date-jalali");
      const gregInput   = document.getElementById("date");

      if (jalaliInput) {
        jalaliInput.addEventListener("input", () => _syncJalaliToGregorian(jalaliInput.value));
      }
      if (gregInput) {
        gregInput.addEventListener("change", () => _syncGregorianToJalali(gregInput.value));
      }

      state.events = Cache.load();
      UI.renderList();
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
      UI.renderList();
      try {
        const res = await API.request("/api/list", {});
        if (res.success) { state.events = res.targets; Cache.save(state.events); }
      } catch (e) { if (e.message !== "AbortError") console.warn("Sync:", e.message); }
      state.loading = false;
      UI.renderList();
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
      UI.renderList();
    },

    async add(title, date, repeat) {
      title  = (title  || "").trim();
      date   = (date   || "").trim();
      repeat = (repeat || "none").trim();

      if (!title) { UI.showToast("⚠️ Enter a title.", "error"); return; }
      if (!_validateDate(date)) { UI.showToast("⚠️ Invalid date.", "error"); return; }
      if (title.length > 200)  { UI.showToast("⚠️ Title too long.", "error"); return; }

      if (state.editingId) return this.saveEdit(title, date, repeat);

      const tempId = "tmp_" + Date.now();
      state.events.unshift({ id: tempId, title, date_iso: date, date_jalali: Jalali.display(date), repeat, optimistic: true, notify_status: "pending" });
      UI.renderList();
      tg.HapticFeedback.impactOccurred("medium");

      try {
        const res = await API.request("/api/add", { title, date, repeat });
        if (res.success) { UI.setEditMode(null); UI.showToast("✅ Added!"); await this.sync(); }
      } catch (e) {
        state.events = state.events.filter(ev => ev.id !== tempId);
        UI.renderList();
        tg.HapticFeedback.notificationOccurred("error");
        UI.showToast(e.message === "RATE_LIMIT" ? "⚠️ Too many requests." : "❌ Failed.", "error");
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
      tg.HapticFeedback.impactOccurred("medium");
      try {
        const res = await API.request("/api/edit", { event_id: eventId, title, date, repeat });
        if (res.success) { UI.setEditMode(null); UI.showToast("✅ Updated!"); await this.sync(); }
      } catch { tg.HapticFeedback.notificationOccurred("error"); UI.showToast("❌ Failed.", "error"); }
    },

    deleteEvent(eventId) {
      tg.showPopup({
        title: "Delete", message: "Delete this event?",
        buttons: [{ id:"yes", type:"destructive", text:"Delete" }, { id:"no", type:"cancel" }]
      }, async (btn) => {
        if (btn !== "yes") return;
        tg.HapticFeedback.notificationOccurred("warning");
        const backup = [...state.events];
        state.events = state.events.filter(e => e.id !== eventId);
        UI.renderList();
        try {
          await API.request("/api/delete", { event_id: eventId });
          Cache.save(state.events);
          UI.showToast("🗑️ Deleted.");
        } catch {
          state.events = backup;
          UI.renderList();
          UI.showToast("❌ Failed.", "error");
        }
      });
    }
  };
})();

window.addEventListener("load", () => TimeManager.init());
