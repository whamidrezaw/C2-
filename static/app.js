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
      body: JSON.stringify({ timezone: state.userTZ, ...payload }),
      signal: this._controllers[url].signal
    });

    if (res.status === 429) throw new Error("RATE_LIMIT");
    if (res.status === 403) throw new Error("AUTH_FAILED");
    if (!res.ok) throw new Error("API_ERROR");
    return res.json();
  }
};
