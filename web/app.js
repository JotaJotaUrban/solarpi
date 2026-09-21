const DEFAULT_ECONOMICS_START_DATE = "2026-08-21";

const state = {
  historyMinutes: 60,
  historyPoints: [],
  lastHistoryFetch: 0,
  latestSnapshot: null,
  weatherLocation: "borriol",
  weatherCurrent: null,
  weatherToday: null,
  weatherTomorrow: null,
  weatherProductionForecast: null,
  todayProductionPlan: null,
  weatherByLocation: {},
  totalRange: "day",
  totals: null,
  economicsStartDate: DEFAULT_ECONOMICS_START_DATE,
  economicsBalance: null,
  peakRange: "day",
  peaks: null,
};

const weatherLocations = {
  borriol: "Borriol",
  merida: "Mérida",
};

function finiteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

const els = {
  currentDateTime: document.querySelector("#current-datetime"),
  weatherPill: document.querySelector("#weather-pill"),
  weatherIcon: document.querySelector("#weather-icon"),
  weatherPlace: document.querySelector("#weather-place"),
  weatherSummary: document.querySelector("#weather-summary"),
  weatherTemp: document.querySelector("#weather-temp"),
  weatherMax: document.querySelector("#weather-max"),
  weatherMin: document.querySelector("#weather-min"),
  weatherHumidity: document.querySelector("#weather-humidity"),
  weatherWind: document.querySelector("#weather-wind"),
  todayProduction: document.querySelector("#today-production"),
  tomorrowPill: document.querySelector("#tomorrow-pill"),
  tomorrowIcon: document.querySelector("#tomorrow-icon"),
  tomorrowDate: document.querySelector("#tomorrow-date"),
  tomorrowTemp: document.querySelector("#tomorrow-temp"),
  tomorrowProduction: document.querySelector("#tomorrow-production"),
  inverterStatus: document.querySelector("#inverter-status"),
  lastRead: document.querySelector("#last-read"),
  solarPower: document.querySelector("#solar-power"),
  pvSplit: document.querySelector("#pv-split"),
  housePower: document.querySelector("#house-power"),
  batterySoc: document.querySelector("#battery-soc"),
  batteryFill: document.querySelector("#battery-fill"),
  batteryFlow: document.querySelector("#battery-flow"),
  gridPower: document.querySelector("#grid-power"),
  gridMode: document.querySelector("#grid-mode"),
  metricSolar: document.querySelector("#metric-solar"),
  metricHouse: document.querySelector("#metric-house"),
  metricBattery: document.querySelector("#metric-battery"),
  metricGrid: document.querySelector("#metric-grid"),
  solarDetail: document.querySelector("#solar-detail"),
  batteryDetail: document.querySelector("#battery-detail"),
  gridDetail: document.querySelector("#grid-detail"),
  gridReadout: document.querySelector("#grid-readout"),
  pvReadout: document.querySelector("#pv-readout"),
  system: {
    cpu: document.querySelector("#system-cpu"),
    ram: document.querySelector("#system-ram"),
    storage: document.querySelector("#system-storage"),
    temp: document.querySelector("#system-temp"),
  },
  totals: {
    production: document.querySelector("#total-production"),
    consumption: document.querySelector("#total-consumption"),
    gridImport: document.querySelector("#total-grid-import"),
    gridExport: document.querySelector("#total-grid-export"),
  },
  economics: {
    period: document.querySelector("#economics-period"),
    startDate: document.querySelector("#economics-start-date"),
    balanceCard: document.querySelector("#economics-balance-card"),
    balance: document.querySelector("#economics-balance"),
    balanceDetail: document.querySelector("#economics-balance-detail"),
    exportCredit: document.querySelector("#economics-export-credit"),
    exportDetail: document.querySelector("#economics-export-detail"),
    recoveryCost: document.querySelector("#economics-recovery-cost"),
    recoveryDetail: document.querySelector("#economics-recovery-detail"),
    recoverableEnergy: document.querySelector("#economics-recoverable-energy"),
    rateDetail: document.querySelector("#economics-rate-detail"),
  },
  peaks: {
    demand: document.querySelector("#peak-demand"),
    demandAt: document.querySelector("#peak-demand-at"),
    production: document.querySelector("#peak-production"),
    productionAt: document.querySelector("#peak-production-at"),
    gridImport: document.querySelector("#peak-grid-import"),
    gridImportAt: document.querySelector("#peak-grid-import-at"),
    gridExport: document.querySelector("#peak-grid-export"),
    gridExportAt: document.querySelector("#peak-grid-export-at"),
  },
  trends: {
    solar: document.querySelector("#trend-solar"),
    house: document.querySelector("#trend-house"),
    battery: document.querySelector("#trend-battery"),
    grid: document.querySelector("#trend-grid"),
  },
  lanes: {
    solar: document.querySelector("#solar-lane"),
    house: document.querySelector("#house-lane"),
    battery: document.querySelector("#battery-lane"),
    grid: document.querySelector("#grid-lane"),
  },
  charts: {
    history: document.querySelector("#history-chart"),
    grid: document.querySelector("#grid-chart"),
    pv: document.querySelector("#pv-chart"),
    sparkSolar: document.querySelector("#spark-solar"),
    sparkHouse: document.querySelector("#spark-house"),
    sparkBattery: document.querySelector("#spark-battery"),
    sparkGrid: document.querySelector("#spark-grid"),
  },
};

