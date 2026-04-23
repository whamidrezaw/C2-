(() => {
  const tg = window.Telegram?.WebApp || null;

  function fatal(message) {
    console.error("[TM_FATAL]", message);
    document.body.innerHTML = `
      <div style="padding: 20px; text-align: center; color: red;">
        <h2>⚠️ Error</h2>
        <p>${message}</p>
      </div>
    `;
  }

  console.log("[DEBUG] window.Telegram:", !!window.Telegram);
  console.log("[DEBUG] tg object:", !!tg);

  if (!tg) {
    fatal("This application only works inside Telegram. Please open it from Telegram Mini App.");
    return;
  }

  try {
    tg.ready();
    tg.expand();
  } catch (_) {}

  const initData = tg.initData || "";
  console.log("[DEBUG] initData length:", initData.length);

  if (!initData) {
    fatal("Telegram Mini App could not authenticate. Please reopen the Mini App.");
    return;
  }

  const state = {
    events: [],
    filteredEvents: [],
    currentFilter: "all",
    searchTerm: "",
    activeSheet: null,
    detailEventId: null,
    editingEventId: null,
    lastFocusedElement: null,
    initData,
  };

  const els = {
    syncStatus: document.getElementById("syncStatus"),
    eventCount: document.getElementById("eventCount"),
    refreshBtn: document.getElementById("refreshBtn"),
    retryBtn: document.getElementById("retryBtn"),
    emptyAddBtn: document.getElementById("emptyAddBtn"),
    searchInput: document.getElementById("searchInput"),
    filterButtons: [...document.querySelectorAll("[data-filter]")],
    eventsWrap: document.getElementById("eventsWrap"),
    listState: document.getElementById("listState"),
    listErrorState: document.getElementById("listErrorState"),
    toast: document.getElementById("toast"),

    openComposerBtn: document.getElementById("openComposerBtn"),
    closeComposerX: document.getElementById("closeComposerX"),
    cancelBtn: document.getElementById("cancelBtn"),
    saveEventBtn: document.getElementById("saveEventBtn"),
    composerSheet: document.getElementById("composerSheet"),

    detailSheet: document.getElementById("detailSheet"),
    closeDetailX: document.getElementById("closeDetailX"),
    detailEditBtn: document.getElementById("detailEditBtn"),
    detailShareBtn: document.getElementById("detailShareBtn"),
    detailPinBtn: document.getElementById("detailPinBtn"),
    detailDeleteBtn: document.getElementById("detailDeleteBtn"),
    detailNote: document.getElementById("detailNote"),
    detailNoteSaveBtn: document.getElementById("detailNoteSaveBtn"),
    detailNoteCancelBtn: document.getElementById("detailNoteCancelBtn"),

    detailEventTitle: document.getElementById("detailEventTitle"),
    detailCategoryBadge: document.getElementById("detailCategoryBadge"),
    detailRepeatBadge: document.getElementById("detailRepeatBadge"),
    detailDateIso: document.getElementById("detailDateIso"),
    detailDateJalali: document.getElementById("detailDateJalali"),
    detailTimezone: document.getElementById("detailTimezone"),
    detailStatus: document.getElementById("detailStatus"),

    eventForm: document.getElementById("eventForm"),
    eventId: document.getElementById("eventId"),
    title: document.getElementById("title"),
    date: document.getElementById("date"),
    dateJalali: document.getElementById("date-jalali"),
    repeat: document.getElementById("repeat"),
    category: document.getElementById("category"),
    pin: document.getElementById("pin"),
    note: document.getElementById("note"),
    composerTitle: document.getElementById("composerTitle"),
    composerSubtitle: document.getElementById("composerSubtitle"),

    sheetOverlay: document.getElementById("sheetOverlay"),
  };

  const CATEGORY_LABELS = {
    general: "General",
    birthday: "Birthday",
    work: "Work",
    family: "Family",
    health: "Health",
    travel: "Travel",
    finance: "Finance",
    study: "Study",
    other: "Other",
  };

  const REPEAT_LABELS = {
    none: "One time",
    daily: "Daily",
    weekly: "Weekly",
    monthly: "Monthly",
    yearly: "Yearly",
  };

  const STATUS_LABELS = {
    pending: "Pending",
    processing: "Processing",
    done: "Sent",
    failed: "Failed",
  };

  function initTelegram() {
    try {
      applyTelegramTheme();
      if (typeof tg.setHeaderColor === "function") {
        tg.setHeaderColor("secondary_bg_color");
      }
      if (typeof tg.setBackgroundColor === "function") {
        tg.setBackgroundColor(tg.themeParams?.bg_color || "#ffffff");
      }
      tg.onEvent?.("themeChanged", applyTelegramTheme);
    } catch (_) {}
  }

  function applyTelegramTheme() {
    if (!tg?.themeParams) return;
    const p = tg.themeParams;
    const root = document.documentElement;

    if (p.bg_color) root.style.setProperty("--tg-bg", p.bg_color);
    if (p.secondary_bg_color) root.style.setProperty("--tg-surface", p.secondary_bg_color);
    if (p.text_color) root.style.setProperty("--tg-text", p.text_color);
    if (p.hint_color) root.style.setProperty("--tg-muted", p.hint_color);
    if (p.button_color) root.style.setProperty("--tg-primary", p.button_color);
    if (p.button_text_color) root.style.setProperty("--tg-primary-text", p.button_text_color);
    if (p.destructive_text_color) root.style.setProperty("--tg-danger", p.destructive_text_color);
    if (p.link_color) root.style.setProperty("--tg-link", p.link_color);
  }

  function setSyncStatus(text) {
    if (els.syncStatus) els.syncStatus.textContent = text;
  }

  function setLoading(loading) {
    document.body.classList.toggle("is-loading", loading);
    setSyncStatus(loading ? "Syncing" : "Ready");
  }

  function showToast(message, type = "info") {
    if (!els.toast) {
      alert(message);
      return;
    }
    els.toast.textContent = message;
    els.toast.dataset.type = type;
    els.toast.classList.add("is-visible");

    window.clearTimeout(showToast._t);
    showToast._t = window.setTimeout(() => {
      els.toast.classList.remove("is-visible");
    }, 2400);
  }

  function getInitData() {
    return state.initData;
  }

  async function apiPost(path, payload) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        initData: getInitData(),
        ...payload,
      }),
    });

    let data = null;
    try {
      data = await response.json();
    } catch (_) {}

    console.log("[DEBUG] POST", path, "status=", response.status, "data=", data);

    if (!response.ok) {
      const detail = data?.detail || "REQUEST_FAILED";
      throw new Error(detail);
    }

    return data;
  }

  function normalizeErrorMessage(error) {
    const detail = error?.message || "";
    const map = {
      NO_DATA: "Telegram authentication data is missing.",
      BAD_HASH: "The Telegram request is invalid.",
      EXPIRED: "The Mini App session has expired. Please reopen the page.",
      INVALID_DATE: "The entered date is invalid.",
      TITLE_TOO_LONG: "The title is too long.",
      NOTE_TOO_LONG: "The note is too long.",
      EVENT_LIMIT_REACHED: "You have reached the event limit.",
      RATE_LIMIT: "Too many requests. Please try again in a moment.",
      NOT_FOUND_OR_UNAUTHORIZED: "This event was not found or you do not have access to it.",
      REQUEST_FAILED: "The request failed.",
      NO_HASH: "Telegram authentication data is incomplete.",
      NO_USER: "User information was not received from Telegram.",
      INVALID_AUTH_DATE: "The authentication time is invalid.",
      INVALID_INIT_DATA: "The data received from Telegram is invalid.",
      MISCONFIGURED: "The server configuration is incomplete.",
    };
    return map[detail] || `An error occurred: ${detail || "UNKNOWN"}`;
  }

  async function loadEvents() {
    setLoading(true);
    if (els.listErrorState) els.listErrorState.hidden = true;

    try {
      const data = await apiPost("/api/list", { skip: 0 });
      state.events = Array.isArray(data.targets) ? data.targets : [];
      state.filteredEvents = [...state.events];
      renderEvents();
      updateCounters();
      showEmptyOrError();
    } catch (error) {
      console.error("[DEBUG] loadEvents failed:", error);
      state.events = [];
      state.filteredEvents = [];
      renderEvents();
      if (els.listState) els.listState.hidden = true;
      if (els.listErrorState) els.listErrorState.hidden = false;
      showToast(normalizeErrorMessage(error), "error");
      setSyncStatus("Error");
    } finally {
      setLoading(false);
    }
  }

  function updateCounters() {
    if (els.eventCount) els.eventCount.textContent = String(state.events.length);
  }

  function showEmptyOrError() {
    if (!els.listState) return;

    const hasEvents = state.events.length > 0;
    const hasFiltered = state.filteredEvents.length > 0;

    if (els.listErrorState) els.listErrorState.hidden = true;
    els.listState.hidden = true;

    if (!hasEvents) {
      els.listState.hidden = false;
      const title = els.listState.querySelector(".empty-state-title");
      const text = els.listState.querySelector(".empty-state-text");
      if (title) title.textContent = "No events yet";
      if (text) text.textContent = "Add your first event to receive reminders directly in Telegram.";
      if (els.emptyAddBtn) els.emptyAddBtn.hidden = false;
    } else if (hasEvents && !hasFiltered) {
      els.listState.hidden = false;
      const title = els.listState.querySelector(".empty-state-title");
      const text = els.listState.querySelector(".empty-state-text");
      if (title) title.textContent = "No results found";
      if (text) text.textContent = "Change the filter or search term.";
      if (els.emptyAddBtn) els.emptyAddBtn.hidden = true;
    }
  }

  function applyFilters() {
    const q = state.searchTerm.trim().toLowerCase();

    state.filteredEvents = state.events.filter((item) => {
      const matchesFilter =
        state.currentFilter === "all"
          ? true
          : state.currentFilter === "pinned"
          ? item.pinned
          : item.category === state.currentFilter;

      const haystack = `${item.title} ${item.note || ""} ${item.date_iso} ${item.date_jalali}`.toLowerCase();
      const matchesSearch = !q || haystack.includes(q);

      return matchesFilter && matchesSearch;
    });
  }
