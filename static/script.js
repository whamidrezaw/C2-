const tg = window.Telegram.WebApp;
tg.expand();

function applyTheme() {
    if (!tg.themeParams) return;
    const p = tg.themeParams;
    const root = document.documentElement.style;
    if(p.secondary_bg_color) root.setProperty("--bg-color", p.secondary_bg_color);
    if(p.bg_color) root.setProperty("--card-bg", p.bg_color);
    if(p.text_color) root.setProperty("--text-primary", p.text_color);
    if(p.hint_color) root.setProperty("--text-secondary", p.hint_color);
    if(p.button_color) root.setProperty("--accent-color", p.button_color);
}
applyTheme();
tg.onEvent('themeChanged', applyTheme);

function updateClock() {
    const now = new Date();
    document.getElementById('clock').innerText = now.toLocaleTimeString('en-GB', {hour12: false, hour:'2-digit', minute:'2-digit'});
    document.getElementById('date-display').innerText = now.toLocaleDateString('en-GB', {weekday:'long', year:'numeric', month:'long', day:'numeric'});
}
setInterval(updateClock, 1000);
updateClock();

function render(userData) {
    const div = document.getElementById('content');
    if (!userData || Object.keys(userData).length === 0) {
        div.innerHTML = `<div class="empty-state">List is empty.</div>`;
        return;
    }

    const events = Object.entries(userData).map(([key, item]) => {
        const parts = item.date.split('.');
        const target = new Date(`${parts[2]}-${parts[1]}-${parts[0]}`);
        const today = new Date(); today.setHours(0,0,0,0);
        const diff = Math.ceil((target - today) / 86400000);
        return { ...item, diff };
    }).sort((a, b) => a.diff - b.diff);

    let html = '';
    events.forEach(item => {
        let badge = 'bg-gray', txt = Math.abs(item.diff) + ' Days';
        if (item.diff < 0) txt = "Passed";
        else if (item.diff === 0) { badge = 'bg-red'; txt = "Today"; }
        else if (item.diff <= 180) badge = 'bg-red';
        else if (item.diff <= 365) badge = 'bg-yellow';
        else badge = 'bg-green';

        const shamsi = item.shamsi_date ? 
            `<div class="date-row"><span class="date-label">IR</span><span class="date-val">${item.shamsi_date}</span></div>` : '';

        html += `
        <div class="card">
            <div style="font-size: 24px;">📌</div>
            <div class="card-info">
                <div class="card-title">${item.title}</div>
                <div class="card-date-group">
                    <div class="date-row"><span class="date-label">EN</span><span class="date-val">${item.date}</span></div>
                    ${shamsi}
                </div>
            </div>
            <div class="card-badge ${badge}">${txt}</div>
        </div>`;
    });
    div.innerHTML = html;
}

// Initial Render called from HTML