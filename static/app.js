const tg = window.Telegram?.WebApp;

if (tg) {
  tg.ready();
  tg.expand();
}

function getInitData() {
  return tg?.initData || "";
}

async function apiPost(url, payload = {}) {
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": getInitData()
    },
    body: JSON.stringify(payload)
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }

  return res.json();
}

async function loadEvents() {
  try {
    const data = await apiPost("/api/list", {});
    console.log("events", data);
  } catch (err) {
    console.error("loadEvents failed:", err);
    alert("خطا در دریافت رویدادها");
  }
}

async function addEvent(payload) {
  try {
    const data = await apiPost("/api/add", payload);
    console.log("added", data);
    return data;
  } catch (err) {
    console.error("addEvent failed:", err);
    alert("خطا در ثبت رویداد");
    throw err;
  }
}

window.tmApi = {
  loadEvents,
  addEvent
};