function formatPower(value) {
  const abs = Math.abs(Number(value) || 0);
  if (abs >= 1000) {
    return `${(abs / 1000).toFixed(2)} kW`;
  }
  return `${Math.round(abs)} W`;
}

function formatSignedPower(value) {
  const number = Number(value) || 0;
  if (number > 0) return formatPower(number);
  if (number < 0) return `-${formatPower(number)}`;
  return "0 W";
}

function formatWeatherNumber(value, suffix, decimals = 0) {
  const number = finiteNumber(value);
  if (number === null) return suffix === "%" ? "--%" : `-- ${suffix}`;
  if (suffix === "%") return `${number.toFixed(decimals)}%`;
  return `${number.toFixed(decimals)} ${suffix}`;
}

function formatPercent(value) {
  const number = finiteNumber(value);
  if (number === null) return "--%";
  return `${number.toFixed(0)}%`;
}

function formatSystemTemperature(value) {
  const number = finiteNumber(value);
  if (number === null) return "-- °C";
  return `${number.toFixed(1)} °C`;
}

function formatTemperatureRange(min, max) {
  const low = finiteNumber(min);
  const high = finiteNumber(max);
  const lowText = low !== null ? `${Math.round(low)}°` : "--°";
  const highText = high !== null ? `${Math.round(high)}°C` : "--°C";
  return `${lowText} / ${highText}`;
}

function formatTemperatureShort(value) {
  const number = finiteNumber(value);
  if (number === null) return "--°";
  return `${Math.round(number)}°`;
}

function formatShortDate(value) {
  if (!value) return "--";
  const parts = String(value).split("-").map((part) => Number(part));
  if (parts.length < 3 || parts.some((part) => !Number.isFinite(part))) return "--";
  const months = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"];
  const day = parts[2];
  const month = months[parts[1] - 1];
  if (!day || !month) return "--";
  return `${day} ${month}`;
}

function formatDateInputValue(date = new Date()) {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}

function formatEconomicsPeriod(value) {
  const parts = String(value || DEFAULT_ECONOMICS_START_DATE).split("-");
  if (parts.length !== 3) return `Desde ${DEFAULT_ECONOMICS_START_DATE} 00:00`;
  return `Desde ${parts[2]}/${parts[1]}/${parts[0]} 00:00`;
}

function formatHeaderDateTime(date = new Date()) {
  const isoDate = [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
  const time = [
    String(date.getHours()).padStart(2, "0"),
    String(date.getMinutes()).padStart(2, "0"),
  ].join(":");
  return `${formatShortDate(isoDate)} ${time}`;
}

function updateHeaderDateTime() {
  setText(els.currentDateTime, formatHeaderDateTime());
}

function formatEnergy(value) {
  const number = finiteNumber(value);
  if (number === null) return "-- kWh";
  return `${number.toFixed(number < 10 ? 2 : 1)} kWh`;
}

function formatEnergyAmount(value) {
  const number = finiteNumber(value);
  if (number === null) return "--";
  return number.toFixed(number < 10 ? 2 : 1);
}

function formatCurrency(value, signed = false) {
  const number = finiteNumber(value);
  if (number === null) return "-- €";
  const formatted = new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Math.abs(number));
  if (!signed || number === 0) return formatted;
  return `${number > 0 ? "+" : "-"}${formatted}`;
}

function formatRate(value) {
  const number = finiteNumber(value);
  if (number === null) return "-- €/kWh";
  return `${number.toLocaleString("es-ES", {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  })} €/kWh`;
}

function formatForecastEnergy(value) {
  const number = finiteNumber(value);
  if (number === null) return "-- kWh";
  return `${number.toFixed(number < 10 ? 2 : 1)} kWh`;
}

function formatPeakTime(value, range) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  const options = range === "day"
    ? { hour: "2-digit", minute: "2-digit" }
    : { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" };
  return `Registrado ${date.toLocaleString("es-ES", options)}`;
}

function formatPeakPower(value) {
  if (value === null || value === undefined) return "-- W";
  return formatPower(value);
}

function batteryModeLabel(mode) {
  return {
    charging: "Cargando",
    discharging: "Descargando",
    standby: "En espera",
  }[mode] || "Sin estado";
}

function interpolateColor(from, to, ratio) {
  const amount = Math.max(0, Math.min(1, ratio));
  const color = from.map((channel, index) => {
    return Math.round(channel + (to[index] - channel) * amount);
  });
  return `rgb(${color[0]}, ${color[1]}, ${color[2]})`;
}

function batteryColor(percent) {
  const value = Math.max(0, Math.min(100, Number(percent) || 0));
  if (value <= 50) {
    return interpolateColor([255, 59, 48], [255, 210, 31], value / 50);
  }
  return interpolateColor([255, 210, 31], [40, 224, 124], (value - 50) / 50);
}

function setText(el, text) {
  if (!el || el.textContent === text) return;
  el.textContent = text;
}

function setStatus(online) {
  document.body.dataset.connection = online ? "ok" : "offline";
  if (els.inverterStatus) {
    const lastRead = els.lastRead ? els.lastRead.textContent : "--:--:--";
    els.inverterStatus.setAttribute(
      "aria-label",
      online ? `Último dato del inversor ${lastRead}` : "Sin datos recientes del inversor",
    );
  }
}

