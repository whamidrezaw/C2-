

  function fatal(message) {
    console.error("[TM_FATAL]", message);
    document.body.innerHTML = `
      <div style="padding: 20px; text-align: center; color: red;">
        <h2>⚠️ خطا</h2>
        <p>${message}</p>
      </div>
    `;
  }

  console.log("[DEBUG] window.Telegram:", !!window.Telegram);
  console.log("[DEBUG] tg object:", !!tg);

  if (!tg) {
    fatal("این اپلیکیشن فقط از داخل تلگرام کار می‌کند. لطفا از Telegram Mini App وارد شوید.");
    return;
  }

  try {
    tg.ready();
    tg.expand();
  } catch (_) {}

  const initData = (tg.initData || "").trim();
  console.log("[DEBUG] initData length:", initData.length);

  if (!initData) {
    fatal("Telegram Mini App نتوانست احراز هویت کند. Mini App را دوباره باز کنید.");
    return;
  }



  const els = {

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
    general: "عمومی",
    birthday: "تولد",
    work: "کار",
    family: "خانواده",
    health: "سلامت",
    travel: "سفر",
    finance: "مالی",
    study: "مطالعه",
    other: "سایر",
  };

  const REPEAT_LABELS = {
    none: "یک‌بار",
    daily: "روزانه",
    weekly: "هفتگی",
    monthly: "ماهانه",
    yearly: "سالانه",
  };

  const STATUS_LABELS = {
    pending: "در انتظار",
    processing: "در حال پردازش",
    done: "ارسال شده",
    failed: "ناموفق",
  };

  function initTelegram() {
    if (!tg) return;

    try {
      tg.ready();
      tg.expand();
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
    els.syncStatus.textContent = text;
  }

  function setLoading(loading) {
    document.body.classList.toggle("is-loading", loading);
    setSyncStatus(loading ? "در حال همگام‌سازی" : "آماده");
  }

  function showToast(message, type = "info") {
    const toast = els.toast;
    toast.textContent = message;
    toast.dataset.type = type;
    toast.classList.add("is-visible");

    window.clearTimeout(showToast._t);
    showToast._t = window.setTimeout(() => {
      toast.classList.remove("is-visible");
    }, 2400);
  }

  function getInitData() {
    return state.initData || tg?.initData || "";
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

    if (!response.ok) {
      const detail = data?.detail || "REQUEST_FAILED";
      throw new Error(detail);
    }

    return data;
  }

  function normalizeErrorMessage(error) {
    const detail = error?.message || "";
    const map = {
      NO_DATA: "اطلاعات احراز هویت تلگرام وجود ندارد.",
      BAD_HASH: "اعتبار درخواست تلگرام نامعتبر است.",
      EXPIRED: "نشست Mini App منقضی شده است. صفحه را دوباره باز کن.",
      INVALID_DATE: "تاریخ واردشده معتبر نیست.",
      TITLE_TOO_LONG: "عنوان بیش از حد طولانی است.",
      NOTE_TOO_LONG: "یادداشت بیش از حد طولانی است.",
      EVENT_LIMIT_REACHED: "به سقف تعداد رویدادها رسیده‌ای.",
      RATE_LIMIT: "تعداد درخواست‌ها زیاد است. چند لحظه بعد دوباره تلاش کن.",
      NOT_FOUND_OR_UNAUTHORIZED: "این رویداد پیدا نشد یا دسترسی آن را نداری.",
      REQUEST_FAILED: "درخواست انجام نشد.",
    };
    return map[detail] || "خطایی رخ داد. دوباره تلاش کن.";
  }

  async function loadEvents() {
    setLoading(true);
    els.listErrorState.hidden = true;

    try {
      const data = await apiPost("/api/list", { skip: 0 });
      state.events = Array.isArray(data.targets) ? data.targets : [];
      state.detailEventId = state.events.some((item) => item.id === state.detailEventId)
        ? state.detailEventId
        : null;

      applyFilters();
      renderEvents();
      updateCounters();
      showEmptyOrError();
    } catch (error) {
      state.events = [];
      state.filteredEvents = [];
      renderEvents();
      els.listState.hidden = true;
      els.listErrorState.hidden = false;
      showToast(normalizeErrorMessage(error), "error");
      setSyncStatus("خطا");
    } finally {
      setLoading(false);
    }
  }

  function updateCounters() {
    els.eventCount.textContent = String(state.events.length);
  }

  function showEmptyOrError() {
    const hasEvents = state.events.length > 0;
    const hasFiltered = state.filteredEvents.length > 0;

    // ابتدا همه state ها را ریست می‌کنیم
    els.listErrorState.hidden = true;
    els.listState.hidden = true;

    if (!hasEvents) {
      // هیچ رویدادی وجود ندارد
      els.listState.hidden = false;
      els.listState.querySelector(".empty-state-title").textContent = "هنوز رویدادی ثبت نشده";
      els.listState.querySelector(".empty-state-text").textContent =
        "اولین رویداد را اضافه کن تا یادآوری‌هایت را مستقیم در تلگرام دریافت کنی.";
      els.emptyAddBtn.hidden = false;
    } else if (hasEvents && !hasFiltered) {
      // رویداد هست ولی فیلتر/جستجو نتیجه نداد
      els.listState.hidden = false;
      els.listState.querySelector(".empty-state-title").textContent = "نتیجه‌ای پیدا نشد";
      els.listState.querySelector(".empty-state-text").textContent = "فیلتر یا جستجو را تغییر بده.";
      els.emptyAddBtn.hidden = true;
    }
    // در غیر این صورت (hasEvents && hasFiltered) لیست نمایش داده می‌شه — listState پنهان می‌مونه
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

  function renderEvents() {
    const wrap = els.eventsWrap;
    wrap.innerHTML = "";

    if (!state.filteredEvents.length) {
      showEmptyOrError();
      return;
    }

    const fragment = document.createDocumentFragment();

    state.filteredEvents.forEach((event) => {
      const article = document.createElement("article");
      article.className = "event-card";
      article.tabIndex = 0;
      article.setAttribute("role", "button");
      article.setAttribute("aria-label", `نمایش جزئیات ${event.title}`);

      article.innerHTML = `
        <div class="event-card-top">
          <div class="event-head">
            <h3 class="event-title">${escapeHtml(event.title)}</h3>
            <div class="event-badges">
              ${event.pinned ? `<span class="mini-badge">📌</span>` : ""}
              <span class="mini-badge mini-badge-soft">${escapeHtml(CATEGORY_LABELS[event.category] || "عمومی")}</span>
            </div>
          </div>
          <span class="event-repeat">${escapeHtml(REPEAT_LABELS[event.repeat] || "یک‌بار")}</span>
        </div>

        <div class="event-dates">
          <span>${escapeHtml(event.date_iso)}</span>
          <span>•</span>
          <span>${escapeHtml(event.date_jalali)}</span>
        </div>

        <div class="event-bottom">
          <span class="status-dot status-${escapeHtml(event.notify_status)}"></span>
          <span class="event-status">${escapeHtml(STATUS_LABELS[event.notify_status] || "نامشخص")}</span>
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

    els.sheetOverlay.hidden = false;

    [els.composerSheet, els.detailSheet].forEach((sheet) => {
      const active = sheet.id === name;
      sheet.hidden = !active;
      sheet.setAttribute("aria-hidden", String(!active));
    });

    state.activeSheet = name;
    els.openComposerBtn.setAttribute("aria-expanded", String(name === "composerSheet"));

    updateTelegramBackButton();

    window.setTimeout(() => {
      if (focusTarget) focusTarget.focus();
    }, 40);
  }

  function closeSheets() {
    [els.composerSheet, els.detailSheet].forEach((sheet) => {
      sheet.hidden = true;
      sheet.setAttribute("aria-hidden", "true");
    });

    els.sheetOverlay.hidden = true;
    state.activeSheet = null;
    els.openComposerBtn.setAttribute("aria-expanded", "false");
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
    if (state.activeSheet) {
      closeSheets();
    }
  }

  function resetComposerForm() {
    els.eventForm.reset();
    els.eventId.value = "";
    els.pin.checked = false;
    els.dateJalali.value = "";
    state.editingEventId = null;
    els.composerTitle.textContent = "رویداد جدید";
    els.composerSubtitle.textContent = "عنوان، تاریخ و نوع تکرار را مشخص کن.";
    els.saveEventBtn.textContent = "ذخیره رویداد";
  }

  function openCreateComposer() {
    resetComposerForm();
    openSheet("composerSheet", els.title);
  }

  function openEditComposer(event) {
    state.editingEventId = event.id;

    els.eventId.value = event.id;
    els.title.value = event.title || "";
    els.date.value = event.date_iso || "";
    els.dateJalali.value = event.date_jalali || "";
    els.repeat.value = event.repeat || "none";
    els.category.value = event.category || "general";
    els.pin.checked = !!event.pinned;
    els.note.value = event.note || "";

    els.composerTitle.textContent = "ویرایش رویداد";
    els.composerSubtitle.textContent = "اطلاعات رویداد را به‌روزرسانی کن.";
    els.saveEventBtn.textContent = "ذخیره تغییرات";

    openSheet("composerSheet", els.title);
  }

  function getEventById(eventId) {
    return state.events.find((item) => item.id === eventId) || null;
  }

  function openDetail(eventId) {
    const event = getEventById(eventId);
    if (!event) return;

    state.detailEventId = eventId;

    els.detailEventTitle.textContent = event.title || "—";
    els.detailCategoryBadge.textContent = CATEGORY_LABELS[event.category] || "عمومی";
    els.detailRepeatBadge.textContent = REPEAT_LABELS[event.repeat] || "یک‌بار";
    els.detailDateIso.textContent = event.date_iso || "—";
    els.detailDateJalali.textContent = event.date_jalali || "—";
    els.detailTimezone.textContent = event.tz_name || "UTC";
    els.detailStatus.textContent = STATUS_LABELS[event.notify_status] || "—";
    els.detailNote.value = event.note || "";
    els.detailPinBtn.textContent = event.pinned ? "برداشتن سنجاق" : "سنجاق";

    openSheet("detailSheet", els.detailNote);
  }

  async function submitEventForm(e) {
    e.preventDefault();

    const payload = {
      title: els.title.value.trim(),
      date: els.date.value,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
      repeat: els.repeat.value,
      category: els.category.value,
      note: els.note.value.trim(),
      pinned: els.pin.checked,
    };

    if (!payload.title || !payload.date) {
      showToast("عنوان و تاریخ الزامی هستند.", "error");
      return;
    }

    setLoading(true);

    try {
      if (state.editingEventId) {
        await apiPost("/api/edit", {
          event_id: state.editingEventId,
          ...payload,
        });
        showToast("رویداد به‌روزرسانی شد.", "success");
      } else {
        await apiPost("/api/add", payload);
        showToast("رویداد با موفقیت ثبت شد.", "success");
      }

      closeSheets();
      resetComposerForm();
      await loadEvents();
    } catch (error) {
      showToast(normalizeErrorMessage(error), "error");
    } finally {
      setLoading(false);
    }
  }

  async function deleteCurrentEvent() {
    const event = getEventById(state.detailEventId);
    if (!event) return;

    const ok = window.confirm(`رویداد «${event.title}» حذف شود؟`);
    if (!ok) return;

    setLoading(true);
    try {
      await apiPost("/api/delete", { event_id: event.id });
      closeSheets();
      showToast("رویداد حذف شد.", "success");
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
        note: els.detailNote.value.trim(),
      });

      const target = getEventById(event.id);
      if (target) target.note = data.note || "";

      showToast("یادداشت ذخیره شد.", "success");
      renderEvents();
    } catch (error) {
      showToast(normalizeErrorMessage(error), "error");
    } finally {
      setLoading(false);
    }
  }

  function resetCurrentNote() {
    const event = getEventById(state.detailEventId);
    if (!event) return;
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
      els.detailPinBtn.textContent = event.pinned ? "برداشتن سنجاق" : "سنجاق";
      renderEvents();
      updateCounters();
      showToast(event.pinned ? "رویداد سنجاق شد." : "سنجاق برداشته شد.", "success");
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
      `Repeat: ${REPEAT_LABELS[event.repeat] || "One-time"}`,
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
        showToast("اشتراک‌گذاری انجام شد.", "success");
        return;
      }

      await copyToClipboard(text);
      showToast("متن رویداد کپی شد.", "success");
    } catch (_) {
      showToast("اشتراک‌گذاری انجام نشد.", "error");
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
      0,
      31,
      (gy % 4 === 0 && gy % 100 !== 0) || gy % 400 === 0 ? 29 : 28,
      31,
      30,
      31,
      30,
      31,
      31,
      30,
      31,
      30,
      31,
    ];

    let gm = 0;
    for (gm = 1; gm <= 12; gm++) {
      const v = salA[gm];
      if (gd <= v) break;
      gd -= v;
    }

    return {
      gy,
      gm,
      gd,
    };
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
    const jd = 1 + (days < 186 ? (days % 31) : ((days - 186) % 30));

    return { jy, jm, jd };
  }

  function format2(n) {
    return String(n).padStart(2, "0");
  }

  function syncJalaliFromGregorian() {
    if (!els.date.value) {
      els.dateJalali.value = "";
      return;
    }

    const [gy, gm, gd] = els.date.value.split("-").map(Number);
    if (!gy || !gm || !gd) return;

    const j = gregorianToJalali(gy, gm, gd);
    els.dateJalali.value = `${j.jy}/${format2(j.jm)}/${format2(j.jd)}`;
  }

  function syncGregorianFromJalali() {
    const raw = els.dateJalali.value.trim().replaceAll("-", "/");
    if (!raw) return;

    const parts = raw.split("/");
    if (parts.length !== 3) return;

    const [jy, jm, jd] = parts.map((n) => Number(n));
    if (!jy || !jm || !jd) return;

    const g = jalaliToGregorian(jy, jm, jd);
    els.date.value = `${g.gy}-${format2(g.gm)}-${format2(g.gd)}`;
  }

  function bindEvents() {
    els.refreshBtn.addEventListener("click", loadEvents);
    els.retryBtn.addEventListener("click", loadEvents);
    els.emptyAddBtn.addEventListener("click", openCreateComposer);
    els.openComposerBtn.addEventListener("click", openCreateComposer);
    els.closeComposerX.addEventListener("click", closeSheets);
    els.closeDetailX.addEventListener("click", closeSheets);
    els.cancelBtn.addEventListener("click", closeSheets);
    els.sheetOverlay.addEventListener("click", closeSheets);

    els.eventForm.addEventListener("submit", submitEventForm);

    els.date.addEventListener("change", syncJalaliFromGregorian);
    els.dateJalali.addEventListener("change", syncGregorianFromJalali);
    els.dateJalali.addEventListener("blur", syncGregorianFromJalali);

    els.searchInput.addEventListener("input", (e) => {
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

    els.detailEditBtn.addEventListener("click", handleDetailEdit);
    els.detailDeleteBtn.addEventListener("click", deleteCurrentEvent);
    els.detailPinBtn.addEventListener("click", toggleCurrentPin);
    els.detailShareBtn.addEventListener("click", shareCurrentEvent);
    els.detailNoteSaveBtn.addEventListener("click", saveCurrentNote);
    els.detailNoteCancelBtn.addEventListener("click", resetCurrentNote);

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && state.activeSheet) closeSheets();
    });
  }

  initTelegram();
  bindEvents();
  loadEvents();
})();
