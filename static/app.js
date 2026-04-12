"use strict";

const TimeManager = (() => {
  const tg = window.Telegram.WebApp;

  const state = {
    events: [],
    loading: false,
    editingId: null,
    userTZ: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    view: "list",
    detailId: null
  };

  let _renderPending = false;
  function scheduleRender() {
    if (_renderPending) return;
    _renderPending = true;
    requestAnimationFrame(() => {
      if (state.view === "list") UI.renderList();
      _renderPending = false;
    });
  }

  function normalizeDigits(str) {
    return String(str || "")
      .replace(/[۰-۹]/g, d => String(d.charCodeAt(0) - 1776))
      .replace(/[٠-٩]/g, d => String(d.charCodeAt(0) - 1632));
  }

  function normalizeDateInput(str) {
    return normalizeDigits(str)
      .trim()
      .replace(/\s+/g, "")
      .replace(/[.,،\-]+/g, "/")
      .replace(/\/+/g, "/");
  }

  function autoFormatJalaliInput(str) {
    const normalized = normalizeDateInput(str);
    if (!normalized) return "";

    const digitsOnly = normalized.replace(/\D/g, "");
    if (!normalized.includes("/") && digitsOnly.length === 8) {
      return `${digitsOnly.slice(0, 4)}/${digitsOnly.slice(4, 6)}/${digitsOnly.slice(6, 8)}`;
    }

    return normalized;
  }

  function _parseIsoParts(s) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(s || "").trim());
    if (!m) return null;
    return {
      y: Number(m[1]),
      m: Number(m[2]),
      d: Number(m[3])
    };
  }

  function _validateDate(s) {
    const p = _parseIsoParts(s);
    if (!p) return false;
    const dt = new Date(p.y, p.m - 1, p.d);
    return dt.getFullYear() === p.y &&
           dt.getMonth() === p.m - 1 &&
           dt.getDate() === p.d;
  }

  function _dateFromIsoLocal(dateIso) {
    const p = _parseIsoParts(dateIso);
    if (!p) return null;

    const dt = new Date(p.y, p.m - 1, p.d);
    if (dt.getFullYear() !== p.y || dt.getMonth() !== p.m - 1 || dt.getDate() !== p.d) {
      return null;
    }

    dt.setHours(0, 0, 0, 0);
    return dt;
  }

  function _todayLocal() {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate());
  }

  function _diffDays(a, b) {
    return Math.round((b.getTime() - a.getTime()) / 86400000);
  }

  function _shiftDate(base, years = 0, months = 0) {
    const y = base.getFullYear() + years;
    const m = base.getMonth() + months;
    const d = base.getDate();

    const shifted = new Date(y, m, 1);
    const lastDay = new Date(shifted.getFullYear(), shifted.getMonth() + 1, 0).getDate();
    shifted.setDate(Math.min(d, lastDay));
    shifted.setHours(0, 0, 0, 0);

    return shifted;
  }

  function _countdownPartsToArray(cd) {
    const parts = [];
    if (cd.years > 0) parts.push({ short: `${cd.years}y`, long: `${cd.years} year${cd.years > 1 ? "s" : ""}` });
    if (cd.months > 0) parts.push({ short: `${cd.months}m`, long: `${cd.months} month${cd.months > 1 ? "s" : ""}` });
    if (cd.weeks > 0) parts.push({ short: `${cd.weeks}w`, long: `${cd.weeks} week${cd.weeks > 1 ? "s" : ""}` });
    if (cd.days > 0) parts.push({ short: `${cd.days}d`, long: `${cd.days} day${cd.days > 1 ? "s" : ""}` });
    return parts;
  }

  function formatCountdownShort(cd, maxParts = 3) {
    if (cd.today) return "Today!";
    if (cd.passed) return `${cd.totalDays} day${cd.totalDays > 1 ? "s" : ""} ago`;
    const parts = _countdownPartsToArray(cd).slice(0, maxParts);
    return (parts.length ? parts : [{ short: "0d" }]).map(p => p.short).join(" ");
  }

  function formatCountdownLong(cd) {
    if (cd.today) return "Today is the day!";
    if (cd.passed) return `${cd.totalDays} day${cd.totalDays > 1 ? "s" : ""} ago`;
    const parts = _countdownPartsToArray(cd);
    return `${(parts.length ? parts : [{ long: "0 days" }]).map(p => p.long).join(", ")} left`;
  }

  const Jalali = {
    _MONTH_DAYS: [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29],

    toGregorian(jy, jm, jd) {
      jy = parseInt(jy, 10);
      jm = parseInt(jm, 10);
      jd = parseInt(jd, 10);

      let gy;
      if (jy > 979) {
        gy = 1600;
        jy -= 979;
      } else {
        gy = 621;
      }

      let days =
        (365 * jy) +
        Math.floor(jy / 33) * 8 +
        Math.floor(((jy % 33) + 3) / 4) +
        78 +
        jd +
        (jm < 7 ? (jm - 1) * 31 : ((jm - 7) * 30) + 186);

      gy += 400 * Math.floor(days / 146097);
      days %= 146097;

      if (days > 36524) {
        gy += 100 * Math.floor(--days / 36524);
        days %= 36524;
        if (days >= 365) days++;
      }

      gy += 4 * Math.floor(days / 1461);
      days %= 1461;

      if (days > 365) {
        gy += Math.floor((days - 1) / 365);
        days = (days - 1) % 365;
      }

      let gd = days + 1;
      const sal_a = [
        0,
        31,
        ((gy % 4 === 0 && gy % 100 !== 0) || gy % 400 === 0) ? 29 : 28,
        31, 30, 31, 30, 31, 31, 30, 31, 30, 31
      ];

      let gm = 1;
      while (gm <= 12 && gd > sal_a[gm]) {
        gd -= sal_a[gm];
        gm++;
      }

      return `${gy}-${String(gm).padStart(2, "0")}-${String(gd).padStart(2, "0")}`;
    },

    _j2(gy, gm, gd) {
      const g_days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
      const j_days_in_month = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29];
      let jy, jm, jd, g_day_no, j_day_no, j_np, i;

      gy -= 1600;
      gm -= 1;
      gd -= 1;

      g_day_no = 365 * gy + Math.floor((gy + 3) / 4) - Math.floor((gy + 99) / 100) + Math.floor((gy + 399) / 400);

      for (i = 0; i < gm; ++i) g_day_no += g_days_in_month[i];

      if (gm > 1 && ((gy + 1600) % 4 === 0 && ((gy + 1600) % 100 !== 0 || (gy + 1600) % 400 === 0))) {
        ++g_day_no;
      }

      g_day_no += gd;
      j_day_no = g_day_no - 79;
      j_np = Math.floor(j_day_no / 12053);
      j_day_no %= 12053;
      jy = 979 + 33 * j_np + 4 * Math.floor(j_day_no / 1461);
      j_day_no %= 1461;

      if (j_day_no >= 366) {
        jy += Math.floor((j_day_no - 1) / 365);
        j_day_no = (j_day_no - 1) % 365;
      }

      for (i = 0; i < 11 && j_day_no >= j_days_in_month[i]; ++i) {
        j_day_no -= j_days_in_month[i];
      }

      jm = i + 1;
      jd = j_day_no + 1;

      return `${jy}/${String(jm).padStart(2, "0")}/${String(jd).padStart(2, "0")}`;
    },

    parse(str) {
      const normalized = autoFormatJalaliInput(str);
      if (!normalized) return null;

      const parts = normalized.split("/");
      if (parts.length !== 3) return null;

      const [jy, jm, jd] = parts.map(v => Number(v));
      if (![jy, jm, jd].every(Number.isInteger)) return null;
      if (jy < 1300 || jy > 1500) return null;
      if (jm < 1 || jm > 12) return null;
      if (jd < 1 || jd > 31) return null;
      if (jm >= 7 && jm <= 11 && jd > 30) return null;
      if (jm === 12 && jd > 30) return null;

      try {
        const iso = this.toGregorian(jy, jm, jd);
        if (!_validateDate(iso)) return null;

        const roundTrip = this._j2(...iso.split("-").map(Number));
        const expected = `${jy}/${String(jm).padStart(2, "0")}/${String(jd).padStart(2, "0")}`;
        if (roundTrip !== expected) return null;

        return iso;
      } catch {
        return null;
      }
    },

    display(iso) {
      if (!_validateDate(iso)) return "";
      try {
        const [y, m, d] = iso.split("-").map(Number);
        return this._j2(y, m, d);
      } catch {
        return iso;
      }
    }
  };

  function getUrgency(dateIso) {
    if (!dateIso) return "green";

    const now = _todayLocal();
    const event = _dateFromIsoLocal(dateIso);
    if (!event) return "green";

    const diff = _diffDays(now, event);

    if (diff < 0) return "past";
    if (diff <= 7) return "red";
    if (diff <= 30) return "crimson";
    if (diff <= 90) return "orange";
    if (diff <= 182) return "amber";
    if (diff <= 365) return "lime";
    return "green";
  }

  function getCountdown(dateIso) {
    const today = _todayLocal();
    const event = _dateFromIsoLocal(dateIso);

    if (!event) {
      return {
        invalid: true,
        passed: false,
        today: false,
        totalDays: 0,
        years: 0,
        months: 0,
        weeks: 0,
        days: 0
      };
    }

    const totalDiff = _diffDays(today, event);

    if (totalDiff < 0) {
      return {
        passed: true,
        today: false,
        totalDays: Math.abs(totalDiff),
        years: 0,
        months: 0,
        weeks: 0,
        days: 0
      };
    }

    if (totalDiff === 0) {
      return {
        passed: false,
        today: true,
        totalDays: 0,
        years: 0,
        months: 0,
        weeks: 0,
        days: 0
      };
    }

    let years = event.getFullYear() - today.getFullYear();
    if (years < 0) years = 0;

    let cursor = _shiftDate(today, years, 0);
    if (cursor > event) {
      years--;
      cursor = _shiftDate(today, years, 0);
    }

    let months =
      (event.getFullYear() - cursor.getFullYear()) * 12 +
      (event.getMonth() - cursor.getMonth());

    if (months < 0) months = 0;

    let monthCursor = _shiftDate(cursor, 0, months);
    if (monthCursor > event) {
      months--;
      monthCursor = _shiftDate(cursor, 0, months);
    }

    cursor = monthCursor;

    const remainingDays = _diffDays(cursor, event);
    const weeks = Math.floor(remainingDays / 7);
    const days = remainingDays % 7;

    return {
      passed: false,
      today: false,
      totalDays: totalDiff,
      years,
      months,
      weeks,
      days
    };
  }

  const API = {
    _controllers: {},
    async request(url, payload = {}) {
      this._controllers[url]?.abort();
      this._controllers[url] = new AbortController();

      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ initData: tg.initData, timezone: state.userTZ, ...payload }),
        signal: this._controllers[url].signal
      });

      if (res.status === 429) throw new Error("RATE_LIMIT");
      if (res.status === 403) throw new Error("AUTH_FAILED");
      if (!res.ok) throw new Error("API_ERROR");

      return res.json();
    }
  };

  const Cache = {
    KEY: "tm_events_v4",
    save(d) { try { localStorage.setItem(this.KEY, JSON.stringify(d)); } catch {} },
    load() {
      try {
        const r = localStorage.getItem(this.KEY);
        return r ? JSON.parse(r) : [];
      } catch {
        localStorage.removeItem(this.KEY);
        return [];
      }
    }
  };

  const REPEAT_CONFIG = {
    none: { label: "One-time", icon: "⏰", color: "#8a8a8a" },
    daily: { label: "Daily", icon: "🔁", color: "#3390ec" },
    weekly: { label: "Weekly", icon: "🔁", color: "#7b61ff" },
    monthly: { label: "Monthly", icon: "🔁", color: "#fb8c00" },
    yearly: { label: "Every Year", icon: "🎂", color: "#e53935" }
  };

  const VALID_STATUSES = new Set(["pending", "done", "failed", "processing"]);
  const STATUS_LABELS = {
    pending: "⏳ Waiting",
    done: "✅ Sent",
    failed: "❌ Failed",
    processing: "🔄 Sending…"
  };

  const UI = {
    _buildCard(e) {
      const urgency = getUrgency(e.date_iso);
      const card = document.createElement("div");
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

      const rc = REPEAT_CONFIG[e.repeat] || REPEAT_CONFIG.none;
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

      if (cd.today) {
        cdEl.textContent = "🎉 Today!";
      } else if (cd.passed) {
        cdEl.textContent = `⌛ ${formatCountdownShort(cd)}`;
      } else {
        cdEl.textContent = `⏳ ${formatCountdownShort(cd)} left`;
      }

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
        editBtn.onclick = (ev) => {
          ev.stopPropagation();
          TimeManager.startEdit(e);
        };

        const delBtn = document.createElement("button");
        delBtn.className = "btn-icon btn-delete";
        delBtn.textContent = "🗑️";
        delBtn.title = "Delete";
        delBtn.setAttribute("aria-label", "Delete event");
        delBtn.onclick = (ev) => {
          ev.stopPropagation();
          TimeManager.deleteEvent(e.id);
        };

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

    renderDetail(e) {
      const root = document.getElementById("list");
      root.innerHTML = "";

      const cd = getCountdown(e.date_iso);
      const urgency = getUrgency(e.date_iso);
      const rc = REPEAT_CONFIG[e.repeat] || REPEAT_CONFIG.none;
      const jalali = e.date_jalali || Jalali.display(e.date_iso);

      const wrap = document.createElement("div");
      wrap.className = "detail-wrap";

      const back = document.createElement("button");
      back.className = "btn-back";
      back.textContent = "← Back";
      back.onclick = () => TimeManager.showList();

      const title = document.createElement("h2");
      title.className = "detail-title";
      title.textContent = e.title;

      const dates = document.createElement("div");
      dates.className = "detail-dates";

      const _makeDateItem = (labelText, valueText, valueExtraClass = "") => {
        const item = document.createElement("div");
        item.className = "detail-date-item";

        const lbl = document.createElement("span");
        lbl.className = "detail-label";
        lbl.textContent = labelText;

        const val = document.createElement("span");
        val.className = `detail-val${valueExtraClass ? " " + valueExtraClass : ""}`;
        val.textContent = valueText;

        item.appendChild(lbl);
        item.appendChild(val);
        return item;
      };

      dates.appendChild(_makeDateItem("📅 Gregorian", e.date_iso));
      dates.appendChild(_makeDateItem("📅 Jalali", jalali, "jalali"));

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
        cdMain.textContent = cd.totalDays;

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
          const row = document.createElement("div");
          row.className = "cd-row";

          const numEl = document.createElement("span");
          numEl.className = "cd-num";
          numEl.textContent = num;

          const unitEl = document.createElement("span");
          unitEl.className = "cd-unit";
          unitEl.textContent = unit;

          row.appendChild(numEl);
          row.appendChild(unitEl);
          cdGrid.appendChild(row);
        };

        if (cd.years > 0) _addRow(cd.years, "years");
        if (cd.months > 0) _addRow(cd.months, "months");
        if (cd.weeks > 0) _addRow(cd.weeks, "weeks");
        if (cd.days > 0) _addRow(cd.days, "days");
        if (cd.years === 0 && cd.months === 0 && cd.weeks === 0 && cd.days === 0) _addRow(0, "days");

        const cdLabel = document.createElement("div");
        cdLabel.className = "cd-label";
        cdLabel.textContent = formatCountdownLong(cd);

        cdBox.appendChild(cdTitle);
        cdBox.appendChild(cdGrid);
        cdBox.appendChild(cdLabel);
      }

      const safeStatus = VALID_STATUSES.has(e.notify_status) ? e.notify_status : "pending";

      const meta = document.createElement("div");
      meta.className = "detail-meta";

      const _makeMetaItem = (valueEl, labelText) => {
        const item = document.createElement("div");
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
      statusVal.className = `status-${safeStatus}`;
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
      if (!t) {
        t = document.createElement("div");
        t.id = "toast";
        document.body.appendChild(t);
      }
      t.textContent = msg;
      t.className = `toast toast-${type} show`;
      clearTimeout(t._tid);
      t._tid = setTimeout(() => t.classList.remove("show"), 2800);
    },

    setEditMode(event = null) {
      const titleEl = document.getElementById("title");
      const dateEl = document.getElementById("date");
      const jalaliEl = document.getElementById("date-jalali");
      const repeatEl = document.getElementById("repeat");
      const addBtn = document.getElementById("addBtn");
      const cancelBtn = document.getElementById("cancelBtn");

      if (event) {
        titleEl.value = event.title;
        dateEl.value = event.date_iso;
        if (jalaliEl) jalaliEl.value = event.date_jalali || Jalali.display(event.date_iso);
        if (repeatEl) repeatEl.value = event.repeat || "none";
        addBtn.textContent = "💾 Save";
        cancelBtn.style.display = "block";
        titleEl.focus();
        state.editingId = event.id;
      } else {
        titleEl.value = "";
        dateEl.value = "";
        if (jalaliEl) jalaliEl.value = "";
        if (repeatEl) repeatEl.value = "none";
        addBtn.textContent = "＋ Add";
        cancelBtn.style.display = "none";
        state.editingId = null;
      }
    }
  };

  function _syncJalaliToGregorian(jalaliStr) {
    const dateEl = document.getElementById("date");
    const jalaliEl = document.getElementById("date-jalali");
    if (!dateEl) return;

    const raw = String(jalaliStr || "").trim();
    if (!raw) {
      dateEl.style.borderColor = "";
      if (jalaliEl) jalaliEl.style.borderColor = "";
      return;
    }

    const formatted = autoFormatJalaliInput(raw);
    if (jalaliEl && jalaliEl.value !== formatted) {
      jalaliEl.value = formatted;
    }

    const iso = Jalali.parse(formatted);
    if (iso) {
      dateEl.value = iso;
      dateEl.style.borderColor = "var(--success)";
      if (jalaliEl) jalaliEl.style.borderColor = "var(--success)";
    } else {
      dateEl.style.borderColor = "var(--danger)";
      if (jalaliEl) jalaliEl.style.borderColor = "var(--danger)";
    }
  }

  function _syncGregorianToJalali(isoStr) {
    const jalaliEl = document.getElementById("date-jalali");
    const dateEl = document.getElementById("date");

    if (jalaliEl) {
      jalaliEl.value = isoStr ? Jalali.display(isoStr) : "";
      jalaliEl.style.borderColor = "";
    }

    if (dateEl) {
      dateEl.style.borderColor = "";
    }
  }

  return {
    init() {
      tg.expand();
      tg.ready();
      this._applyTheme();
      tg.onEvent("themeChanged", () => this._applyTheme());

      const jalaliInput = document.getElementById("date-jalali");
      const gregInput = document.getElementById("date");
      const addBtn = document.getElementById("addBtn");
      const cancelBtn = document.getElementById("cancelBtn");
      const titleEl = document.getElementById("title");
      const repeatEl = document.getElementById("repeat");

      let _jalaliDbt;
      if (jalaliInput) {
        jalaliInput.addEventListener("input", () => {
          const formatted = autoFormatJalaliInput(jalaliInput.value);
          if (formatted !== jalaliInput.value) {
            jalaliInput.value = formatted;
          }

          clearTimeout(_jalaliDbt);
          _jalaliDbt = setTimeout(() => _syncJalaliToGregorian(jalaliInput.value), 250);
        });
      }

      if (gregInput) {
        gregInput.addEventListener("change", () => {
          _syncGregorianToJalali(gregInput.value);
        });
      }

      if (addBtn) {
        addBtn.addEventListener("click", () => {
          this.add(titleEl.value, gregInput.value, repeatEl.value);
        });
      }

      if (cancelBtn) {
        cancelBtn.addEventListener("click", () => this.cancelEdit());
      }

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
      if (p.bg_color) document.documentElement.style.setProperty("--tg-bg", p.bg_color);
      if (p.text_color) document.documentElement.style.setProperty("--tg-text", p.text_color);
      if (p.hint_color) document.documentElement.style.setProperty("--tg-hint", p.hint_color);
      if (p.button_color) document.documentElement.style.setProperty("--accent", p.button_color);
    },

    async sync() {
      state.loading = true;
      scheduleRender();
      try {
        const res = await API.request("/api/list", {});
        if (res.success) {
          state.events = res.targets;
          Cache.save(state.events);
          if (state.view === "detail" && state.detailId) {
            const current = state.events.find(ev => ev.id === state.detailId);
            if (current) UI.renderDetail(current);
          }
        }
      } catch (e) {
        if (e.name !== "AbortError") console.warn("Sync:", e.message);
      }
      state.loading = false;
      scheduleRender();
    },

    showDetail(e) {
      state.view = "detail";
      state.detailId = e.id;
      document.querySelector(".input-container").style.display = "none";
      UI.renderDetail(e);
      tg.HapticFeedback.impactOccurred("light");
    },

    showList() {
      state.view = "list";
      state.detailId = null;
      document.querySelector(".input-container").style.display = "flex";
      scheduleRender();
    },

    async add(title, date, repeat) {
      title = (title || "").trim();
      date = (date || "").trim();
      repeat = (repeat || "none").trim();

      if (!title) {
        UI.showToast("⚠️ Enter a title.", "error");
        return;
      }
      if (!_validateDate(date)) {
        UI.showToast("⚠️ Invalid date.", "error");
        return;
      }
      if (title.length > 200) {
        UI.showToast("⚠️ Title too long.", "error");
        return;
      }

      if (state.editingId) return this.saveEdit(title, date, repeat);

      const addBtn = document.getElementById("addBtn");
      addBtn.disabled = true;

      const tempId = "tmp_" + Date.now();
      state.events.unshift({
        id: tempId,
        title,
        date_iso: date,
        date_jalali: Jalali.display(date),
        repeat,
        optimistic: true,
        notify_status: "pending"
      });
      scheduleRender();
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
        scheduleRender();
        tg.HapticFeedback.notificationOccurred("error");
        UI.showToast(e.message === "RATE_LIMIT" ? "⚠️ Too many requests." : "❌ Failed.", "error");
      } finally {
        addBtn.disabled = false;
      }
    },

    startEdit(event) {
      this.showList();
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
        addBtn.disabled = false;
      }
    },

    deleteEvent(eventId) {
      tg.showPopup({
        title: "Delete",
        message: "Delete this event?",
        buttons: [
          { id: "yes", type: "destructive", text: "Delete" },
          { id: "no", type: "cancel" }
        ]
      }, async (btn) => {
        if (btn !== "yes") return;
        tg.HapticFeedback.notificationOccurred("warning");

        const backup = [...state.events];
        state.events = state.events.filter(e => e.id !== eventId);
        scheduleRender();

        try {
          await API.request("/api/delete", { event_id: eventId });
          Cache.save(state.events);
          UI.showToast("🗑️ Deleted.");
          if (state.detailId === eventId) this.showList();
        } catch {
          state.events = backup;
          scheduleRender();
          UI.showToast("❌ Failed.", "error");
        }
      });
    }
  };
})();

window.addEventListener("load", () => TimeManager.init());