function startOfLocalDay(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function addMonthsSafe(date, months) {
  const d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const originalDay = d.getDate();
  d.setDate(1);
  d.setMonth(d.getMonth() + months);
  const lastDay = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
  d.setDate(Math.min(originalDay, lastDay));
  return d;
}

function diffCalendarParts(fromDate, toDate) {
  let cursor = startOfLocalDay(fromDate);
  const target = startOfLocalDay(toDate);

  if (target < cursor) {
    return { past: true, years: 0, months: 0, weeks: 0, days: 0, totalDays: Math.ceil((cursor - target) / 86400000) };
  }

  let years = 0;
  let months = 0;

  while (true) {
    const next = addMonthsSafe(cursor, 12);
    if (next <= target) {
      years += 1;
      cursor = next;
    } else {
      break;
    }
  }

  while (true) {
    const next = addMonthsSafe(cursor, 1);
    if (next <= target) {
      months += 1;
      cursor = next;
    } else {
      break;
    }
  }

  const remainingDays = Math.ceil((target - cursor) / 86400000);
  const weeks = Math.floor(remainingDays / 7);
  const days = remainingDays % 7;
  const totalDays = Math.ceil((target - startOfLocalDay(fromDate)) / 86400000);

  return { past: false, years, months, weeks, days, totalDays };
}

function formatPart(value, label) {
  return value > 0 ? `${value} ${label}` : "";
}

function getCountdownData(dateIso) {
  const today = startOfLocalDay(new Date());
  const target = startOfLocalDay(new Date(`${dateIso}T00:00:00`));
  const diff = diffCalendarParts(today, target);

  if (diff.past) {
    return {
      tone: "past",
      shortText: "رویداد گذشته است",
      fullText: "این رویداد گذشته است",
      totalDays: -diff.totalDays,
    };
  }

  if (diff.totalDays === 0) {
    return {
      tone: "today",
      shortText: "امروز",
      fullText: "این رویداد امروز است",
      totalDays: 0,
    };
  }

  const parts = [
    formatPart(diff.years, "سال"),
    formatPart(diff.months, "ماه"),
    formatPart(diff.weeks, "هفته"),
    formatPart(diff.days, "روز"),
  ].filter(Boolean);

  const compactParts = [
    formatPart(diff.years, "سال"),
    formatPart(diff.months, "ماه"),
    formatPart(diff.weeks * 7 + diff.days, "روز"),
  ].filter(Boolean);

  const fullText = `${parts.join(" و ")} تا رویداد مانده`;
  const shortText = `${compactParts.join(" و ")} مانده`;

  let tone = "long";
  if (diff.totalDays <= 7) tone = "critical";
  else if (diff.totalDays <= 30) tone = "soon";
  else if (diff.totalDays <= 90) tone = "warm";
  else if (diff.totalDays <= 180) tone = "cool";
  else if (diff.totalDays <= 365) tone = "future";

  return {
    tone,
    shortText,
    fullText,
    totalDays: diff.totalDays,
  };
}
  function renderEvents() {
    if (!els.eventsWrap) return;

    const wrap = els.eventsWrap;
    wrap.innerHTML = "";

    if (!state.filteredEvents.length) {
      showEmptyOrError();
      return;
    }

    const fragment = document.createDocumentFragment();

    state.filteredEvents.forEach((event) => {
      const article = document.createElement("article");
      const tone = getUrgencyTone(event.dateiso);
      const urgencyLabel = getUrgencyLabel(event.dateiso);
      const countdown = getCountdownData(event.dateiso);
      article.className = `event-card tone-${countdown.tone}`;
      article.tabIndex = 0;
      article.setAttribute("role", "button");
      article.setAttribute("aria-label", `Show details for ${event.title}`);

      article.innerHTML = `
        <div class="event-card-top">
          <div class="event-head">
            <h3 class="event-title">${escapeHtml(event.title)}</h3>
            <div class="event-badges">
  ${event.pinned ? '<span class="mini-badge">📌 سنجاق‌شده</span>' : ""}
  <span class="mini-badge mini-badge-soft">${escapeHtml(CATEGORY_LABELS[event.category] || "General")}</span>
  <span class="mini-badge mini-badge-urgency tone-${countdown.tone}">${escapeHtml(countdown.shortText)}</span>
</div>

<div class="event-dates">
  <span>${escapeHtml(event.dateiso)}</span>
  <span>•</span>
  <span>${escapeHtml(event.datejalali)}</span>
</div>

<div class="event-countdown tone-${countdown.tone}">
  ${escapeHtml(countdown.fullText)}
</div>

        <div class="event-bottom">
          <span class="status-dot status-${escapeHtml(event.notify_status)}"></span>
          <span class="event-status">${escapeHtml(STATUS_LABELS[event.notify_status] || "Unknown")}</span>
        </div>
      `;

      article.addEventListener("click", () => openDetail(event.id));
      article.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          openDetail(event.id);
        }
      });

      fragment.appendChild(article);
    });

    wrap.appendChild(fragment);
    showEmptyOrError();
  }

  function openSheet(name, focusTarget = null) {
    state.lastFocusedElement = document.activeElement;

    if (els.sheetOverlay) els.sheetOverlay.hidden = false;

    [els.composerSheet, els.detailSheet].forEach((sheet) => {
      if (!sheet) return;
      const active = sheet.id === name;
      sheet.hidden = !active;
      sheet.setAttribute("aria-hidden", String(!active));
    });

    state.activeSheet = name;

    if (els.openComposerBtn) {
      els.openComposerBtn.setAttribute("aria-expanded", String(name === "composerSheet"));
    }

    updateTelegramBackButton();

    window.setTimeout(() => {
      if (focusTarget) focusTarget.focus();
    }, 40);
  }

  function closeSheets() {
    [els.composerSheet, els.detailSheet].forEach((sheet) => {
      if (!sheet) return;
      sheet.hidden = true;
      sheet.setAttribute("aria-hidden", "true");
    });

    if (els.sheetOverlay) els.sheetOverlay.hidden = true;
    state.activeSheet = null;

    if (els.openComposerBtn) {
      els.openComposerBtn.setAttribute("aria-expanded", "false");
    }

    updateTelegramBackButton();

    if (state.lastFocusedElement && typeof state.lastFocusedElement.focus === "function") {
      state.lastFocusedElement.focus();
    }
  }

  function updateTelegramBackButton() {
    if (!tg?.BackButton) return;

    try {
      tg.BackButton.hide();
      tg.BackButton.offClick(handleTelegramBack);
      if (state.activeSheet) {
        tg.BackButton.onClick(handleTelegramBack);
        tg.BackButton.show();
      }
    } catch (_) {}
  }

  function handleTelegramBack() {
    if (state.activeSheet) closeSheets();
  }

  function resetComposerForm() {
    if (!els.eventForm) return;
    els.eventForm.reset();
    if (els.eventId) els.eventId.value = "";
    if (els.pin) els.pin.checked = false;
    if (els.dateJalali) els.dateJalali.value = "";
    state.editingEventId = null;
    if (els.composerTitle) els.composerTitle.textContent = "New event";
    if (els.composerSubtitle) els.composerSubtitle.textContent = "Set the title, date, and repeat pattern.";
    if (els.saveEventBtn) els.saveEventBtn.textContent = "Save event";
  }

  function openCreateComposer() {
    resetComposerForm();
    openSheet("composerSheet", els.title);
  }

  function openEditComposer(event) {
    state.editingEventId = event.id;
    if (els.eventId) els.eventId.value = event.id;
    if (els.title) els.title.value = event.title || "";
    if (els.date) els.date.value = event.date_iso || "";
    if (els.dateJalali) els.dateJalali.value = event.date_jalali || "";
    if (els.repeat) els.repeat.value = event.repeat || "none";
    if (els.category) els.category.value = event.category || "general";
    if (els.pin) els.pin.checked = !!event.pinned;
    if (els.note) els.note.value = event.note || "";
    if (els.composerTitle) els.composerTitle.textContent = "Edit event";
    if (els.composerSubtitle) els.composerSubtitle.textContent = "Update the event information.";
    if (els.saveEventBtn) els.saveEventBtn.textContent = "Save changes";
    openSheet("composerSheet", els.title);
  }

  function getEventById(eventId) {
    return state.events.find((item) => item.id === eventId) || null;
  }

  function openDetail(eventId) {
    const event = getEventById(eventId);
    if (!event) return;

    state.detailEventId = eventId;

    if (els.detailEventTitle) els.detailEventTitle.textContent = event.title || "—";
    if (els.detailCategoryBadge) els.detailCategoryBadge.textContent = CATEGORY_LABELS[event.category] || "General";
    if (els.detailRepeatBadge) els.detailRepeatBadge.textContent = REPEAT_LABELS[event.repeat] || "One time";
    if (els.detailDateIso) els.detailDateIso.textContent = event.date_iso || "—";
    if (els.detailDateJalali) els.detailDateJalali.textContent = event.date_jalali || "—";
    if (els.detailTimezone) els.detailTimezone.textContent = event.tz_name || "UTC";
    if (els.detailStatus) els.detailStatus.textContent = STATUS_LABELS[event.notify_status] || "—";
    if (els.detailNote) els.detailNote.value = event.note || "";
    if (els.detailPinBtn) els.detailPinBtn.textContent = event.pinned ? "Unpin" : "Pin";

    openSheet("detailSheet", els.detailNote);
  }

  async function submitEventForm(e) {
    e.preventDefault();

    const payload = {
      title: els.title?.value.trim() || "",
      date: els.date?.value || "",
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
      repeat: els.repeat?.value || "none",
      category: els.category?.value || "general",
      note: els.note?.value.trim() || "",
      pinned: !!els.pin?.checked,
    };

    if (!payload.title || !payload.date) {
      showToast("Title and date are required.", "error");
      return;
    }

    setLoading(true);

    try {
      if (state.editingEventId) {
        await apiPost("/api/edit", {
          event_id: state.editingEventId,
          ...payload,
        });
        showToast("Event updated.", "success");
      } else {
        await apiPost("/api/add", payload);
        showToast("Event saved successfully.", "success");
      }

      closeSheets();
      resetComposerForm();
      await loadEvents();
    } catch (error) {
      console.error("[DEBUG] submitEventForm failed:", error);
      showToast(normalizeErrorMessage(error), "error");
    } finally {
      setLoading(false);
    }
  }

  async function deleteCurrentEvent() {
    const event = getEventById(state.detailEventId);
    if (!event) return;

    const ok = window.confirm(`Delete event "${event.title}"?`);
    if (!ok) return;

    setLoading(true);
    try {
      await apiPost("/api/delete", { event_id: event.id });
      closeSheets();
      showToast("Event deleted.", "success");
      await loadEvents();
    } catch (error) {
      showToast(normalizeErrorMessage(error), "error");
    } finally {
      setLoading(false);
    }
  }

  async function saveCurrentNote() {
    const event = getEventById(state.detailEventId);
    if (!event) return;

    setLoading(true);
    try {
      const data = await apiPost("/api/note", {
        event_id: event.id,
        note: els.detailNote?.value.trim() || "",
      });

      const target = getEventById(event.id);
      if (target) target.note = data.note || "";

      showToast("Note saved.", "success");
      renderEvents();
    } catch (error) {
      showToast(normalizeErrorMessage(error), "error");
    } finally {
      setLoading(false);
    }
  }

  function resetCurrentNote() {
    const event = getEventById(state.detailEventId);
    if (!event || !els.detailNote) return;
    els.detailNote.value = event.note || "";
  }

  async function toggleCurrentPin() {
    const event = getEventById(state.detailEventId);
    if (!event) return;

    const nextPinned = !event.pinned;

    setLoading(true);
    try {
      const data = await apiPost("/api/pin", {
        event_id: event.id,
        pinned: nextPinned,
      });

      event.pinned = !!data.pinned;
      if (els.detailPinBtn) {
        els.detailPinBtn.textContent = event.pinned ? "Unpin" : "Pin";
      }
      renderEvents();
      updateCounters();
      showToast(event.pinned ? "Event pinned." : "Event unpinned.", "success");
    } catch (error) {
      showToast(normalizeErrorMessage(error), "error");
    } finally {
      setLoading(false);
    }
  }

  async function shareCurrentEvent() {
    const event = getEventById(state.detailEventId);
    if (!event) return;

    const text = [
      `📅 ${event.title}`,
      `Gregorian: ${event.date_iso}`,
      `Jalali: ${event.date_jalali}`,
      `Repeat: ${REPEAT_LABELS[event.repeat] || "One time"}`,
      event.note ? `Note: ${event.note}` : "",
    ]
      .filter(Boolean)
      .join("\n");

    try {
      if (navigator.share) {
        await navigator.share({
          title: event.title,
          text,
        });
        showToast("Shared successfully.", "success");
        return;
      }

      await copyToClipboard(text);
      showToast("Event text copied.", "success");
    } catch (_) {
      showToast("Sharing failed.", "error");
    }
  }

  async function copyToClipboard(text) {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }

    const temp = document.createElement("textarea");
    temp.value = text;
    temp.setAttribute("readonly", "");
    temp.style.position = "absolute";
    temp.style.left = "-9999px";
    document.body.appendChild(temp);
    temp.select();
    document.execCommand("copy");
    document.body.removeChild(temp);
  }

  function handleDetailEdit() {
    const event = getEventById(state.detailEventId);
    if (!event) return;
    openEditComposer(event);
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function jalaliToGregorian(jy, jm, jd) {
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
      (jm < 7 ? (jm - 1) * 31 : (jm - 7) * 30 + 186);

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
      0, 31, (gy % 4 === 0 && gy % 100 !== 0) || gy % 400 === 0 ? 29 : 28, 31, 30, 31,
      30, 31, 31, 30, 31, 30, 31,
    ];

    let gm = 0;
    for (gm = 1; gm <= 12; gm++) {
      const v = salA[gm];
      if (gd <= v) break;
      gd -= v;
    }

    return { gy, gm, gd };
  }

  function gregorianToJalali(gy, gm, gd) {
    const g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
    let jy;
    if (gy > 1600) {
      jy = 979;
      gy -= 1600;
    } else {
      jy = 0;
      gy -= 621;
    }

    const gy2 = gm > 2 ? gy + 1 : gy;
    let days =
      365 * gy +
      Math.floor((gy2 + 3) / 4) -
      Math.floor((gy2 + 99) / 100) +
      Math.floor((gy2 + 399) / 400) -
      80 +
      gd +
      g_d_m[gm - 1];

    jy += 33 * Math.floor(days / 12053);
    days %= 12053;

    jy += 4 * Math.floor(days / 1461);
    days %= 1461;

    if (days > 365) {
      jy += Math.floor((days - 1) / 365);
      days = (days - 1) % 365;
    }

    const jm = days < 186 ? 1 + Math.floor(days / 31) : 7 + Math.floor((days - 186) / 30);
    const jd = 1 + (days < 186 ? days % 31 : (days - 186) % 30);

    return { jy, jm, jd };
  }

  function format2(n) {
    return String(n).padStart(2, "0");
  }

  function syncJalaliFromGregorian() {
    if (!els.date?.value) {
      if (els.dateJalali) els.dateJalali.value = "";
      return;
    }

    const [gy, gm, gd] = els.date.value.split("-").map(Number);
    if (!gy || !gm || !gd) return;

    const j = gregorianToJalali(gy, gm, gd);
    if (els.dateJalali) {
      els.dateJalali.value = `${j.jy}/${format2(j.jm)}/${format2(j.jd)}`;
    }
  }

  function syncGregorianFromJalali() {
    const raw = els.dateJalali?.value.trim().replaceAll("-", "/") || "";
    if (!raw) return;

    const parts = raw.split("/");
    if (parts.length !== 3) return;

    const [jy, jm, jd] = parts.map((n) => Number(n));
    if (!jy || !jm || !jd) return;

    const g = jalaliToGregorian(jy, jm, jd);
    if (els.date) {
      els.date.value = `${g.gy}-${format2(g.gm)}-${format2(g.gd)}`;
    }
  }

  function bindEvents() {
    els.refreshBtn?.addEventListener("click", loadEvents);
    els.retryBtn?.addEventListener("click", loadEvents);
    els.emptyAddBtn?.addEventListener("click", openCreateComposer);
    els.openComposerBtn?.addEventListener("click", openCreateComposer);
    els.closeComposerX?.addEventListener("click", closeSheets);
    els.closeDetailX?.addEventListener("click", closeSheets);
    els.cancelBtn?.addEventListener("click", closeSheets);
    els.sheetOverlay?.addEventListener("click", closeSheets);

    els.eventForm?.addEventListener("submit", submitEventForm);

    els.date?.addEventListener("change", syncJalaliFromGregorian);
    els.dateJalali?.addEventListener("change", syncGregorianFromJalali);
    els.dateJalali?.addEventListener("blur", syncGregorianFromJalali);

    els.searchInput?.addEventListener("input", (e) => {
      state.searchTerm = e.target.value || "";
      applyFilters();
      renderEvents();
    });

    els.filterButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        state.currentFilter = btn.dataset.filter || "all";
        els.filterButtons.forEach((item) => item.classList.toggle("is-active", item === btn));
        applyFilters();
        renderEvents();
      });
    });

    els.detailEditBtn?.addEventListener("click", handleDetailEdit);
    els.detailDeleteBtn?.addEventListener("click", deleteCurrentEvent);
    els.detailPinBtn?.addEventListener("click", toggleCurrentPin);
    els.detailShareBtn?.addEventListener("click", shareCurrentEvent);
    els.detailNoteSaveBtn?.addEventListener("click", saveCurrentNote);
    els.detailNoteCancelBtn?.addEventListener("click", resetCurrentNote);

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && state.activeSheet) closeSheets();
    });
  }

  initTelegram();
  bindEvents();
  loadEvents();
})();