function weatherName(location) {
  return weatherLocations[location] || "Borriol";
}

function clearWeather() {
  const name = weatherName(state.weatherLocation);
  state.weatherCurrent = null;
  state.weatherToday = null;
  state.weatherTomorrow = null;
  state.weatherProductionForecast = null;
  if (state.weatherLocation === "borriol") {
    state.todayProductionPlan = null;
  }
  els.weatherIcon.className = "weather-icon weather-unavailable";
  els.weatherPill.setAttribute("aria-label", `Tiempo en ${name}`);
  setText(els.weatherPlace, name);
  setText(els.weatherSummary, "--");
  setText(els.weatherTemp, "-- °C");
  setText(els.weatherMax, "--°");
  setText(els.weatherMin, "--°");
  setText(els.weatherHumidity, "--%");
  setText(els.weatherWind, "-- km/h");
  clearTomorrowForecast();
  updateTodayProduction();
}

function clearTomorrowForecast() {
  els.tomorrowIcon.className = "weather-icon weather-unavailable";
  els.tomorrowPill.setAttribute("aria-label", "Previsión para mañana no disponible");
  setText(els.tomorrowDate, "--");
  setText(els.tomorrowTemp, "-- / -- °C");
  setText(els.tomorrowProduction, "-- kWh");
}

function updateTomorrowForecast(forecast, productionForecast = null) {
  if (!forecast) {
    clearTomorrowForecast();
    return;
  }

  const condition = forecast.condition || "unavailable";
  const date = formatShortDate(forecast.date);
  const range = formatTemperatureRange(
    forecast.temperature_min_c,
    forecast.temperature_max_c,
  );
  const estimatedKwh = productionForecast
    ? productionForecast.estimated_kwh
    : forecast.production_estimate_kwh;
  const energy = formatForecastEnergy(estimatedKwh);

  els.tomorrowIcon.className = `weather-icon weather-${condition}`;
  els.tomorrowPill.setAttribute("aria-label", `Previsión ${date}: ${range}. Producción prevista ${energy}`);
  setText(els.tomorrowDate, date);
  setText(els.tomorrowTemp, range);
  setText(els.tomorrowProduction, energy);
}

function updateWeather(payload) {
  const location = payload.location || {};
  const locationId = location.id || state.weatherLocation;
  const condition = payload.condition || "unavailable";
  const name = location.name || weatherName(locationId);
  state.weatherCurrent = payload;
  state.weatherToday = payload.today || null;
  state.weatherTomorrow = payload.tomorrow || null;
  state.weatherProductionForecast = payload.production_forecast || null;
  if (payload.today_production) {
    state.todayProductionPlan = payload.today_production;
  }
  state.weatherByLocation[locationId] = {
    current: payload,
    today: state.weatherToday,
    tomorrow: state.weatherTomorrow,
    productionForecast: state.weatherProductionForecast,
  };

  els.weatherIcon.className = `weather-icon weather-${condition}`;
  els.weatherPill.setAttribute("aria-label", `Tiempo en ${name}. Pulsa para cambiar`);
  setText(els.weatherPlace, name);
  setText(els.weatherSummary, payload.weather_label || "--");
  setText(els.weatherTemp, formatWeatherNumber(payload.temperature_c, "°C", 1));
  setText(els.weatherMax, formatTemperatureShort(state.weatherToday?.temperature_max_c));
  setText(els.weatherMin, formatTemperatureShort(state.weatherToday?.temperature_min_c));
  setText(els.weatherHumidity, formatWeatherNumber(payload.humidity_percent, "%"));
  setText(els.weatherWind, formatWeatherNumber(payload.wind_speed_kmh, "km/h"));
  updateTomorrowForecast(state.weatherTomorrow, state.weatherProductionForecast);
  updateTodayProduction();
}

function clearTotals() {
  state.totals = null;
  [
    els.totals.production,
    els.totals.consumption,
    els.totals.gridImport,
    els.totals.gridExport,
  ].forEach((el) => setText(el, "-- kWh"));
  updateTotalTabs();
  updateTodayProduction();
}

function updateTotalTabs() {
  document.querySelectorAll("[data-total-range]").forEach((button) => {
    button.classList.toggle("active", button.dataset.totalRange === state.totalRange);
  });
}

function renderTotals() {
  const range = state.totalRange;
  const data = state.totals ? state.totals[range] || {} : {};

  setText(els.totals.production, formatEnergy(data.production_kwh));
  setText(els.totals.consumption, formatEnergy(data.consumption_kwh));
  setText(els.totals.gridImport, formatEnergy(data.grid_import_kwh));
  setText(els.totals.gridExport, formatEnergy(data.grid_export_kwh));
  updateTotalTabs();
}

function updateTotals(payload) {
  state.totals = payload;
  renderTotals();
  updateTodayProduction();
}

function updateTodayProduction() {
  const dayTotals = state.totals ? state.totals.day || {} : {};
  const planned = state.todayProductionPlan || {};
  const actual = finiteNumber(dayTotals.production_kwh) !== null
    ? dayTotals.production_kwh
    : planned.actual_kwh;
  const expected = planned.expected_kwh;
  setText(
    els.todayProduction,
    `${formatEnergyAmount(actual)} / ${formatEnergyAmount(expected)} kWh`,
  );
}

function clearEconomicsBalance() {
  state.economicsBalance = null;
  renderEconomicsBalance();
}

