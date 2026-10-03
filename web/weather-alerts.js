// Separate from the dashboard refresh: weather warnings never delay inverter data.
(() => {
  const widget = document.querySelector('#weather-alerts');
  const list = document.querySelector('#weather-alerts-list');
  const status = document.querySelector('#weather-alerts-status');
  let payload = { alerts: [], status: 'loading' };
  const formatter = new Intl.DateTimeFormat('es-ES', {
    timeZone: 'Europe/Madrid', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  });
  function render() {
    const now = Date.now();
    const alerts = payload.alerts.filter(item => Date.parse(item.expires) > now);
    widget.hidden = alerts.length === 0;
    list.replaceChildren();
    if (!alerts.length) return;
    status.textContent = payload.status === 'ok'
      ? `Actualizado ${formatter.format(new Date(payload.updated_at))}`
      : 'Sin actualizar · últimos avisos recibidos';
    for (const alert of alerts) {
      const row = document.createElement('a');
      row.className = `weather-alert-item alert-${['yellow', 'orange', 'red'].includes(alert.level) ? alert.level : 'yellow'}`;
      row.href = 'https://www.aemet.es/es/eltiempo/prediccion/avisos';
      row.target = '_blank';
      row.rel = 'noopener noreferrer';
      const badge = document.createElement('strong');
      badge.className = 'weather-alert-level';
      badge.textContent = alert.level_label;
      const summary = document.createElement('span');
      summary.className = 'weather-alert-summary';
      summary.textContent = `${alert.event} · ${alert.area}`;
      const dates = document.createElement('small');
      const active = Date.parse(alert.onset) <= now;
      dates.textContent = `${active ? 'Activo' : 'Próximo'} · ${formatter.format(new Date(alert.onset))} — ${formatter.format(new Date(alert.expires))}`;
      row.append(badge, summary, dates);
      list.append(row);
    }
  }
  async function refresh() {
    try {
      const response = await fetch('/api/weather-alerts', {cache: 'no-store'});
      if (!response.ok) throw new Error(`weather-alerts ${response.status}`);
      payload = await response.json();
    } catch (_) {
      payload.status = 'unavailable';
    }
    render();
  }
  refresh();
  setInterval(refresh, 30000);
})();
