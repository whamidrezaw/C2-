const TimeManager = (() => {
  const tg = window.Telegram.WebApp;
  const state = { events: [], loading: false };

  const API = {
    controller: null,
    async request(url, payload) {
      if (this.controller) this.controller.abort();
      this.controller = new AbortController();
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ initData: tg.initData, ...payload }),
        signal: this.controller.signal
      });
      if (!res.ok) throw new Error("API_ERROR");
      return res.json();
    }
  };

  const UI = {
    render() {
      const root = document.getElementById("list");
      if (state.loading && state.events.length === 0) {
        root.innerHTML = '<div class="loader">Syncing...</div>';
        return;
      }
      if (state.events.length === 0) {
        root.innerHTML = '<div class="empty">📅 No events yet.<br>Add one below!</div>';
        return;
      }
      root.innerHTML = state.events.map(e => `
        <div class="card ${e.optimistic ? 'syncing' : ''}">
          <div class="card-title">${e.title}</div>
          <div class="card-date">${e.date_iso}</div>
        </div>
      `).join("");
    }
  };

  return {
    init() {
      tg.expand();
      const cache = localStorage.getItem("events_v1");
      if (cache) { state.events = JSON.parse(cache); UI.render(); }
      this.sync();
    },
    async sync() {
      state.loading = true;
      try {
        const res = await API.request("/api/list", {});
        if (res.success) {
          state.events = res.targets;
          localStorage.setItem("events_v1", JSON.stringify(state.events));
        }
      } catch (e) { console.error("Sync failed"); }
      state.loading = false;
      UI.render();
    },
    async add(title, date) {
      if (!title || !date) return;
      const tempId = "tmp_" + Date.now();
      const tempEvent = { id: tempId, title, date_iso: date, optimistic: true };
      
      state.events.unshift(tempEvent);
      UI.render();
      tg.HapticFeedback.impactOccurred('medium');

      try {
        const res = await API.request("/api/add", { title, date });
        if (res.success) {
          this.sync();
          document.getElementById("title").value = "";
          document.getElementById("date").value = "";
        }
      } catch (e) {
        state.events = state.events.filter(ev => ev.id !== tempId);
        UI.render();
        tg.HapticFeedback.notificationOccurred('error');
        alert("Failed to save event. Check your connection.");
      }
    }
  };
})();

window.onload = () => TimeManager.init();