function updateEconomicsBalance(payload) {
  state.economicsBalance = payload;
  if (payload && payload.start_date) {
    state.economicsStartDate = payload.start_date;
    if (els.economics.startDate) {
      els.economics.startDate.value = payload.start_date;
    }
  }
  renderEconomicsBalance();
}

function renderEconomicsBalance() {
  const balanceData = state.economicsBalance || {};
  const rates = balanceData.rates || {};
  const importedKwh = finiteNumber(balanceData.imported_kwh);
  const exportedKwh = finiteNumber(balanceData.exported_kwh);
  const recoveredKwh = finiteNumber(balanceData.recovered_kwh);
  const exportCredit = finiteNumber(balanceData.export_credit_eur);
  const recoveryCost = finiteNumber(balanceData.recovery_cost_eur);
  const balance = finiteNumber(balanceData.balance_eur);
  const recoverableKwh = finiteNumber(balanceData.recoverable_kwh);
  const exportRate = finiteNumber(rates.export_price_eur_kwh);
  const recoveryRate = finiteNumber(rates.recovery_price_eur_kwh);
  const periodDate = balanceData.start_date || state.economicsStartDate;
  const periodLabel = balanceData.period_label || formatEconomicsPeriod(periodDate);

  if (
    importedKwh === null
    || exportedKwh === null
    || recoveredKwh === null
    || exportCredit === null
    || recoveryCost === null
    || balance === null
    || recoverableKwh === null
  ) {
    els.economics.balanceCard.classList.remove("is-positive", "is-negative", "is-even");
    els.economics.balanceCard.classList.add("is-even");
    setText(els.economics.period, periodLabel);
    setText(els.economics.balance, "-- €");
    setText(els.economics.balanceDetail, "--");
    setText(els.economics.exportCredit, "-- €");
    setText(els.economics.exportDetail, `-- kWh · ${formatRate(exportRate)}`);
    setText(els.economics.recoveryCost, "-- €");
    setText(els.economics.recoveryDetail, `-- kWh · ${formatRate(recoveryRate)}`);
    setText(els.economics.recoverableEnergy, "-- kWh");
    setText(els.economics.rateDetail, `${formatRate(exportRate)} / ${formatRate(recoveryRate)}`);
    return;
  }

  const balanceState = {
    positive: "is-positive",
    negative: "is-negative",
    even: "is-even",
  }[balanceData.balance_state] || "is-even";

  els.economics.balanceCard.classList.remove("is-positive", "is-negative", "is-even");
  els.economics.balanceCard.classList.add(balanceState);

  setText(els.economics.period, periodLabel);
  setText(els.economics.balance, formatCurrency(balance, true));
  setText(els.economics.balanceDetail, balanceData.balance_label || "--");
  setText(els.economics.exportCredit, formatCurrency(exportCredit));
  setText(els.economics.exportDetail, `${formatEnergy(exportedKwh)} · ${formatRate(exportRate)}`);
  setText(els.economics.recoveryCost, formatCurrency(recoveryCost));
  setText(els.economics.recoveryDetail, `${formatEnergy(recoveredKwh)} · ${formatRate(recoveryRate)}`);
  setText(els.economics.recoverableEnergy, formatEnergy(recoverableKwh));
  setText(els.economics.rateDetail, `${formatRate(exportRate)} / ${formatRate(recoveryRate)}`);
}

function clearPeaks() {
  state.peaks = null;
  setText(els.peaks.demand, "-- W");
  setText(els.peaks.demandAt, "--");
  setText(els.peaks.production, "-- W");
  setText(els.peaks.productionAt, "--");
}

function updatePeakTabs() {
  document.querySelectorAll("[data-peak-range]").forEach((button) => {
    button.classList.toggle("active", button.dataset.peakRange === state.peakRange);
  });
}

function renderPeaks() {
  const range = state.peakRange;
  const data = state.peaks ? state.peaks[range] || {} : {};
  const demand = data.demand_peak || {};
  const production = data.production_peak || {};
  const gridImport = data.grid_import_peak || {};
  const gridExport = data.grid_export_peak || {};

  setText(els.peaks.demand, formatPeakPower(demand.value_w));
  setText(els.peaks.demandAt, formatPeakTime(demand.timestamp, range));
  setText(els.peaks.production, formatPeakPower(production.value_w));
  setText(els.peaks.productionAt, formatPeakTime(production.timestamp, range));
  setText(els.peaks.gridImport, formatPeakPower(gridImport.value_w));
  setText(els.peaks.gridImportAt, formatPeakTime(gridImport.timestamp, range));
  setText(els.peaks.gridExport, formatPeakPower(gridExport.value_w));
  setText(els.peaks.gridExportAt, formatPeakTime(gridExport.timestamp, range));
  updatePeakTabs();
}

function updatePeaks(payload) {
  state.peaks = payload;
  renderPeaks();
}

function clearSystemMetrics() {
  setText(els.system.cpu, "--%");
  setText(els.system.ram, "--%");
  setText(els.system.storage, "--%");
  setText(els.system.temp, "-- °C");
  Object.values(els.system).forEach((el) => setMetricState(el, null));
}

