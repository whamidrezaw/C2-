"use strict";

const TimeManager = (() => {
  const tg = window.Telegram?.WebApp || {
    initData: "",
    colorScheme: "light",
    themeParams: {},
    expand() {},
    ready() {},
    onEvent() {},
    switchInlineQuery() {},
    BackButton: {
      show() {},
      hide() {},
      onClick() {}
    },
    showPopup(config, cb) {
      const ok = window.confirm(config?.message || "Are you sure?");
      cb(ok ? "yes" : "no");
    },
    HapticFeedback: {
      impactOccurred() {},
      notificationOccurred() {}
    }
  };

  const state = {
    events: [],
    loading: false,
    editingId: null,
    userTZ: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    view: "list",
    detailId: null,
    composerOpen: false
  };

  const REPEAT_CONFIG = {
    none: { label: "One-time", icon: "⏰", color: "#8a8a8a" },
    daily: { label: "Daily", icon: "🔁", color: "#3390ec" },
    weekly: { label: "Weekly", icon: "🔁", color: "#7b61ff" },
    monthly: { label: "Monthly", icon: "🔁", color: "#fb8c00" },
    yearly: { label: "Every Year", icon: "🎂", color: "#e53935" }
  };

  const CATEGORY_CONFIG = {
    general: { label: "General", icon: "🏷️" },
    birthday: { label: "Birthday", icon: "🎂" },
    work: { label: "Work", icon: "💼" },
    family: { label: "Family", icon: "👨‍👩‍👧" },
    health: { label: "Health", icon: "🩺" },
    travel: { label: "Travel", icon: "✈️" },
    finance: { label: "Finance", icon: "💰" },
    study: { label: "Study", icon: "📚" },
    other: { label: "Other", icon: "📌" }
  };

  const VALID_STATUSES = new Set(["pending", "done", "failed", "processing"]);
  const STATUS_LABELS = {
    pending: "⏳ Waiting",
    done: "✅ Sent",
    failed: "❌ Failed",
    processing: "🔄 Sending…"
  };

  const Cache = {
    KEY: "tm_events_v5",
    save(data) {
      try {
        localStorage.setItem(this.KEY, JSON.stringify(data));
      } catch {}
    },
    load() {
      try {
        const raw = localStorage.getItem(this.KEY);
        return raw ? JSON.parse(raw) : [];
      } catch {
        return [];
      }
    }
  };

  let _renderPending = false;

  function scheduleRender() {
    if (_renderPending) return;
    _renderPending = true;

    requestAnimationFrame(() => {
      if (state.view === "list") {
        UI.renderList();
      } else if (state.view === "detail" && state.detailId) {
        const current = _getEventById(state.detailId);
        if (current) UI.renderDetail(current);
      }
      _renderPending = false;
    });
  }

  function _els() {
    return {
      sheet: document.getElementById("composerSheet"),
      overlay: document.getElementById("composerOverlay"),
      openBtn: document.getElementById("openComposerBtn")
    };
  }

  function _pushAppState(mode) {
    history.pushState({ tmMode: mode, t: Date.now() }, "");
    _syncTelegramBackButton();
  }

  function _syncTelegramBackButton() {
    const visible = state.composerOpen || state.view === "detail";
    if (visible) tg.BackButton?.show?.();
    else tg.BackButton?.hide?.();
  }

  function _openComposer(push = true) {
    const { sheet, overlay, openBtn } = _els();
    if (!sheet || !overlay) return;

    state.composerOpen = true;
    sheet.hidden = false;
    overlay.hidden = false;
    sheet.classList.add("open");
    overlay.classList.add("open");
    sheet.setAttribute("aria-hidden", "false");
    if (openBtn) openBtn.style.display = "none";

    if (push) _pushAppState("composer");
    else _syncTelegramBackButton();

    const titleEl = document.getElementById("title");
    setTimeout(() => titleEl?.focus(), 120);
  }

  function _closeComposer(reset = false) {
    const { sheet, overlay, openBtn } = _els();
    if (!sheet || !overlay) return;

    state.composerOpen = false;
    sheet.classList.remove("open");
    overlay.classList.remove("open");
    sheet.setAttribute("aria-hidden", "true");
    if (openBtn) openBtn.style.display = "inline-flex";

    setTimeout(() => {
      overlay.hidden = true;
      if (!state.composerOpen) sheet.hidden = true;
    }, 220);

    if (reset) UI.setEditMode(null);
    _syncTelegramBackButton();
  }

  function _normalizeDigits(str) {
    return String(str || "")
      .replace(/[۰-۹]/g, d => String(d.charCodeAt(0) - 1776))
      .replace(/[٠-٩]/g, d => String(d.charCodeAt(0) - 1632));
  }

  function _normalizeDateInput(str) {
    return _normalizeDigits(str)
      .trim()
      .replace(/\s+/g, "")
      .replace(/[.,،\-]+/g, "/")
      .replace(/\/+/g, "/");
  }

  function _autoFormatJalaliInput(str) {
    const normalized = _normalizeDateInput(str);
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
    return { y: Number(m[1]), m: Number(m[2]), d: Number(m[3]) };
  }

  function _validateDate(s) {
    const p = _parseIsoParts(s);
    if (!p) return false;
    const dt = new Date(p.y, p.m - 1, p.d);
    return dt.getFullYear() === p.y && dt.getMonth() === p.m - 1 && dt.getDate() === p.d;
  }

  function _dateFromIsoLocal(dateIso) {
    const p = _parseIsoParts(dateIso);
    if (!p) return null;
    const dt = new Date(p.y, p.m - 1, p.d);
    if (dt.getFullYear() !== p.y || dt.getMonth() !== p.m - 1 || dt.getDate() !== p.d) return null;
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

  function _sortEvents(arr) {
    return [...arr].sort((a, b) => {
      if (Boolean(a.pinned) !== Boolean(b.pinned)) return a.pinned ? -1 : 1;
      const ad = _dateFromIsoLocal(a.date_iso);
      const bd = _dateFromIsoLocal(b.date_iso);
      if (!ad && !bd) return 0;
      if (!ad) return 1;
      if (!bd) return -1;
      return ad - bd;
    });
  }

  function _getEventById(id) {
    return state.events.find(e => e.id === id) || null;
  }

  function _updateEventInState(id, patch) {
    let changed = false;
    state.events = state.events.map(event => {
      if (event.id !== id) return event;
      changed = true;
      return { ...event, ...patch };
    });

    if (changed) {
      state.events = _sortEvents(state.events);
      Cache.save(state.events);
    }

    return changed;
  }

  function _safeCategory(value) {
    return CATEGORY_CONFIG[value] ? value : "general";
  }

  function _safeRepeat(value) {
    return REPEAT_CONFIG[value] ? value : "none";
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
        365 * jy +
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
      const salA = [
        0,
        31,
        ((gy % 4 === 0 && gy % 100 !== 0) || gy % 400 === 0) ? 29 : 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31
      ];

      let gm = 1;
      while (gm <= 12 && gd > salA[gm]) {
        gd -= salA[gm];
        gm++;
      }

      return `${gy}-${String(gm).padStart(2, "0")}-${String(gd).padStart(2, "0")}`;
    },

    _j2(gy, gm, gd) {
      const gDays = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
      const jDays = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29];
      let jy, jm, jd, gDayNo, jDayNo, jNp, i;

      gy -= 1600;
      gm -= 1;
      gd -= 1;

      gDayNo = 365 * gy + Math.floor((gy + 3) / 4) - Math.floor((gy + 99) / 100) + Math.floor((gy + 399) / 400);
      for (i = 0; i < gm; ++i) gDayNo += gDays[i];
      if (gm > 1 && ((gy + 1600) % 4 === 0 && ((gy + 1600) % 100 !== 0 || (gy + 1600) % 400 === 0))) {
        ++gDayNo;
      }
      gDayNo += gd;

      jDayNo = gDayNo - 79;
      jNp = Math.floor(jDayNo / 12053);
      jDayNo %= 12053;

      jy = 979 + 33 * jNp + 4 * Math.floor(jDayNo / 1461);
      jDayNo %= 1461;

      if (jDayNo >= 366) {
        jy += Math.floor((jDayNo - 1) / 365);
        jDayNo = (jDayNo - 1) % 365;
      }

      for (i = 0; i < 11 && jDayNo >= jDays[i]; ++i) jDayNo -= jDays[i];
      jm = i + 1;
      jd = jDayNo + 1;

      return `${jy}/${String(jm).padStart(2, "0")}/${String(jd).padStart(2, "0")}`;
    },

    parse(str) {
      const normalized = _autoFormatJalaliInput(str);
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
      years -= 1;
      cursor = _shiftDate(today, years, 0);
    }

    let months = (event.getFullYear() - cursor.getFullYear()) * 12 + (event.getMonth() - cursor.getMonth());
    if (months < 0) months = 0;

    let monthCursor = _shiftDate(cursor, 0, months);
    if (monthCursor > event) {
      months -= 1;
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
      this._controllers[url]?.abort?.();
      this._controllers[url] = new AbortController();

      const res = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Telegram-Init-Data": tg.initData || ""
        },
        body: JSON.stringify({
          timezone: state.userTZ,
          ...payload
        }),
        signal: this._controllers[url].signal
      });

      if (res.status === 429) throw new Error("RATE_LIMIT");
      if (res.status === 403) throw new Error("AUTH_FAILED");
      if (!res.ok) throw new Error("API_ERROR");

      return res.json();
    }
  };

  const UI = {
    _buildCard(event) {
      const urgency = getUrgency(event.date_iso);
      const repeat = REPEAT_CONFIG[_safeRepeat(event.repeat)] || REPEAT_CONFIG.none;
      const categoryKey = _safeCategory(event.category);
      const category = CATEGORY_CONFIG[categoryKey];
      const countdown = getCountdown(event.date_iso);
      const safeStatus = VALID_STATUSES.has(event.notify_status) ? event.notify_status : "pending";

      const card = document.createElement("div");
      card.className = `card urgency-${urgency} ${event.optimistic ? "syncing" : ""}`;
      card.dataset.id = event.id;
      card.addEventListener("click", ev => {
        if (ev.target.closest(".card-actions")) return;
        TimeManager.showDetail(event);
      });

      const top = document.createElement("div");
      top.className = "card-top";

      const title = document.createElement("div");
      title.className = "card-title";
      title.textContent = `${event.pinned ? "📌 " : ""}${event.title}`;

      const badgeWrap = document.createElement("div");
      badgeWrap.style.display = "flex";
      badgeWrap.style.gap = "6px";
      badgeWrap.style.flexWrap = "wrap";
      badgeWrap.style.justifyContent = "flex-end";

      const repeatBadge = document.createElement("span");
      repeatBadge.className = "repeat-badge";
      repeatBadge.textContent = `${repeat.icon} ${repeat.label}`;
      repeatBadge.style.setProperty("--badge-color", repeat.color);

      const categoryBadge = document.createElement("span");
      categoryBadge.className = "repeat-badge";
      categoryBadge.textContent = `${category.icon} ${category.label}`;
      categoryBadge.style.setProperty("--badge-color", "#607d8b");

      badgeWrap.appendChild(categoryBadge);
      badgeWrap.appendChild(repeatBadge);
      top.appendChild(title);
      top.appendChild(badgeWrap);

      const dateRow = document.createElement("div");
      dateRow.className = "card-date-row";

      const dG = document.createElement("span");
      dG.className = "card-date";
      dG.textContent = event.date_iso || "";

      const sep = document.createElement("span");
      sep.className = "date-sep";
      sep.textContent = " • ";

      const dJ = document.createElement("span");
      dJ.className = "card-date jalali";
      dJ.textContent = event.date_jalali || Jalali.display(event.date_iso);

      dateRow.appendChild(dG);
      dateRow.appendChild(sep);
      dateRow.appendChild(dJ);

      const cdEl = document.createElement("div");
      cdEl.className = "card-countdown";
      if (countdown.today) cdEl.textContent = "🎉 Today!";
      else if (countdown.passed) cdEl.textContent = `⌛ ${formatCountdownShort(countdown)}`;
      else cdEl.textContent = `⏳ ${formatCountdownShort(countdown)} left`;

      const statusEl = document.createElement("div");
      statusEl.className = `card-status status-${safeStatus}`;
      statusEl.textContent = STATUS_LABELS[safeStatus] || "";
      statusEl.style.marginTop = "2px";

      const actions = document.createElement("div");
      actions.className = "card-actions";

      if (!event.optimistic) {
        const editBtn = document.createElement("button");
        editBtn.className = "btn-icon btn-edit";
        editBtn.type = "button";
        editBtn.textContent = "✏️";
        editBtn.setAttribute("aria-label", "Edit event");
        editBtn.onclick = ev => {
          ev.stopPropagation();
          TimeManager.startEdit(event);
        };

        const delBtn = document.createElement("button");
        delBtn.className = "btn-icon btn-delete";
        delBtn.type = "button";
        delBtn.textContent = "🗑️";
        delBtn.setAttribute("aria-label", "Delete event");
        delBtn.onclick = ev => {
          ev.stopPropagation();
          TimeManager.deleteEvent(event.id);
        };

        actions.appendChild(editBtn);
        actions.appendChild(delBtn);
      }

      card.appendChild(top);
      card.appendChild(dateRow);
      card.appendChild(cdEl);
      card.appendChild(statusEl);

      if (event.note) {
        const notePreview = document.createElement("div");
        notePreview.className = "card-date";
        notePreview.textContent = `📝 ${event.note.slice(0, 80)}${event.note.length > 80 ? "…" : ""}`;
        card.appendChild(notePreview);
      }

      card.appendChild(actions);
      return card;
    },

    renderList() {
      const root = document.getElementById("list");
      if (!root) return;
      root.innerHTML = "";

      if (state.loading && state.events.length === 0) {
        root.innerHTML = '<div class="loader"><span class="spinner"></span> Syncing…</div>';
        return;
      }

      if (state.events.length === 0) {
        root.innerHTML = '<div class="empty">📅 No events yet.<br><small>Tap "Add event" to create one.</small></div>';
        return;
      }

      const frag = document.createDocumentFragment();
      _sortEvents(state.events).forEach(event => frag.appendChild(this._buildCard(event)));
      root.appendChild(frag);
    },

    renderDetail(event) {
      const root = document.getElementById("list");
      if (!root) return;
      root.innerHTML = "";

      const countdown = getCountdown(event.date_iso);
      const urgency = getUrgency(event.date_iso);
      const repeat = REPEAT_CONFIG[_safeRepeat(event.repeat)] || REPEAT_CONFIG.none;
      const category = CATEGORY_CONFIG[_safeCategory(event.category)];
      const safeStatus = VALID_STATUSES.has(event.notify_status) ? event.notify_status : "pending";
      const jalali = event.date_jalali || Jalali.display(event.date_iso);

      const wrap = document.createElement("div");
      wrap.className = "detail-wrap";

      const title = document.createElement("h2");
      title.className = "detail-title";
      title.textContent = `${event.pinned ? "📌 " : ""}${event.title}`;

      const dates = document.createElement("div");
      dates.className = "detail-dates";

      const makeDateItem = (labelText, valueText, valueExtraClass = "") => {
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

      dates.appendChild(makeDateItem("📅 Gregorian", event.date_iso));
      dates.appendChild(makeDateItem("📅 Jalali", jalali, "jalali"));

      const cdBox = document.createElement("div");
      cdBox.className = `countdown-box urgency-bg-${urgency}`;

      if (countdown.today) {
        const cdMain = document.createElement("div");
        cdMain.className = "cd-main";
        cdMain.textContent = "🎉";

        const cdLabel = document.createElement("div");
        cdLabel.className = "cd-label";
        cdLabel.textContent = "Today is the day!";

        cdBox.appendChild(cdMain);
        cdBox.appendChild(cdLabel);
      } else if (countdown.passed) {
        const cdMain = document.createElement("div");
        cdMain.className = "cd-main";
        cdMain.textContent = countdown.totalDays;

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

        const addRow = (num, unit) => {
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

        if (countdown.years > 0) addRow(countdown.years, "years");
        if (countdown.months > 0) addRow(countdown.months, "months");
        if (countdown.weeks > 0) addRow(countdown.weeks, "weeks");
        if (countdown.days > 0) addRow(countdown.days, "days");
        if (!countdown.years && !countdown.months && !countdown.weeks && !countdown.days) addRow(0, "days");

        const cdLabel = document.createElement("div");
        cdLabel.className = "cd-label";
        cdLabel.textContent = formatCountdownLong(countdown);

        cdBox.appendChild(cdTitle);
        cdBox.appendChild(cdGrid);
        cdBox.appendChild(cdLabel);
      }

      const meta = document.createElement("div");
      meta.className = "detail-meta";

      const makeMetaItem = (valueText, labelText, valueClass = "") => {
        const item = document.createElement("div");
        item.className = "meta-item";

        const value = document.createElement("span");
        value.className = valueClass;
        value.textContent = valueText;

        const lbl = document.createElement("span");
        lbl.className = "meta-label";
        lbl.textContent = labelText;

        item.appendChild(value);
        item.appendChild(lbl);
        return item;
      };

      meta.appendChild(makeMetaItem(`${repeat.icon} ${repeat.label}`, "Repeat"));
      meta.appendChild(makeMetaItem(`${category.icon} ${category.label}`, "Category"));
      meta.appendChild(makeMetaItem(event.pinned ? "📌 Pinned" : "—", "Pin"));
      meta.appendChild(makeMetaItem(STATUS_LABELS[safeStatus] || "", "Notification", `status-${safeStatus}`));

      wrap.appendChild(title);
      wrap.appendChild(dates);
      wrap.appendChild(cdBox);
      wrap.appendChild(meta);

      const tpl = document.getElementById("detailExtrasTemplate");
      if (tpl?.content) {
        const frag = tpl.content.cloneNode(true);

        const shareBtn = frag.querySelector('[data-action="share"]');
        const pinBtn = frag.querySelector('[data-action="pin"]');
        const noteInput = frag.querySelector("#detail-note");
        const noteSaveBtn = frag.querySelector("#noteSaveBtn");
        const noteCancelBtn = frag.querySelector("#noteCancelBtn");
        const noteSection = frag.querySelector(".detail-notes");

        if (shareBtn) {
          shareBtn.textContent = "🔥 Share";
          shareBtn.onclick = () => TimeManager.shareEvent(event.id);
        }

        if (pinBtn) {
          pinBtn.textContent = event.pinned ? "📌 Unpin" : "📌 Pin";
          pinBtn.onclick = () => TimeManager.togglePin(event.id, !event.pinned);
        }

        if (noteInput) {
          noteInput.value = event.note || "";

          const counter = document.createElement("div");
          counter.className = "meta-label";
          counter.style.marginTop = "8px";

          const renderCount = () => {
            counter.textContent = `${noteInput.value.length}/2000`;
            if (noteSaveBtn) {
              noteSaveBtn.disabled = noteInput.value === (event.note || "");
            }
          };

          noteInput.addEventListener("input", renderCount);
          renderCount();
          noteSection?.appendChild(counter);
        }

        if (noteSaveBtn && noteInput) {
          noteSaveBtn.onclick = () => TimeManager.saveNote(event.id, noteInput.value);
        }

        if (noteCancelBtn && noteInput) {
          noteCancelBtn.onclick = () => {
            noteInput.value = event.note || "";
            noteInput.dispatchEvent(new Event("input"));
          };
        }

        wrap.appendChild(frag);
      }

      root.appendChild(wrap);
    },

    showToast(message, type = "success") {
      let toast = document.getElementById("toast");
      if (!toast) {
        toast = document.createElement("div");
        toast.id = "toast";
        document.body.appendChild(toast);
      }

      toast.textContent = message;
      toast.className = `toast toast-${type} show`;
      clearTimeout(toast._tid);
      toast._tid = setTimeout(() => toast.classList.remove("show"), 2800);
    },

    setEditMode(event = null) {
      const form = document.getElementById("eventForm");
      const titleEl = document.getElementById("title");
      const dateEl = document.getElementById("date");
      const jalaliEl = document.getElementById("date-jalali");
      const repeatEl = document.getElementById("repeat");
      const categoryEl = document.getElementById("category");
      const pinEl = document.getElementById("pin");
      const addBtn = document.getElementById("addBtn");
      const cancelBtn = document.getElementById("cancelBtn");

      if (!titleEl || !dateEl || !repeatEl || !categoryEl || !pinEl || !addBtn || !cancelBtn) return;

      if (event) {
        titleEl.value = event.title || "";
        dateEl.value = event.date_iso || "";
        if (jalaliEl) jalaliEl.value = event.date_jalali || Jalali.display(event.date_iso);
        repeatEl.value = _safeRepeat(event.repeat);
        categoryEl.value = _safeCategory(event.category);
        pinEl.checked = Boolean(event.pinned);
        addBtn.textContent = "💾 Save";
        cancelBtn.style.display = "block";
        state.editingId = event.id;
        form?.scrollIntoView({ behavior: "smooth", block: "nearest" });
        titleEl.focus();
      } else {
        titleEl.value = "";
        dateEl.value = "";
        if (jalaliEl) jalaliEl.value = "";
        repeatEl.value = "none";
        categoryEl.value = "general";
        pinEl.checked = false;
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

    const formatted = _autoFormatJalaliInput(raw);
    if (jalaliEl && jalaliEl.value !== formatted) jalaliEl.value = formatted;

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

    if (dateEl) dateEl.style.borderColor = "";
  }

  function _buildShareText(event) {
    const category = CATEGORY_CONFIG[_safeCategory(event.category)];
    const countdown = getCountdown(event.date_iso);

    const timeLine = countdown.today
      ? "Today!"
      : countdown.passed
        ? `${countdown.totalDays} day${countdown.totalDays > 1 ? "s" : ""} ago`
        : `${formatCountdownShort(countdown)} left`;

    return [
      `${event.pinned ? "📌 " : ""}${event.title}`,
      `📅 ${event.date_iso} • ${event.date_jalali || Jalali.display(event.date_iso)}`,
      `${category.icon} ${category.label}`,
      `⏳ ${timeLine}`,
      event.note ? `📝 ${event.note}` : ""
    ].filter(Boolean).join("\n");
  }

  function _telegramBackHandler() {
    if (state.composerOpen) {
      _closeComposer(false);
      if (history.state?.tmMode === "composer") history.back();
      return;
    }

    if (state.view === "detail") {
      TimeManager.showList();
      if (history.state?.tmMode === "detail") history.back();
    }
  }

  return {
    init() {
      tg.expand?.();
      tg.ready?.();
      this._applyTheme();
      tg.onEvent?.("themeChanged", () => this._applyTheme());

      const form = document.getElementById("eventForm");
      const titleEl = document.getElementById("title");
      const dateEl = document.getElementById("date");
      const jalaliEl = document.getElementById("date-jalali");
      const repeatEl = document.getElementById("repeat");
      const categoryEl = document.getElementById("category");
      const pinEl = document.getElementById("pin");
      const addBtn = document.getElementById("addBtn");
      const cancelBtn = document.getElementById("cancelBtn");
      const openComposerBtn = document.getElementById("openComposerBtn");
      const composerOverlay = document.getElementById("composerOverlay");

      history.replaceState({ tmMode: "list", t: Date.now() }, "");
      _syncTelegramBackButton();

      try {
        tg.BackButton?.onClick?.(_telegramBackHandler);
      } catch {}

      let jalaliDebounce;
      if (jalaliEl) {
        jalaliEl.addEventListener("input", () => {
          const formatted = _autoFormatJalaliInput(jalaliEl.value);
          if (formatted !== jalaliEl.value) jalaliEl.value = formatted;
          clearTimeout(jalaliDebounce);
          jalaliDebounce = setTimeout(() => _syncJalaliToGregorian(jalaliEl.value), 250);
        });
      }

      if (dateEl) {
        dateEl.addEventListener("change", () => _syncGregorianToJalali(dateEl.value));
      }

      if (form) {
        form.addEventListener("submit", ev => {
          ev.preventDefault();
          this.add(titleEl?.value, dateEl?.value, repeatEl?.value, categoryEl?.value, pinEl?.checked);
        });
      }

      if (addBtn && !form) {
        addBtn.addEventListener("click", () => {
          this.add(titleEl?.value, dateEl?.value, repeatEl?.value, categoryEl?.value, pinEl?.checked);
        });
      }

      if (cancelBtn) {
        cancelBtn.addEventListener("click", () => {
          this.cancelEdit();
          if (history.state?.tmMode === "composer") history.back();
        });
      }

      if (titleEl) {
        titleEl.addEventListener("keydown", ev => {
          if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.add(titleEl.value, dateEl?.value, repeatEl?.value, categoryEl?.value, pinEl?.checked);
          }
        });
      }

      if (openComposerBtn) {
        openComposerBtn.addEventListener("click", () => {
          UI.setEditMode(null);
          _openComposer(true);
        });
      }

      if (composerOverlay) {
        composerOverlay.addEventListener("click", () => {
          _closeComposer(false);
          history.back();
        });
      }

      window.addEventListener("popstate", () => {
        if (state.composerOpen) {
          _closeComposer(false);
          return;
        }

        if (state.view === "detail") {
          this.showList(false);
        }

        _syncTelegramBackButton();
      });

      state.events = _sortEvents(Cache.load());
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
          state.events = _sortEvents(res.targets || []);
          Cache.save(state.events);

          if (state.view === "detail" && state.detailId) {
            const current = _getEventById(state.detailId);
            if (current) UI.renderDetail(current);
            else this.showList();
          }
        }
      } catch (e) {
        if (e.name !== "AbortError") console.warn("Sync:", e.message);
      }

      state.loading = false;
      scheduleRender();
    },

    showDetail(event, push = true) {
      state.view = "detail";
      state.detailId = event.id;
      _closeComposer(false);
      UI.renderDetail(event);
      if (push) _pushAppState("detail");
      else _syncTelegramBackButton();
      tg.HapticFeedback?.impactOccurred?.("light");
    },

    showList(push = false) {
      state.view = "list";
      state.detailId = null;
      scheduleRender();
      if (push) _pushAppState("list");
      else _syncTelegramBackButton();
    },

    async add(title, date, repeat, category, pinned) {
      title = String(title || "").trim();
      date = String(date || "").trim();
      repeat = _safeRepeat(repeat);
      category = _safeCategory(category);
      pinned = Boolean(pinned);

      if (!title) return UI.showToast("⚠️ Enter a title.", "error");
      if (!_validateDate(date)) return UI.showToast("⚠️ Invalid date.", "error");
      if (title.length > 200) return UI.showToast("⚠️ Title too long.", "error");

      if (state.editingId) {
        return this.saveEdit(title, date, repeat, category, pinned);
      }

      const addBtn = document.getElementById("addBtn");
      if (addBtn) addBtn.disabled = true;

      const tempId = `tmp_${Date.now()}`;
      state.events = _sortEvents([
        {
          id: tempId,
          title,
          date_iso: date,
          date_jalali: Jalali.display(date),
          repeat,
          category,
          pinned,
          note: "",
          optimistic: true,
          notify_status: "pending"
        },
        ...state.events
      ]);

      scheduleRender();
      tg.HapticFeedback?.impactOccurred?.("medium");

      try {
        const res = await API.request("/api/add", {
          title,
          date,
          date_jalali: Jalali.display(date),
          repeat,
          category,
          pinned,
          note: ""
        });

        if (res.success) {
          UI.setEditMode(null);
          _closeComposer(true);
          UI.showToast("✅ Added!");
          await this.sync();
        }
      } catch (e) {
        state.events = state.events.filter(ev => ev.id !== tempId);
        scheduleRender();
        tg.HapticFeedback?.notificationOccurred?.("error");
        UI.showToast(
          e.message === "RATE_LIMIT"
            ? "⚠️ Too many requests."
            : e.message === "AUTH_FAILED"
              ? "🔒 Authorization failed."
              : "❌ Failed.",
          "error"
        );
      } finally {
        if (addBtn) addBtn.disabled = false;
      }
    },

    startEdit(event) {
      UI.setEditMode(event);
      _openComposer(true);
      tg.HapticFeedback?.impactOccurred?.("light");
    },

    cancelEdit() {
      UI.setEditMode(null);
      _closeComposer(false);
      tg.HapticFeedback?.impactOccurred?.("light");
    },

    async saveEdit(title, date, repeat, category, pinned) {
      const eventId = state.editingId;
      if (!eventId) return;

      const existing = _getEventById(eventId);
      const note = existing?.note || "";
      const addBtn = document.getElementById("addBtn");
      if (addBtn) addBtn.disabled = true;

      tg.HapticFeedback?.impactOccurred?.("medium");

      try {
        const res = await API.request("/api/edit", {
          event_id: eventId,
          title,
          date,
          date_jalali: Jalali.display(date),
          repeat,
          category,
          pinned,
          note
        });

        if (res.success) {
          UI.setEditMode(null);
          _closeComposer(true);
          UI.showToast("✅ Updated!");
          await this.sync();
        }
      } catch (e) {
        tg.HapticFeedback?.notificationOccurred?.("error");
        UI.showToast(
          e.message === "AUTH_FAILED" ? "🔒 Authorization failed." : "❌ Failed.",
          "error"
        );
      } finally {
        if (addBtn) addBtn.disabled = false;
      }
    },

    deleteEvent(eventId) {
      tg.showPopup(
        {
          title: "Delete",
          message: "Delete this event?",
          buttons: [
            { id: "yes", type: "destructive", text: "Delete" },
            { id: "no", type: "cancel" }
          ]
        },
        async btn => {
          if (btn !== "yes") return;

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
        }
      );
    },

    async saveNote(eventId, note) {
      note = String(note || "")
        .replace(/\r\n/g, "\n")
        .replace(/\r/g, "\n")
        .trim();

      if (note.length > 2000) {
        return UI.showToast("⚠️ Note is too long.", "error");
      }

      const existing = _getEventById(eventId);
      if (!existing) return;

      const prevNote = existing.note || "";
      if (prevNote === note) {
        return UI.showToast("ℹ️ No changes to save.", "success");
      }

      _updateEventInState(eventId, { note });

      if (state.view === "detail" && state.detailId === eventId) {
        UI.renderDetail(_getEventById(eventId));
      }

      tg.HapticFeedback?.impactOccurred?.("light");

      try {
        const res = await API.request("/api/note", { event_id: eventId, note });
        if (res.success) {
          UI.showToast("📝 Note saved.");
        }
      } catch {
        _updateEventInState(eventId, { note: prevNote });
        if (state.view === "detail" && state.detailId === eventId) {
          UI.renderDetail(_getEventById(eventId));
        }
        UI.showToast("❌ Note save failed.", "error");
      }
    },

    async togglePin(eventId, forcedValue = null) {
      const existing = _getEventById(eventId);
      if (!existing) return;

      const nextPinned = typeof forcedValue === "boolean" ? forcedValue : !Boolean(existing.pinned);
      const prevPinned = Boolean(existing.pinned);

      _updateEventInState(eventId, { pinned: nextPinned });
      scheduleRender();

      if (state.view === "detail" && state.detailId === eventId) {
        UI.renderDetail(_getEventById(eventId));
      }

      tg.HapticFeedback?.impactOccurred?.("medium");

      try {
        const res = await API.request("/api/pin", {
          event_id: eventId,
          pinned: nextPinned
        });

        if (res.success) {
          UI.showToast(nextPinned ? "📌 Pinned." : "📍 Unpinned.");
        }
      } catch {
        _updateEventInState(eventId, { pinned: prevPinned });
        scheduleRender();
        if (state.view === "detail" && state.detailId === eventId) {
          UI.renderDetail(_getEventById(eventId));
        }
        UI.showToast("❌ Pin update failed.", "error");
      }
    },

    async shareEvent(eventId) {
      const event = _getEventById(eventId);
      if (!event) return;

      const shareText = _buildShareText(event);

      try {
        if (typeof tg.switchInlineQuery === "function") {
          tg.switchInlineQuery(shareText, ["users", "groups", "channels"]);
          UI.showToast("🔥 Share mode opened.");
          return;
        }
      } catch {}

      try {
        if (navigator.share) {
          await navigator.share({ text: shareText, title: event.title });
          UI.showToast("✅ Shared.");
          return;
        }
      } catch {}

      try {
        if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(shareText);
          UI.showToast("📋 Copied to clipboard.");
          return;
        }
      } catch {}

      UI.showToast("❌ Share not available.", "error");
    }
  };
})();

window.TimeManager = TimeManager;
window.addEventListener("load", () => TimeManager.init());