function updateSystemMetrics(payload) {
  const cpu = payload.cpu || {};
  const memory = payload.memory || {};
  const storage = payload.storage || {};
  const temperature = payload.temperature || {};

  setText(els.system.cpu, formatPercent(cpu.percent));
  setText(els.system.ram, formatPercent(memory.percent));
  setText(els.system.storage, formatPercent(storage.percent));
  setText(els.system.temp, formatSystemTemperature(temperature.celsius));
  setMetricState(els.system.cpu, cpu.percent, 75, 90);
  setMetricState(els.system.ram, memory.percent, 75, 90);
  setMetricState(els.system.storage, storage.percent, 80, 90);
  setMetricState(els.system.temp, temperature.celsius, 70, 80);
}

function setMetricState(el, value, warning = 75, alert = 90) {
  if (!el) return;
  el.classList.remove("metric-ok", "metric-warn", "metric-alert");
  const number = finiteNumber(value);
  if (number === null) return;
  if (number >= alert) {
    el.classList.add("metric-alert");
  } else if (number >= warning) {
    el.classList.add("metric-warn");
  } else {
    el.classList.add("metric-ok");
  }
}

const TREND_RECENT_SECONDS = 30;
const TREND_REFERENCE_SECONDS = 120;
const TREND_PERCENT_THRESHOLD = 0.05;
const TREND_MIN_REFERENCE_W = 100;
const FLOW_TREND_IDLE_W = 80;
const FLOW_IDLE_W = 20;
const HISTORY_MAX_LINE_GAP_MS = 5 * 60 * 1000;

function pointTime(point) {
  const time = Date.parse(point.ts || point.timestamp || "");
  return Number.isFinite(time) ? time : null;
}

function trendPoints(nowMs) {
  return historyWithLatest()
    .map((point) => ({ ...point, timeMs: pointTime(point) }))
    .filter((point) => point.timeMs !== null && point.timeMs <= nowMs)
    .sort((a, b) => a.timeMs - b.timeMs);
}

function averageWindow(points, field, nowMs, minAgeSeconds, maxAgeSeconds) {
  const values = points
    .filter((point) => {
      const ageSeconds = (nowMs - point.timeMs) / 1000;
      return ageSeconds >= minAgeSeconds && ageSeconds < maxAgeSeconds;
    })
    .map((point) => Number(point[field]))
    .filter((value) => Number.isFinite(value));

  if (values.length < 2) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function percentTrend(points, field, nowMs) {
  const recent = averageWindow(points, field, nowMs, 0, TREND_RECENT_SECONDS);
  const baseline = averageWindow(
    points,
    field,
    nowMs,
    0,
    TREND_REFERENCE_SECONDS,
  );

  if (recent === null || baseline === null) return "neutral";
  if (Math.max(Math.abs(recent), Math.abs(baseline)) < TREND_MIN_REFERENCE_W) return "neutral";
  const delta = recent - baseline;
  const reference = Math.max(Math.abs(baseline), TREND_MIN_REFERENCE_W);
  const change = delta / reference;
  if (change > TREND_PERCENT_THRESHOLD) return "up";
  if (change < -TREND_PERCENT_THRESHOLD) return "down";
  return "neutral";
}

function batteryTrend(snapshot) {
  const watts = Math.abs(Number(snapshot.battery_power_w) || 0);
  if (watts < FLOW_TREND_IDLE_W) return "neutral";
  if (snapshot.battery_mode === "charging") return "up";
  if (snapshot.battery_mode === "discharging") return "down";
  return "neutral";
}

function gridTrend(points, nowMs) {
  const recent = averageWindow(points, "grid_power_w", nowMs, 0, TREND_RECENT_SECONDS);
  if (recent === null || Math.abs(recent) < FLOW_TREND_IDLE_W) return "neutral";
  return recent < 0 ? "up" : "down";
}

function updateTrends(snapshot) {
  const nowMs = pointTime(snapshot) || Date.now();
  const points = trendPoints(nowMs);

  setTrend(els.trends.solar, percentTrend(points, "solar_power_w", nowMs));
  setTrend(els.trends.house, percentTrend(points, "house_power_w", nowMs));
  setTrend(els.trends.battery, batteryTrend(snapshot));
  setTrend(els.trends.grid, gridTrend(points, nowMs));
}

function setTrend(el, nextClass) {
  if (!el) return;
  el.classList.remove("up", "down", "neutral");
  el.classList.add(nextClass);
  el.setAttribute("aria-label", nextClass);
}

function flowSpeed(watts) {
  const value = Math.min(4200, Math.max(80, Math.abs(Number(watts) || 0)));
  return `${Math.max(0.65, 2.6 - value / 2100).toFixed(2)}s`;
}

function updateFlow(snapshot) {
  document.body.dataset.solar = snapshot.solar_power_w > FLOW_IDLE_W
    ? "active"
    : "idle";

  document.body.dataset.grid = snapshot.grid_power_w > FLOW_IDLE_W
    ? "import"
    : snapshot.grid_power_w < -FLOW_IDLE_W
      ? "export"
      : "idle";

  document.body.dataset.battery = snapshot.battery_mode === "charging"
    ? "charge"
    : snapshot.battery_mode === "discharging"
      ? "discharge"
      : "idle";

  els.lanes.solar.style.setProperty("--flow-speed", flowSpeed(snapshot.solar_power_w));
  els.lanes.house.style.setProperty("--flow-speed", flowSpeed(snapshot.house_power_w));
  els.lanes.battery.style.setProperty("--flow-speed", flowSpeed(snapshot.battery_power_w));
  els.lanes.grid.style.setProperty("--flow-speed", flowSpeed(snapshot.grid_power_w));
}

function updateSnapshot(snapshot) {
  state.latestSnapshot = snapshot;
  const batteryMode = batteryModeLabel(snapshot.battery_mode);

  setText(els.solarPower, formatPower(snapshot.solar_power_w));
  setText(els.pvSplit, `PV1 ${formatPower(snapshot.pv1_power_w)} + PV2 ${formatPower(snapshot.pv2_power_w)}`);
  setText(els.housePower, formatPower(snapshot.house_power_w));

  setText(els.batterySoc, `${snapshot.battery_soc_percent}%`);
  els.batteryFill.style.height = `${Math.max(0, Math.min(100, snapshot.battery_soc_percent))}%`;
  els.batteryFill.style.setProperty("--battery-fill-color", batteryColor(snapshot.battery_soc_percent));
  setText(els.batteryFlow, `${batteryMode} ${formatPower(snapshot.battery_power_w)}`);

  if (snapshot.grid_power_w > 0) {
    setText(els.gridPower, formatPower(snapshot.grid_power_w));
    setText(els.gridMode, "Importando");
  } else if (snapshot.grid_power_w < 0) {
    setText(els.gridPower, formatPower(snapshot.grid_power_w));
    setText(els.gridMode, "Exportando");
  } else {
    setText(els.gridPower, "0 W");
    setText(els.gridMode, "Sin intercambio");
  }

  setText(els.metricSolar, formatPower(snapshot.solar_power_w));
  setText(els.metricHouse, formatPower(snapshot.house_power_w));
  setText(els.metricBattery, formatSignedPower(snapshot.battery_power_w));
  setText(els.metricGrid, formatSignedPower(snapshot.grid_power_w));
  setText(els.solarDetail, `${formatPower(snapshot.pv1_power_w)} / ${formatPower(snapshot.pv2_power_w)}`);
  setText(els.batteryDetail, `${batteryMode} ${Number(snapshot.battery_voltage_v).toFixed(1)} V`);
  setText(els.gridDetail, snapshot.grid_power_w > 0 ? "Importación" : snapshot.grid_power_w < 0 ? "Exportación" : "Neutro");
  setText(els.gridReadout, formatPower(snapshot.grid_power_w));
  setText(els.pvReadout, `${formatPower(snapshot.pv1_power_w)} / ${formatPower(snapshot.pv2_power_w)}`);
  setText(els.lastRead, new Date(snapshot.timestamp).toLocaleTimeString());

  updateTrends(snapshot);

  updateFlow(snapshot);
  drawRealtimeCharts();
}

function clearSnapshot() {
  state.latestSnapshot = null;
  document.body.dataset.solar = "idle";
  document.body.dataset.grid = "idle";
  document.body.dataset.battery = "idle";

  [
    els.solarPower,
    els.pvSplit,
    els.housePower,
    els.batterySoc,
    els.batteryFlow,
    els.gridPower,
    els.gridMode,
    els.metricSolar,
    els.metricHouse,
    els.metricBattery,
    els.metricGrid,
    els.solarDetail,
    els.batteryDetail,
    els.gridDetail,
    els.gridReadout,
    els.pvReadout,
    els.lastRead,
  ].forEach((el) => setText(el, "--"));

  els.batteryFill.style.height = "0%";
  Object.values(els.trends).forEach((trend) => setTrend(trend, "neutral"));
  drawAllCharts();
}

async function fetchNow() {
  const response = await fetch("/api/now", { cache: "no-store" });
  if (!response.ok) throw new Error(`now ${response.status}`);
  return response.json();
}

async function fetchHealth() {
  const response = await fetch("/api/health", { cache: "no-store" });
  if (!response.ok) throw new Error(`health ${response.status}`);
  return response.json();
}

async function fetchHistory() {
  const response = await fetch(`/api/history?minutes=${state.historyMinutes}&limit=900`, {
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`history ${response.status}`);
  const payload = await response.json();
  state.historyPoints = payload.points || [];
  state.lastHistoryFetch = Date.now();
  drawAllCharts();
}

async function fetchWeather(location = state.weatherLocation) {
  const response = await fetch(`/api/weather?location=${encodeURIComponent(location)}`, {
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`weather ${response.status}`);
  const payload = await response.json();
  if (location === state.weatherLocation) {
    updateWeather(payload);
  }
}

async function fetchTotals() {
  const response = await fetch("/api/totals", { cache: "no-store" });
  if (!response.ok) throw new Error(`totals ${response.status}`);
  updateTotals(await response.json());
}

async function fetchEconomicsBalance(startDate = state.economicsStartDate) {
  const response = await fetch(`/api/economics-balance?start_date=${encodeURIComponent(startDate)}`, {
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`economics ${response.status}`);
  updateEconomicsBalance(await response.json());
}

async function fetchPeaks() {
  const response = await fetch("/api/peaks", { cache: "no-store" });
  if (!response.ok) throw new Error(`peaks ${response.status}`);
  updatePeaks(await response.json());
}

async function fetchSystemMetrics() {
  const response = await fetch("/api/system", { cache: "no-store" });
  if (!response.ok) throw new Error(`system ${response.status}`);
  updateSystemMetrics(await response.json());
}

async function refresh() {
  try {
    const results = await Promise.all([fetchHealth(), fetchNow()]);
    const health = results[0];
    const snapshot = results[1];
    updateSnapshot(snapshot);
    setStatus(health.status === "ok");

    if (Date.now() - state.lastHistoryFetch > 45000) {
      fetchHistory().catch(drawAllCharts);
    }
  } catch (error) {
    clearSnapshot();
    setStatus(false);
  }
}

function setupCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(rect.width * dpr));
  canvas.height = Math.max(1, Math.floor(rect.height * dpr));
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, rect.width, rect.height);
  return { ctx, width: rect.width, height: rect.height };
}

function historyWithLatest() {
  const points = state.historyPoints.slice();
  if (state.latestSnapshot) {
    points.push({
      ts: state.latestSnapshot.timestamp,
      solar_power_w: state.latestSnapshot.solar_power_w,
      house_power_w: state.latestSnapshot.house_power_w,
      grid_power_w: state.latestSnapshot.grid_power_w,
      battery_power_w: state.latestSnapshot.battery_power_w,
      battery_soc_percent: state.latestSnapshot.battery_soc_percent,
    });
  }
  return points;
}

function drawGrid(ctx, x, y, width, height) {
  ctx.strokeStyle = "rgba(255,255,255,0.08)";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i += 1) {
    const gy = y + (height / 4) * i;
    ctx.beginPath();
    ctx.moveTo(x, gy);
    ctx.lineTo(x + width, gy);
    ctx.stroke();
  }
}

function drawLineChart() {
  const canvas = els.charts.history;
  const view = setupCanvas(canvas);
  const ctx = view.ctx;
  const padding = { top: 16, right: 18, bottom: 30, left: 50 };
  const width = view.width - padding.left - padding.right;
  const height = view.height - padding.top - padding.bottom;
  const rangeEndMs = Date.now();
  const rangeStartMs = rangeEndMs - state.historyMinutes * 60 * 1000;
  const points = historyWithLatest()
    .map((point) => ({ ...point, timeMs: pointTime(point) }))
    .filter((point) => (
      point.timeMs !== null
      && point.timeMs >= rangeStartMs
      && point.timeMs <= rangeEndMs
    ))
    .sort((a, b) => a.timeMs - b.timeMs);

  drawGrid(ctx, padding.left, padding.top, width, height);

  if (points.length < 2) {
    ctx.fillStyle = "#8f9ba8";
    ctx.font = "14px system-ui, sans-serif";
    ctx.fillText("Esperando histórico", padding.left, padding.top + 30);
    return;
  }

  const values = points.flatMap((point) => [
    point.solar_power_w,
    point.house_power_w,
    point.grid_power_w,
    point.battery_power_w,
  ]);
  const min = Math.min(0, ...values);
  const max = Math.max(100, ...values);
  const span = max - min || 1;

  function x(point) {
    const progress = (point.timeMs - rangeStartMs) / (rangeEndMs - rangeStartMs || 1);
    return padding.left + width * Math.min(1, Math.max(0, progress));
  }

  function y(value) {
    return padding.top + height - ((value - min) / span) * height;
  }

  if (min < 0 && max > 0) {
    ctx.strokeStyle = "rgba(255,255,255,0.28)";
    ctx.setLineDash([5, 5]);
    ctx.beginPath();
    ctx.moveTo(padding.left, y(0));
    ctx.lineTo(padding.left + width, y(0));
    ctx.stroke();
    ctx.setLineDash([]);
  }

  function line(field, color, widthPx) {
    ctx.strokeStyle = color;
    ctx.lineWidth = widthPx;
    ctx.shadowColor = color;
    ctx.shadowBlur = 10;
    ctx.beginPath();
    points.forEach((point, index) => {
      const px = x(point);
      const py = y(point[field] || 0);
      const previous = points[index - 1];
      if (index === 0 || point.timeMs - previous.timeMs > HISTORY_MAX_LINE_GAP_MS) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.stroke();
    ctx.shadowBlur = 0;
  }

  line("solar_power_w", "#ffd21f", 2.5);
  line("house_power_w", "#ff3b30", 2);
  line("grid_power_w", "#00d4ff", 2);
  line("battery_power_w", "#28e07c", 2);

  ctx.fillStyle = "#8f9ba8";
  ctx.font = "12px system-ui, sans-serif";
  ctx.fillText(formatSignedPower(max), 6, padding.top + 5);
  ctx.fillText(formatSignedPower(min), 6, padding.top + height);
}

function drawSparkline(canvas, field, color) {
  const view = setupCanvas(canvas);
  const ctx = view.ctx;
  const points = historyWithLatest().slice(-80);
  const values = points.map((point) => Number(point[field]) || 0);
  if (values.length < 2) return;

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;

  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.shadowColor = color;
  ctx.shadowBlur = 8;
  ctx.beginPath();
  values.forEach((value, index) => {
    const x = (view.width * index) / (values.length - 1);
    const y = view.height - ((value - min) / span) * (view.height - 4) - 2;
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  ctx.shadowBlur = 0;
}

function drawGridBalance() {
  const canvas = els.charts.grid;
  const view = setupCanvas(canvas);
  const ctx = view.ctx;
  const points = historyWithLatest().slice(-64);
  const values = points.map((point) => Number(point.grid_power_w) || 0);
  const maxAbs = Math.max(100, ...values.map((value) => Math.abs(value)));
  const centerY = view.height / 2;
  const barGap = 2;
  const barWidth = Math.max(2, (view.width - barGap * values.length) / Math.max(1, values.length));

  ctx.strokeStyle = "rgba(255,255,255,0.24)";
  ctx.beginPath();
  ctx.moveTo(0, centerY);
  ctx.lineTo(view.width, centerY);
  ctx.stroke();

  values.forEach((value, index) => {
    const x = index * (barWidth + barGap);
    const h = (Math.abs(value) / maxAbs) * (view.height * 0.42);
    ctx.fillStyle = value > 0 ? "#ff3b30" : value < 0 ? "#28e07c" : "#8f9ba8";
    if (value >= 0) ctx.fillRect(x, centerY - h, barWidth, h);
    else ctx.fillRect(x, centerY, barWidth, h);
  });

  ctx.fillStyle = "#8f9ba8";
  ctx.font = "12px system-ui, sans-serif";
  ctx.fillText("Importar", 6, 18);
  ctx.fillText("Exportar", 6, view.height - 10);
}

function drawPvSplit() {
  const canvas = els.charts.pv;
  const view = setupCanvas(canvas);
  const ctx = view.ctx;
  const snapshot = state.latestSnapshot;
  const pv1 = snapshot ? snapshot.pv1_power_w : 0;
  const pv2 = snapshot ? snapshot.pv2_power_w : 0;
  const max = Math.max(100, pv1, pv2);
  const rows = [
    { label: "PV1", value: pv1, y: view.height * 0.34, color: "#ffd21f" },
    { label: "PV2", value: pv2, y: view.height * 0.64, color: "#ff9f0a" },
  ];

  rows.forEach((row) => {
    const barX = 52;
    const barW = view.width - 68;
    const width = (row.value / max) * barW;
    ctx.fillStyle = "rgba(255,255,255,0.09)";
    ctx.fillRect(barX, row.y - 10, barW, 20);
    ctx.fillStyle = row.color;
    ctx.shadowColor = row.color;
    ctx.shadowBlur = 12;
    ctx.fillRect(barX, row.y - 10, width, 20);
    ctx.shadowBlur = 0;
    ctx.fillStyle = "#8f9ba8";
    ctx.font = "800 12px system-ui, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(row.label, 8, row.y + 4);
    ctx.fillStyle = "#f3f6f8";
    ctx.textAlign = "right";
    ctx.fillText(formatPower(row.value), view.width - 8, row.y + 4);
  });
  ctx.textAlign = "left";
}

function drawRealtimeCharts() {
  drawGridBalance();
  drawPvSplit();
  drawSparkline(els.charts.sparkSolar, "solar_power_w", "#ffd21f");
  drawSparkline(els.charts.sparkHouse, "house_power_w", "#ff3b30");
  drawSparkline(els.charts.sparkBattery, "battery_power_w", "#28e07c");
  drawSparkline(els.charts.sparkGrid, "grid_power_w", "#00d4ff");
}

function drawAllCharts() {
  drawLineChart();
  drawRealtimeCharts();
}

document.querySelectorAll("[data-minutes]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-minutes]").forEach((item) => {
      item.classList.toggle("active", item === button);
    });
    state.historyMinutes = Number(button.dataset.minutes);
    fetchHistory().catch(drawAllCharts);
  });
});

document.querySelectorAll("[data-total-range]").forEach((button) => {
  button.addEventListener("click", () => {
    state.totalRange = button.dataset.totalRange;
    renderTotals();
  });
});

document.querySelectorAll("[data-peak-range]").forEach((button) => {
  button.addEventListener("click", () => {
    state.peakRange = button.dataset.peakRange;
    renderPeaks();
  });
});

els.weatherPill.addEventListener("click", () => {
  state.weatherLocation = state.weatherLocation === "borriol" ? "merida" : "borriol";
  clearWeather();
  fetchWeather().catch(clearWeather);
});

function setupEconomicsStartPicker() {
  if (!els.economics.startDate) return;
  els.economics.startDate.value = state.economicsStartDate;
  els.economics.startDate.max = formatDateInputValue();
  els.economics.startDate.addEventListener("change", () => {
    state.economicsStartDate = els.economics.startDate.value || DEFAULT_ECONOMICS_START_DATE;
    clearEconomicsBalance();
    fetchEconomicsBalance().catch(clearEconomicsBalance);
  });
}

window.addEventListener("resize", drawAllCharts);

setupEconomicsStartPicker();
clearWeather();
clearTotals();
clearEconomicsBalance();
clearPeaks();
clearSystemMetrics();
updateHeaderDateTime();
refresh();
fetchHistory().catch(drawAllCharts);
fetchWeather().catch(clearWeather);
fetchTotals().catch(clearTotals);
fetchPeaks().catch(clearPeaks);
fetchEconomicsBalance().catch(clearEconomicsBalance);
fetchSystemMetrics().catch(clearSystemMetrics);
setInterval(updateHeaderDateTime, 1000);
setInterval(refresh, 4000);
setInterval(() => fetchWeather().catch(clearWeather), 600000);
setInterval(() => fetchTotals().catch(clearTotals), 60000);
setInterval(() => fetchPeaks().catch(clearPeaks), 60000);
setInterval(() => fetchSystemMetrics().catch(clearSystemMetrics), 30000);
