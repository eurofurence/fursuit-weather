/* Eurofurence Weather
   Author: laffiesphere. */

const REFRESH_MS = 5 * 60 * 1000;
const DWD_WMS = 'https://maps.dwd.de/geoserver/dwd/wms';

const $ = (id) => document.getElementById(id);
const T = (key, vars) => EFW_I18N.T(key, vars);

const fmt = (value, digits = 0, unit = '') =>
  value === null || value === undefined ? '–' : `${Number(value).toFixed(digits)}${unit}`;

function text(el, value) {
  if (!el) {
    console.warn('EF Weather: missing element for text update', value);
    return;
  }
  el.textContent = value;
}

let latest = null; 
const PAST_CONTEXT_HOURS = 6;
const STALE_AFTER_MS = 15 * 60 * 1000;

/* ---------------------------------------------------------------- warnings */

function renderWarnings(warnings) {
  const host = $('warnings');
  host.innerHTML = '';
  if (!warnings.length) return;
  const worst = warnings[0];
  const advance = warnings.filter((w) => w.advance).length;

  const details = document.createElement('details');
  details.className = 'warnings-summary';
  details.style.setProperty('--level', worst.color);

  const summary = document.createElement('summary');
  summary.append(document.createTextNode('⚠️ '));

  const headline = document.createElement('span');
  headline.textContent = worst.event_en || worst.event;
  summary.append(headline);

  if (worst.start || worst.end) {
    const when = document.createElement('span');
    when.className = 'count';
    when.textContent = formatRange(worst.start, worst.end);
    summary.append(when);
  }

  if (advance) {
    const tag = document.createElement('span');
    tag.className = 'advance-tag';
    tag.textContent = T('warnings.advance');
    summary.append(tag);
  }

  if (warnings.length > 1) {
    const more = document.createElement('span');
    more.className = 'count';
    more.textContent = T('warnings.more', { n: warnings.length - 1 });
    summary.append(more);
  }

  details.append(summary);

  const detail = document.createElement('div');
  detail.className = 'detail';
  for (const warning of warnings) detail.append(warningCard(warning));
  details.append(detail);

  host.append(details);
}

function warningCard(warning) {
  const article = document.createElement('article');
  article.className = `warning${warning.advance ? ' is-advance' : ''}`;
  article.style.setProperty('--level', warning.advance ? '#e53935' : warning.color);

  const title = document.createElement('h3');
  title.textContent = warning.event_en || warning.event;
  article.append(title);

  const when = document.createElement('p');
  when.className = 'when';
  when.textContent = [formatRange(warning.start, warning.end), warning.region]
    .filter(Boolean)
    .join(' · ');
  article.append(when);

  if (warning.advance) {
    const note = document.createElement('p');
    note.className = 'advance-note';
    note.textContent = T('warnings.advanceNote');
    article.append(note);
  }

  for (const [value, className] of [
    [warning.headline, 'official'],
    [warning.description, ''],
    [warning.instruction, 'instruction'],
  ]) {
    if (!value) continue;
    const paragraph = document.createElement('p');
    if (className) paragraph.className = className;
    paragraph.lang = 'de';
    paragraph.textContent = value;
    article.append(paragraph);
  }
  return article;
}

function formatRange(start, end) {
  const options = { weekday: 'short' };
  const from = start ? EFW_I18N.dateTime(start, options) : '';
  const to = end ? EFW_I18N.dateTime(end, options) : '';
  if (from && to) return `${from} – ${to}`;
  return from || to || '';
}

/* -------------------------------------------------------------------- FSI */

function renderFSI(data) {
  const fsi = data.fsi;
  const card = $('fsi-card');
  if (!fsi) {
    text($('fsi-label'), T('band.bad'));
    return;
  }

  /* The tint and the ink chosen to read against it are one decision, so they go
     on together. Set the other way round, anything that went wrong between the
     two lines left the panel wearing its colour with no ink to match -- which
     falls back to the page's near-white text on a pale card. Ink first, and the
     worst case is an untinted panel that is still perfectly readable. */
  const ink = EFW.contrastText(fsi.color);
  card.style.setProperty('--ink', ink);
  card.style.setProperty('--fsi', fsi.color);

  text($('fsi-score')?.querySelector('.value'), fsi.score.toFixed(1));
  text($('fsi-label'), fsi.label);
  text($('fsi-advice'), fsi.advice);

  /* The headline is scored from the station report -- the same reading "Right
     now" shows -- while the bars underneath are MOSMIX. The two disagree now
     and then, and calling a measurement a "forecast hour" made that read as a
     contradiction rather than as two different things. Say which this one is.
     The station report does go missing, and then this number does come from the
     forecast, so the wording follows the source rather than assuming. */
  const observed = data.current ? data.current.time_local : null;
  const measured = data.current && data.current.source === 'poi';
  const when = T(measured ? 'fsi.measured' : 'fsi.hour');
  text($('fsi-time'), observed ? `· ${when} ${EFW_I18N.time(observed)}` : '');

  const list = $('subscores');
  list.innerHTML = '';
  for (const entry of Object.values(fsi.subscores)) {
    const item = document.createElement('li');
    item.title = entry.reason;

    const name = document.createElement('span');
    name.className = 'name';
    name.textContent = entry.label;

    const bar = document.createElement('span');
    bar.className = 'bar';
    const fill = document.createElement('span');
    fill.className = 'fill';
    fill.style.width = `${entry.score * 10}%`;
    bar.append(fill);

    const num = document.createElement('span');
    num.className = 'num';
    num.textContent = entry.score.toFixed(1);

    item.append(name, bar, num);
    list.append(item);
  }

  const caps = $('fsi-caps');
  caps.hidden = !fsi.caps_applied.length;
  text(caps, fsi.caps_applied.join(' · '));

  renderWeights(fsi.subscores);
}

/* ------------------------------------------- how much each part of it counts */

/* Geometry of the ring, in the units of its own 100x100 viewBox. The gap is
   the card showing through between segments: a drawn divider would have to
   pick a colour, and the card's colour changes with the score. */
const PIE = { size: 100, radius: 34, width: 19, gap: 1.6 };
const SVG_NS = 'http://www.w3.org/2000/svg';


function renderWeights(subscores) {
  const figure = $('weights');
  const host = $('weights-pie');
  const legend = $('weights-legend');
  if (!figure || !host || !legend) return; // cached markup from before this existed

  const parts = Object.keys(subscores)
    .map(function (key) {
      return { label: subscores[key].label, weight: subscores[key].weight || 0 };
    })
    .filter(function (part) {
      return part.weight > 0;
    })
    .sort(function (a, b) {
      return b.weight - a.weight;
    });

  const total = parts.reduce(function (sum, part) {
    return sum + part.weight;
  }, 0);

  figure.hidden = parts.length < 2 || total <= 0;
  if (figure.hidden) return;

  const half = PIE.size / 2;
  const circumference = 2 * Math.PI * PIE.radius;

  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${PIE.size} ${PIE.size}`);
  svg.setAttribute('role', 'img');

  const ring = document.createElementNS(SVG_NS, 'g');
  ring.setAttribute('transform', `rotate(-90 ${half} ${half})`);
  svg.append(ring);

  let start = 0; // distance along the ring the next segment begins at
  const spoken = [];
  legend.innerHTML = '';

  for (let index = 0; index < parts.length; index += 1) {
    const share = parts[index].weight / total;
    const arc = share * circumference;
    const drawn = Math.max(arc - PIE.gap, 0.5);
    const step = `s${Math.min(index + 1, 4)}`;

    const segment = document.createElementNS(SVG_NS, 'circle');
    segment.setAttribute('class', `seg ${step}`);
    segment.setAttribute('cx', half);
    segment.setAttribute('cy', half);
    segment.setAttribute('r', PIE.radius);
    segment.setAttribute('stroke-width', PIE.width);
    segment.setAttribute('stroke-dasharray', `${drawn} ${circumference - drawn}`);
    segment.setAttribute('stroke-dashoffset', -(start + PIE.gap / 2));
    ring.append(segment);
    start += arc;

    const percent = `${Math.round(share * 100)} %`;
    spoken.push(`${parts[index].label} ${percent}`);

    const row = document.createElement('li');
    const swatch = document.createElement('span');
    swatch.className = `swatch ${step}`;
    const name = document.createElement('span');
    name.className = 'name';
    name.textContent = parts[index].label;
    const value = document.createElement('span');
    value.className = 'pct';
    value.textContent = percent;
    row.append(swatch, name, value);
    legend.append(row);
  }

  svg.setAttribute('aria-label', T('fsi.weightsAlt', { parts: spoken.join(', ') }));
  host.innerHTML = '';
  host.append(svg);
}

/* Purely cosmetic: one particular score earns a video. */
function renderEasterEgg(egg) {
  const panel = $('egg');
  if (!panel) return;
  const show = egg === 'ravi67';
  panel.hidden = !show;

  const video = $('egg-video');
  if (!video) return;
  if (show && video.paused) video.play().catch(() => {});
  if (!show) video.pause();
}

function renderLegend(host) {
  if (!host) return;
  host.innerHTML = '';
  for (const { color, label } of EFW.bands()) {
    const chip = document.createElement('span');
    chip.className = 'chip';
    chip.style.setProperty('--c', color);
    host.append(chip, document.createTextNode(` ${label} `));
  }
}

/* ------------------------------------------------------- current + daily */

/* Every explanation panel needs an id of its own for aria-controls, and the
   grids are rebuilt on every refresh, so the counter runs for the session. */
let noteSeq = 0;

function statGrid(host, items) {
  host.innerHTML = '';

  const note = document.createElement('p');
  note.className = 'stat-note';
  note.id = `stat-note-${(noteSeq += 1)}`;
  note.hidden = true;
  let open = null; // the button whose explanation is showing, if any

  for (const [key, value, infoKey] of items) {
    const item = document.createElement('div');
    item.className = 'item';
    const k = document.createElement('div');
    k.className = 'k';
    k.textContent = key;
    if (infoKey) k.append(document.createTextNode(' '), infoButton(key, infoKey));
    const v = document.createElement('div');
    v.className = 'v';
    v.textContent = value;
    item.append(k, v);
    host.append(item);
  }

  host.append(note);

  function infoButton(term, infoKey) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'info';
    button.textContent = 'i';
    button.setAttribute('aria-label', T('info.about', { term: term }));
    button.setAttribute('aria-expanded', 'false');
    button.setAttribute('aria-controls', note.id);
    button.addEventListener('click', function () {
      const show = open !== button; // the same (i) again closes it
      if (open) open.setAttribute('aria-expanded', 'false');
      open = show ? button : null;
      button.setAttribute('aria-expanded', show ? 'true' : 'false');
      note.textContent = show ? T(infoKey) : '';
      note.hidden = !show;
    });
    return button;
  }
}

function renderNow(current, fsi) {
  const host = $('now');
  host.innerHTML = '';
  if (!current) return;

  const items = [
    [T('now.conditions'), `${current.weather.icon || ''} ${current.weather.text || '–'}`.trim()],
    [T('now.temperature'), EFW_I18N.temp(current.temperature)],
    [T('now.wetbulb'), EFW_I18N.temp(fsi?.wetbulb), 'info.wetbulb'],
    [T('now.dewpoint'), EFW_I18N.temp(fsi?.dewpoint), 'info.dewpoint'],
    [T('now.humidity'), fmt(current.humidity, 0, ' %')],
    [
      T('now.wind'),
      `${fmt(current.wind_speed_kmh, 0, ' km/h')}${current.wind_direction_name ? ` ${current.wind_direction_name}` : ''}`,
    ],
    [T('now.gusts'), fmt(current.wind_gust_kmh, 0, ' km/h')],
    [T('now.rain1h'), fmt(current.precipitation, 1, ' mm')],
    [T('now.pressure'), fmt(current.pressure, 0, ' hPa')],
  ];

  statGrid(host, items);
}

/* ---- conditions behind single bar */


let picked = null; // ISO time of the selected hour
let pickedChart = null; // which chart it was picked in
let charts = []; // {key, strip, detail, series}, rebuilt on every render
let conditionsByTime = new Map(); // ISO time -> the enriched entry from fsi_series

const hourEntry = (entry) => ({ ...entry, ...(conditionsByTime.get(entry.time) || {}) });

function ensureDetail(id, strip) {
  const existing = $(id);
  if (existing) return existing;

  console.warn('EFW: markup has no #%s, building one (stale cached HTML?)', id);
  const host = document.createElement('div');
  host.id = id;
  host.className = 'hour-detail';
  host.hidden = true;
  const caption = strip.parentNode?.querySelector('.strip-caption');
  (caption || strip).insertAdjacentElement('afterend', host);
  return host;
}

function registerChart(key, strip, detail, series) {
  charts.push({ key, strip, detail, series });
  return {
    markNow: true,
    selected: pickedChart === key ? picked : null,
    onSelect: (entry) => pickHour(key, entry.time),
  };
}

function pickHour(key, time) {
  const same = pickedChart === key && picked === time; // clicking it again closes it
  picked = same ? null : time;
  pickedChart = same ? null : key;
  applySelection();
}

function clearPick() {
  picked = null;
  pickedChart = null;
  applySelection();
}

function applySelection() {
  const stillThere = charts.some(
    (chart) => chart.key === pickedChart && chart.series.some((e) => e.time === picked)
  );
  if (!stillThere) clearPickState(); // the hour dropped off the chart under it

  for (const { key, strip, detail, series } of charts) {
    if (!strip || !detail) continue; // degrade to one dead chart, never a dead page
    const time = key === pickedChart ? picked : null;
    for (const column of strip.querySelectorAll('.hour')) {
      column.classList.toggle('is-selected', Boolean(time) && column.dataset.time === time);
    }

    const entry = time ? series.find((item) => item.time === time) : null;
    if (entry) {
      renderHourDetail(detail, hourEntry(entry));
    } else {
      detail.innerHTML = '';
      detail.hidden = true;
    }
  }
}

function clearPickState() {
  picked = null;
  pickedChart = null;
}

function renderHourDetail(host, entry) {
  host.innerHTML = '';

  const color = entry.color || EFW.scoreColor(entry.score);
  host.style.setProperty('--c', color);
  host.style.setProperty('--c-ink', EFW.contrastText(color));

  const head = document.createElement('div');
  head.className = 'head';

  const when = document.createElement('span');
  when.className = 'when';
  when.textContent = EFW_I18N.dateTime(entry.time, { weekday: 'short' });
  head.append(when);

  if (entry.weather?.icon) {
    const icon = document.createElement('span');
    icon.className = 'icon';
    icon.textContent = entry.weather.icon;
    head.append(icon);
  }

  const conditions = document.createElement('span');
  conditions.className = 'cond';
  conditions.textContent = entry.weather?.text || '';
  head.append(conditions);

  const score = document.createElement('span');
  score.className = 'score';
  score.textContent = `${entry.score.toFixed(1)} · ${entry.label || EFW.scoreLabel(entry.score)}`;
  head.append(score);

  const close = document.createElement('button');
  close.type = 'button';
  close.className = 'close';
  close.textContent = '×';
  close.setAttribute('aria-label', T('hour.close'));
  close.addEventListener('click', clearPick);
  head.append(close);

  const grid = document.createElement('div');
  grid.className = 'now';
  statGrid(grid, [
    [T('now.temperature'), EFW_I18N.temp(entry.temperature)],
    [T('now.wetbulb'), EFW_I18N.temp(entry.wetbulb), 'info.wetbulb'],
    [T('now.dewpoint'), EFW_I18N.temp(entry.dewpoint), 'info.dewpoint'],
    [T('now.humidity'), fmt(entry.humidity, 0, ' %')],
    [
      T('now.wind'),
      `${fmt(entry.wind_speed_kmh, 0, ' km/h')}${entry.wind_direction_name ? ` ${entry.wind_direction_name}` : ''}`,
    ],
    [T('now.gusts'), fmt(entry.wind_gust_kmh, 0, ' km/h')],
    [T('hour.rain'), fmt(entry.precipitation, 1, ' mm')],
    [T('hour.rainChance'), fmt(entry.precipitation_prob, 0, ' %')],
  ]);

  host.append(head, grid);

  // Say so plainly, rather than letting a forecast for 09:00 read as advice.
  if (EFW.hourStart(entry.time) + 3600 * 1000 <= Date.now()) {
    const note = document.createElement('p');
    note.className = 'past-note';
    note.textContent = T('hour.past');
    host.append(note);
  }

  host.hidden = false;
}

/**
 * Every hour of one local day, in order, with the forecast dropped into place.
 *
 * The hours the forecast does not reach -- this morning, before the run that is
 * current began -- become empty slots rather than being left out. A day that
 * only half exists would otherwise draw half as many bars, twice as wide, and
 * the day cards could no longer be read against each other at a glance.
 *
 * Stepped by the hour in real time, so the 23- and 25-hour days either side of
 * a clock change come out the length they actually are.
 */
function fullDay(day) {
  const known = new Map(day.series.map((entry) => [EFW.hourStart(entry.time), entry]));
  const midnight = new Date(`${day.date}T00:00:00`); // no offset: local time
  const slots = [];

  for (let at = new Date(midnight); at.getDate() === midnight.getDate(); ) {
    const entry = known.get(at.getTime());
    slots.push(entry || { time: at.toISOString(), score: null });
    at = new Date(at.getTime() + 3600 * 1000);
  }
  return slots;
}

/** "Best 09:00–13:00", on the reader's chosen clock. Nothing at all if the day
    has no such stretch -- an empty label would only raise the question. */
function windowRow(className, label, window) {
  if (!window) return '';
  const span = `${EFW_I18N.time(window.start)}–${EFW_I18N.time(window.end)}`;
  // The score stays, but as the tooltip: the row is about when, not how much.
  return `<span class="${className}" title="${fmt(window.peak_score, 1)}">${label} <strong>${span}</strong></span>`;
}

function renderDays(days) {
  const host = $('days');
  host.innerHTML = '';
  const locale = EFW_I18N.locale();

  for (const day of days) {
    const row = document.createElement('article');
    row.className = 'day';

    const date = new Date(day.date);
    const temps = day.partial
      ? `<span class="lo">${EFW_I18N.tempShort(day.temp_min)}–${EFW_I18N.tempShort(day.temp_max)}</span>`
      : `<strong>${EFW_I18N.tempShort(day.temp_max)}</strong> <span class="lo">${EFW_I18N.tempShort(day.temp_min)}</span>`;

    const direction = day.wind_direction_name ? ` ${day.wind_direction_name}` : '';

    const header = document.createElement('header');
    header.innerHTML = `
      <span class="when">
        <span class="name">${date.toLocaleDateString(locale, { weekday: 'long' })}</span>
        <span class="date">${date.toLocaleDateString(locale, { day: 'numeric', month: 'short' })}</span>
      </span>
      <span class="cond"><span class="icon">${day.weather.icon || ''}</span> ${day.weather.text || ''}</span>
      <span class="temps">${temps}</span>
      <span class="meta">💧 ${fmt(day.precipitation_prob, 0, '%')} · ☀️ ${fmt(day.sunshine_hours, 0, ' h')} · 💨 ${fmt(
        day.wind_speed_kmh,
        0
      )}–${fmt(day.wind_gust_kmh, 0, ' km/h')}${direction}</span>
    `;

    const strip = document.createElement('div');
    strip.className = 'timeline day-strip';
    strip.setAttribute('role', 'group');
    strip.setAttribute(
      'aria-label',
      `${T('days.heading')} — ${date.toLocaleDateString(locale, { weekday: 'long' })}`
    );

    // Each day answers for its own bars, so the panel opens where you clicked
    // rather than somewhere off the top of the page.
    const detail = document.createElement('div');
    detail.className = 'hour-detail';
    detail.hidden = true;

    const hilo = document.createElement('div');
    hilo.className = 'hilo';
    hilo.innerHTML =
      day.hour_count < 3
        ? `<span>${T('days.partial', { n: day.hour_count })}</span>`
        : `
      ${windowRow('best', T('days.best'), day.fsi_best_window)}
      ${windowRow('worst', T('days.worst'), day.fsi_worst_window)}
      <span class="avg">${T('days.average')} ${fmt(day.fsi_avg, 1)} ${T('days.scoreUnit')}</span>
    `;

    row.append(header, strip, detail, hilo);
    host.append(row);
    const slots = fullDay(day);
    EFW.renderStrip(strip, slots, {
      labelEvery: 3,
      emptyLabel: T('days.noData'),
      ...registerChart(day.date, strip, detail, slots),
    });
  }
}

/* ------------------------------------------------------------------ radar */

let map = null;
let radarLayer = null;
let warningLayer = null;
let baseLayer = null;
let radarMeter = null;

/* The festival palette is dark, so the maps always use the dark basemap. */
const BASEMAP_URL = 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png';
const basemapUrl = () => BASEMAP_URL;

function initMap(data) {
  if (map) return;

  const { latitude, longitude } = data.location;
  map = L.map('map', { scrollWheelZoom: false }).setView([latitude, longitude], 8);

  // A map fills in piece by piece and can sit half-drawn for seconds, which
  // reads as broken rather than busy. Count the tiles instead.
  radarMeter = EFW_LOADING.meter($('map'));

  baseLayer = L.tileLayer(basemapUrl(), {
    maxZoom: 19,
    subdomains: 'abcd',
    attribution: '© OpenStreetMap, © CARTO',
  }).addTo(map);

  radarLayer = L.tileLayer
    .wms(DWD_WMS, {
      layers: data.radar.layer,
      format: 'image/png',
      transparent: true,
      version: '1.3.0',
      opacity: 0.75,
      attribution: 'Radar © DWD',
    })
    .addTo(map);

  radarMeter?.follow(baseLayer).follow(radarLayer);

  warningLayer = L.tileLayer.wms(DWD_WMS, {
    layers: 'dwd:Warnungen_Gemeinden',
    format: 'image/png',
    transparent: true,
    version: '1.3.0',
    opacity: 0.45,
    attribution: 'Warnings © DWD',
  });

  L.circleMarker([latitude, longitude], {
    radius: 6,
    color: '#f13ca3',
    weight: 2,
    fillColor: '#fff',
    fillOpacity: 1,
  })
    .addTo(map)
    .bindPopup(data.location.name);

  radarMeter?.follow(warningLayer);

  $('toggle-warnings').addEventListener('change', (event) => {
    if (event.target.checked) warningLayer.addTo(map);
    else map.removeLayer(warningLayer);
  });

}

function refreshRadar() {
  if (radarLayer) radarLayer.setParams({ _t: Date.now() });
  if (warningLayer) warningLayer.setParams({ _t: Date.now() });
  text(
    $('radar-status'),
    `${T('radar.updated')} ${EFW_I18N.time(new Date())}`
  );
}

/* ------------------------------------------------------------ model card */

/* The ICON-D2 fields. Pollen joins them as a fourth tab, but only once the
   reader has named an allergy -- see modelParams(). */
const ICON_PARAMS = ['clouds', 'temperature', 'wind'];
/* How long a frame stays up once it has actually arrived. Each step is a
   separate GRIB file the server may still be fetching, so the timer starts on
   the image's load event rather than blindly -- otherwise the first run through
   would race ahead of the pictures and show nothing but the last frame. */
const MODEL_FRAME_MS = 750;
/* If an image neither loads nor errors -- a request lost somewhere upstream --
   the animation must not simply stop dead with the button still on "pause". */
const MODEL_FRAME_TIMEOUT_MS = 12000;

let modelInfo = null;
let modelParam = 'clouds';
let modelStep = 0;
let modelMap = null;
let modelOverlay = null;
let modelMeter = null;
let modelPlaying = false;
let modelTimer = null;
let modelFailedStep = null; // retried once, not in a loop
let modelBounds = null; // which rectangle the overlay is currently hung on

/* ------------------------------------------------- pollen (one tab of it) */

/** The chosen species, or '' when pollen is off or unavailable. */
function pollenSpecies() {
  if (!modelInfo?.pollen) return '';
  const chosen = EFW_I18N.getAllergy();
  return modelInfo.pollen.species?.[chosen] ? chosen : '';
}

function pollenMeta() {
  const species = pollenSpecies();
  return species ? modelInfo.pollen.species[species] : null;
}

/** Tabs on the model card: the ICON fields, plus pollen once one is chosen. */
function modelParams() {
  return pollenSpecies() ? [...ICON_PARAMS, 'pollen'] : ICON_PARAMS;
}

const isPollen = () => modelParam === 'pollen';

/**
 * What the current tab is drawn from.
 *
 * Pollen is a different model on a different grid in daily rather than hourly
 * steps, so every one of these has to be asked per tab instead of read off the
 * card once. Answering them in one place keeps that from leaking into every
 * caller.
 */
function modelMeta() {
  if (!isPollen()) return modelInfo?.parameters?.[modelParam] ?? null;
  const meta = pollenMeta();
  if (!meta) return null;
  // Shaped like an ICON parameter so the legend renderer needs no special case.
  // The API names the levels in its own vocabulary ("very_high"); only the
  // frontend knows the reader's language, so they are translated here.
  return {
    unit: modelInfo.pollen.unit,
    bands: meta.bands.map((band) => ({
      ...band,
      label: T(`pollen.level.${band.label}`),
      // The top band is open-ended, and printing its invented upper edge in the
      // tooltip would claim a ceiling the data does not have.
      to: band.open ? null : band.to,
    })),
  };
}

const modelMaxStep = () =>
  (isPollen() ? modelInfo?.pollen?.max_step : modelInfo?.max_step) ?? 24;

const modelStepHours = () => (isPollen() ? modelInfo?.pollen?.step_hours ?? 24 : 1);

const modelRun = () => (isPollen() ? modelInfo?.pollen?.run : modelInfo?.run) || null;

const modelViewBox = () => (isPollen() ? modelInfo?.pollen?.bbox : modelInfo?.bbox) ?? null;

/** True when the chosen species has no season today, so there is nothing to draw. */
const pollenOffSeason = () => isPollen() && pollenMeta()?.in_season === false;

function modelImageUrl(step) {
  return isPollen()
    ? `/api/pollen.png?species=${pollenSpecies()}&step=${step}&width=720`
    : `/api/model.png?param=${modelParam}&step=${step}&width=720`;
}

/** The allergy picker beside the language buttons. */
function buildAllergySwitch() {
  const host = $('allergy-switch');
  const select = $('allergy-select');
  if (!host || !select || !modelInfo?.pollen) return;

  const chosen = EFW_I18N.getAllergy();
  select.innerHTML = '';
  for (const key of ['', ...EFW_I18N.ALLERGIES]) {
    const option = document.createElement('option');
    option.value = key;
    // Out-of-season species stay on the list, marked. Dropping them would make
    // the menu change shape through the year with no explanation, and "birch is
    // not published in August" is a better answer than a missing entry.
    const meta = key && modelInfo.pollen.species?.[key];
    const suffix = meta && !meta.in_season ? ` (${T('pollen.offSeason')})` : '';
    option.textContent = key ? `${T(`pollen.${key}`)}${suffix}` : T('pollen.none');
    option.selected = key === chosen;
    select.append(option);
  }
  host.hidden = false;
  sizeAllergySwitch();
}

/** Write the species on show into the pill -- the select over it is invisible,
 *  so this span is both the text and the width. See .allergy-switch in the
 *  stylesheet. Wanted after every rebuild (the language changes the words) and
 *  after every choice. */
function sizeAllergySwitch() {
  const select = $('allergy-select');
  const sizer = $('allergy-sizer');
  if (!select || !sizer) return;
  sizer.textContent = select.options[select.selectedIndex]?.textContent ?? '';
}

function onAllergyChange() {
  EFW_I18N.setAllergy($('allergy-select').value);
  sizeAllergySwitch();
  // The pollen tab appears or disappears with the choice, and a card sitting on
  // it when it goes has to fall back rather than keep requesting a dead layer.
  if (isPollen() && !pollenSpecies()) modelParam = 'clouds';
  else if (pollenSpecies()) modelParam = 'pollen'; // choosing one means wanting to see it
  buildModelTabs();
  buildModelHours();
  updateModel();
}

/**
 * The play button and the row of forecast hours.
 *
 * Built here if the markup does not carry them, for the same reason
 * ensureDetail exists: a browser holding a cached copy of the page from before
 * these controls existed would otherwise take the whole model card down with
 * it -- reaching for an id that is not there threw, and the map never
 * initialised at all. The cache headers make that window small; they do not
 * close it, and one stale page should cost one feature, not the card.
 */
function ensureModelControls() {
  if ($('model-hours') && $('model-play')) return true;

  console.warn('EFW: model controls missing from the markup, building them (stale cached HTML?)');
  const legend = $('model-legend');
  const card = legend?.closest('.card');
  if (!card) return false;

  // Whatever the old markup used to drive the forecast hour goes: two of them
  // would fight over the same step.
  card.querySelector('.model-step')?.remove();

  const row = document.createElement('div');
  row.className = 'model-step';
  row.innerHTML =
    '<button type="button" class="play" id="model-play" aria-pressed="false"></button>' +
    '<div class="hours" id="model-hours" role="group"></div>';
  legend.insertAdjacentElement('beforebegin', row);
  return true;
}

/** A field of colour means nothing without coastlines under it. */
function ensureModelMap() {
  if (modelMap || !modelInfo) return;

  // Leaflet cannot fit bounds inside a zero-size container: while <main> is
  // still hidden the map would silently settle on a whole-world view.
  const container = $('model-map');
  if (!container || !container.offsetWidth) return;

  const b = modelInfo.bbox;
  modelMap = L.map(container, {
    scrollWheelZoom: false,
    attributionControl: false,
    // Integer zoom steps would round down past the exact fit and leave the
    // field floating in the middle of the frame; fractional zoom fills it.
    zoomSnap: 0,
  });
  modelMeter = EFW_LOADING.meter(container);
  const tiles = L.tileLayer(basemapUrl(), { maxZoom: 19, subdomains: 'abcd' }).addTo(modelMap);
  modelMeter?.follow(tiles);
  modelMap.fitBounds(
    [
      [b.min_lat, b.min_lon],
      [b.max_lat, b.max_lon],
    ],
    { padding: [0, 0] }
  );
}

async function initModel() {
  if (modelInfo) return; // already set up on an earlier refresh
  try {
    const response = await EFW_LOADING.track(fetch('/api/model', { cache: 'no-store' }));
    if (!response.ok) throw new Error(`server ${response.status}`);
    modelInfo = await response.json();
  } catch (error) {
    console.error('EFW: model info unavailable', error);
    text($('model-status'), T('model.unavailable'));
    return;
  }

  try {
    setUpModel();
  } catch (error) {
    // One broken card, never a broken page: the index, the day charts and the
    // radar have nothing to do with this and must still come up.
    console.error('EFW: model card failed to start', error);
    modelInfo = null;
    text($('model-status'), T('model.unavailable'));
  }
}

function buildModelTabs() {
  const tabs = $('model-tabs');
  if (!tabs) return;
  tabs.innerHTML = '';
  for (const key of modelParams()) {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.param = key;
    // The pollen tab names the species, not the word "pollen": with a picker
    // above choosing between five of them, "Pollen" alone would not say which.
    button.textContent = key === 'pollen' ? T(`pollen.${pollenSpecies()}`) : T(`model.${key}`);
    button.setAttribute('role', 'tab');
    // Set here as well as in updateModel: the tabs are rebuilt on a language
    // switch, and the new buttons would otherwise come up with none marked.
    button.classList.toggle('active', key === modelParam);
    button.addEventListener('click', () => {
      stopModelPlay();
      modelParam = key;
      // Hours and days are different lengths of list; a step from one can sit
      // off the end of the other.
      modelStep = Math.min(modelStep, modelMaxStep());
      buildModelHours();
      updateModel();
    });
    tabs.append(button);
  }
}

function setUpModel() {
  buildAllergySwitch();
  $('allergy-select')?.addEventListener('change', onAllergyChange);

  // Pinnable like the language and unit switches, so a link can open on the
  // field it is talking about.
  const asked = new URLSearchParams(location.search).get('model');
  if (modelParams().includes(asked)) modelParam = asked;

  buildModelTabs();

  if (ensureModelControls()) {
    buildModelHours();
    $('model-play').addEventListener('click', toggleModelPlay);
    // Nobody is watching a hidden tab, and every frame is a GRIB file the
    // server may have to fetch. Stop rather than animate into the void.
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) stopModelPlay();
    });
    syncModelPlay();
  }
  updateModel();
}

/* A step is an hour on the ICON tabs and a day on the pollen one, so both the
   label and the tooltip have to follow the tab rather than be fixed. */
const stepLabel = (step) =>
  step === 0 ? T(isPollen() ? 'model.today' : 'model.now') : `+${step}${isPollen() ? ' d' : ''}`;

const stepTitle = (step) =>
  T(isPollen() ? 'model.daysAhead' : 'model.hoursAhead', { n: step });

/** One button per forecast step: "now" and then +1, +2, +3 … */
function buildModelHours() {
  const host = $('model-hours');
  if (!host) return;
  host.innerHTML = '';
  host.setAttribute('aria-label', T(isPollen() ? 'model.stepDay' : 'model.step'));
  for (let step = 0; step <= modelMaxStep(); step++) {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.step = String(step);
    button.textContent = stepLabel(step);
    button.title = stepTitle(step);
    button.addEventListener('click', () => {
      stopModelPlay(); // picking a step by hand means you want to stay on it
      modelStep = step;
      updateModel();
    });
    host.append(button);
  }
}

/** Mark the selected step. Every one is on screen, so nothing has to scroll. */
function syncModelHours() {
  const host = $('model-hours');
  if (!host) return;
  // The list is rebuilt when the tab changes, so a stale one here means the
  // steps belong to the other kind of tab and the labels would lie.
  if (host.children.length !== modelMaxStep() + 1) buildModelHours();
  for (const button of host.children) {
    const step = Number(button.dataset.step);
    const on = step === modelStep;
    // Relabelled here rather than only at build time, so a language switch
    // reaches "now" without tearing the grid down and rebuilding it.
    button.textContent = stepLabel(step);
    button.title = stepTitle(step);
    button.classList.toggle('active', on);
    button.setAttribute('aria-pressed', String(on));
  }
}

function toggleModelPlay() {
  if (modelPlaying) stopModelPlay();
  else startModelPlay();
}

function startModelPlay() {
  if (!modelInfo) return;
  modelPlaying = true;
  syncModelPlay();
  advanceModel();
}

function stopModelPlay() {
  modelPlaying = false;
  clearTimeout(modelTimer);
  modelTimer = null;
  syncModelPlay();
}

function advanceModel() {
  modelStep = modelStep >= modelMaxStep() ? 0 : modelStep + 1; // loops
  updateModel();
}

/** Called when a frame has arrived (or given up): queue the next one. */
function scheduleModelFrame() {
  if (!modelPlaying) return;
  clearTimeout(modelTimer);
  modelTimer = setTimeout(advanceModel, MODEL_FRAME_MS);
}

function onModelFrame() {
  modelMeter?.settle();
  modelFailedStep = null;
  scheduleModelFrame();
}

function onModelFrameFailed() {
  modelMeter?.settle();
  console.warn('EFW: model image failed for +%dh', modelStep);

  if (modelPlaying) {
    scheduleModelFrame(); // the animation moves on; one gap is not a failure
    return;
  }

  // Standing still on a broken frame used to look like nothing was happening
  // at all. Say so, and give it one more go -- these are usually a DWD hiccup.
  text($('model-status'), T('model.unavailable'));
  if (modelFailedStep === modelStep) return;
  modelFailedStep = modelStep;
  setTimeout(() => {
    if (!modelPlaying && modelFailedStep === modelStep) updateModel();
  }, 4000);
}

function syncModelPlay() {
  const button = $('model-play');
  if (!button) return;
  button.textContent = modelPlaying ? '⏸' : '▶';
  button.classList.toggle('is-playing', modelPlaying);
  button.setAttribute('aria-pressed', String(modelPlaying));
  button.setAttribute('aria-label', T(modelPlaying ? 'model.pause' : 'model.play'));
  button.title = T(modelPlaying ? 'model.pause' : 'model.play');
}

function updateModel() {
  if (!modelInfo) return;

  const step = modelStep;
  syncModelHours();

  for (const button of $('model-tabs').children) {
    button.classList.toggle('active', button.dataset.param === modelParam);
  }

  ensureModelMap();

  // A species out of its season has no file behind it at all, so asking for one
  // would be a guaranteed 404. Say which months it does cover instead.
  if (pollenOffSeason()) {
    stopModelPlay();
    if (modelOverlay) {
      modelMap?.removeLayer(modelOverlay);
      modelOverlay = null;
      modelBounds = null;
    }
    const meta = pollenMeta();
    const asDate = (iso) => EFW_I18N.dateOnly(EFW_I18N.dayStart(iso), { month: 'long' });
    text(
      $('model-status'),
      T('pollen.notInSeason', {
        species: T(`pollen.${pollenSpecies()}`),
        start: asDate(meta.season.start),
        end: asDate(meta.season.end),
      })
    );
    renderModelLegend();
    return;
  }

  const url = modelImageUrl(step);
  const box = modelViewBox();
  const bounds = box && [
    [box.min_lat, box.min_lon],
    [box.max_lat, box.max_lon],
  ];

  if (modelOverlay) {
    modelMeter?.expect();
    // The pollen grid covers Germany only, so it hangs on a different rectangle
    // from the ICON fields. Moving the image without moving its frame would
    // stretch one model's field across the other's ground.
    if (bounds && String(bounds) !== String(modelBounds)) modelOverlay.setBounds(bounds);
    modelOverlay.setUrl(url);
  } else if (modelMap && bounds) {
    modelMeter?.expect();
    modelOverlay = L.imageOverlay(url, bounds, {
      opacity: 0.75,
      interactive: false,
    }).addTo(modelMap);
    modelOverlay.on('load', onModelFrame);
    // A step DWD has not published yet answers 502. Say so, and when playing
    // skip on to the next one rather than stalling the animation there.
    modelOverlay.on('error', onModelFrameFailed);
  }
  modelBounds = bounds;

  // Belt and braces: neither event is guaranteed to fire for every URL.
  if (modelPlaying) {
    clearTimeout(modelTimer);
    modelTimer = setTimeout(advanceModel, MODEL_FRAME_TIMEOUT_MS);
  }

  // The pollen run is a bare date, so it is read as local noon; an ICON run is
  // a full timestamp and keeps its hour.
  const run = modelRun() ? EFW_I18N.dayStart(modelRun()) : null;
  const valid = run
    ? new Date(run.getTime() + step * modelStepHours() * 3600 * 1000)
    : null;
  // A daily mean names a day and nothing finer; an hourly field names the hour.
  const stamp = isPollen() ? EFW_I18N.dateOnly : EFW_I18N.dateTime;
  text(
    $('model-status'),
    [
      run ? `${T('model.run')} ${stamp(run, { day: 'numeric', month: 'short' })}` : '',
      valid ? `→ ${stamp(valid, { weekday: 'short' })}` : '',
    ]
      .filter(Boolean)
      .join(' ')
  );

  // The key describes the field, not the step: rebuilding it on every frame of
  // the animation would be churn for nothing.
  if (legendParam !== modelParam + pollenSpecies()) renderModelLegend();
}

let legendParam = null; // which field the key on screen describes

function renderModelLegend() {
  const host = $('model-legend');
  const meta = modelMeta();
  // Nothing to describe yet -- this runs once on the first payload, before
  // /api/model has answered. Leave the key alone rather than blanking it, and
  // leave legendParam unset so updateModel still builds it when the data lands.
  if (!host || !meta) return;

  legendParam = modelParam + pollenSpecies();
  host.innerHTML = '';

  if (isPollen()) {
    // Out of season there is no field and so no scale, but the caveat below
    // still belongs on screen -- it is about the product, not about today.
    if (meta && !pollenOffSeason()) {
      host.append(scaleRow(T(`pollen.${pollenSpecies()}`), meta, false));
    }
    const note = document.createElement('div');
    note.className = 'note';
    note.textContent = `${T('pollen.source')} ${T('pollen.caveat')}`;
    host.append(note);
    return;
  }

  host.append(scaleRow(T(`model.${modelParam}`), meta, modelParam === 'temperature'));

  // Clouds carry rain on top, so that overlay needs its own scale.
  if (meta.overlay) {
    host.append(scaleRow(T('model.rain'), meta.overlay, false));
  }

  if (meta.arrows) {
    const note = document.createElement('div');
    note.className = 'note';
    note.innerHTML = `<span class="arrow">→</span> ${T('model.windNote')}`;
    host.append(note);
  }
}

/** How many values fit along a scale before they start colliding. */
function labelStride(count, width) {
  const perLabel = 30; // room for a number like "-10" and a gap
  return Math.max(1, Math.ceil(perLabel / Math.max(1, width / count)));
}

/**
 * One scale under the map.
 *
 * The field is drawn in steps, so the key is drawn in the same steps: a block
 * per band, and the numbers on the boundaries between them. A single smooth
 * ramp could only ever be honest about its two ends, which is what made the old
 * one unreadable -- there was no way to tell 12 °C from 18 °C on it.
 */
function scaleRow(name, meta, isTemperature) {
  const row = document.createElement('div');
  row.className = 'row';

  // The unit is named once, beside the field, rather than on every number
  // along the scale -- repeated, they were wide enough to collide at the end.
  const unit = isTemperature ? `°${EFW_I18N.getUnit()}` : meta.unit;
  const label = document.createElement('span');
  label.className = 'name';
  label.textContent = `${name} (${unit})`;

  const bar = document.createElement('div');
  bar.className = 'bar';

  const number = (v) => (isTemperature ? EFW_I18N.tempShort(v).replace('°', '') : String(v));
  const full = (v) => (isTemperature ? EFW_I18N.temp(v, 0) : `${v} ${meta.unit}`);

  if (meta.bands?.length) {
    const swatches = document.createElement('div');
    swatches.className = 'swatches';
    for (const band of meta.bands) {
      const cell = document.createElement('span');
      cell.style.background = band.color;
      // A band with no upper edge (the top pollen level) reads as "at or above",
      // rather than borrowing a ceiling the data does not have.
      const range =
        band.to === null || band.to === undefined
          ? `≥ ${full(band.from)}`
          : `${full(band.from)}–${full(band.to)}`;
      cell.title = band.label ? `${band.label} — ${range}` : range;
      swatches.append(cell);
    }
    bar.append(
      swatches,
      meta.bands[0].label ? cellMarks(meta.bands) : edgeMarks(meta.bands, number)
    );
  } else {
    // Rain is the exception: its ramp is square-rooted, so it stays a gradient
    // with the ticks sitting where those rates actually fall on it.
    const stops = meta.ramp.map(([at, color]) => `${color} ${(at * 100).toFixed(0)}%`);
    const scale = document.createElement('span');
    scale.className = 'scale';
    scale.style.background = `linear-gradient(to right, ${stops.join(', ')})`;
    bar.append(scale, tickMarks(meta.ticks || []));
  }

  row.append(label, bar);
  return row;
}

/** A name centred under each block -- "1/8" … "8/8" for the cloud eighths. */
function cellMarks(bands) {
  const marks = document.createElement('div');
  marks.className = 'marks cells';
  for (const band of bands) {
    const mark = document.createElement('span');
    mark.textContent = band.label;
    marks.append(mark);
  }
  return marks;
}

/** Numbers on the boundaries between blocks, thinned until they fit. */
function edgeMarks(bands, value) {
  const marks = document.createElement('div');
  marks.className = 'marks';

  const edges = [...bands.map((band) => band.from), bands[bands.length - 1].to];
  const last = edges.length - 1;
  // Measured against the card: the bar itself has no width until it is in the
  // document, and this only has to decide how many numbers to draw.
  const room = Math.max(140, ($('model-legend')?.clientWidth || 420) - 122); // less the name
  const stride = labelStride(bands.length, room);

  const wanted = new Set();
  for (let index = 0; index <= last; index += stride) wanted.add(index);
  // The end of the scale always gets its number, and whatever falls less than
  // a full stride short of it gives way -- otherwise the two run together.
  const previous = last - (last % stride || stride);
  if (last - previous < stride) wanted.delete(previous);
  wanted.add(last);

  for (const index of [...wanted].sort((a, b) => a - b)) {
    const mark = document.createElement('span');
    mark.className = index === 0 ? 'first' : index === last ? 'last' : '';
    mark.style.left = `${(index / last) * 100}%`;
    mark.textContent = value(edges[index]);
    marks.append(mark);
  }
  return marks;
}

/** Ticks at their own positions along a gradient. */
function tickMarks(ticks) {
  const marks = document.createElement('div');
  marks.className = 'marks';
  ticks.forEach((tick, index) => {
    const mark = document.createElement('span');
    mark.className = index === 0 ? 'first' : index === ticks.length - 1 ? 'last' : '';
    mark.style.left = `${tick.at * 100}%`;
    mark.textContent = String(tick.value);
    marks.append(mark);
  });
  return marks;
}

/* ------------------------------------------------- site load & the notices */

/* The server puts its load on every /api/ response, so knowing that the site is
   busy costs no request of its own. Held here so a language switch can redraw
   the notice without waiting for the next refresh. */
let siteLoad = 'normal';

function readSiteLoad(response) {
  const level = response.headers.get('X-Site-Load');
  // Absent when the operator turned counting off, or when a proxy strips it.
  siteLoad = level === 'busy' || level === 'crowded' ? level : 'normal';
  renderLoadNotice();
}

function renderLoadNotice() {
  const box = $('load-notice');
  if (!box) return;
  box.hidden = siteLoad === 'normal';
  box.classList.toggle('crowded', siteLoad === 'crowded');
  if (!box.hidden) text(box, T(`load.${siteLoad}`));
}

/* Shown once per device until dismissed. Nothing here is a consent gate: the
   site sets no cookies and stores only what the visitor chose, so the box tells
   rather than asks, and the page underneath is fully usable behind it. */
function initStorageNotice() {
  const box = $('storage-notice');
  if (!box || EFW_I18N.noticeSeen()) return;
  box.hidden = false;
  $('notice-ok')?.addEventListener('click', () => {
    EFW_I18N.setNoticeSeen();
    box.hidden = true;
  });
}

/* ------------------------------------------------------------- preferences */

function initPreferences() {
  for (const button of $('lang-switch').children) {
    button.addEventListener('click', () => {
      EFW_I18N.setLang(button.dataset.lang);
      syncToggles();
      load(); // generated text comes from the API, so refetch in the new language
    });
  }

  // Units and clock are conversions of what we already hold, so they redraw
  // rather than refetch.
  for (const [id, apply] of [
    ['unit-switch', (button) => EFW_I18N.setUnit(button.dataset.unit)],
    ['clock-switch', (button) => EFW_I18N.setClock(button.dataset.clock)],
  ]) {
    for (const button of $(id).children) {
      button.addEventListener('click', () => {
        apply(button);
        syncToggles();
        if (latest) render(latest);
      });
    }
  }
  syncToggles();
}

function syncToggles() {
  for (const button of $('lang-switch').children) {
    button.classList.toggle('active', button.dataset.lang === EFW_I18N.getLang());
  }
  for (const button of $('unit-switch').children) {
    button.classList.toggle('active', button.dataset.unit === EFW_I18N.getUnit());
  }
  for (const button of $('clock-switch').children) {
    button.classList.toggle('active', button.dataset.clock === EFW_I18N.getClock());
  }
  EFW_I18N.apply();
  renderLoadNotice(); // its text is set in JS, so apply() cannot reach it

  // Send a German reader to the German page. Both are real pages rather than
  // one page with a switch, so this is a link swap rather than a translation.
  const privacy = EFW_I18N.getLang() === 'de' ? '/datenschutz' : '/privacy';
  for (const link of document.querySelectorAll('.privacy-link')) link.href = privacy;
}

/* ------------------------------------------------------------------- load */

function render(data) {
  if (data.bands) EFW.setBands(data.bands);

  charts = [];
  conditionsByTime = new Map((data.fsi_series || []).map((entry) => [entry.time, entry]));

  renderWarnings(data.warnings);
  renderFSI(data);

  const timeline = $('timeline');
  const outlook = EFW.outlook(data.fsi_series, 24, PAST_CONTEXT_HOURS);
  EFW.renderStrip(timeline, outlook, {
    labelEvery: 2,
    emptyLabel: T('days.noData'),
    warnings: EFW.warningRanges(data.warnings),
    ...registerChart('timeline', timeline, ensureDetail('hour-detail', timeline), outlook),
  });

  renderLegend($('legend-days'));
  renderNow(data.current, data.fsi);
  renderDays(data.daily);
  renderModelLegend();
  if (modelInfo) {
    // All of these carry generated text, so they follow the language.
    buildAllergySwitch();
    buildModelTabs();
    syncModelHours();
    syncModelPlay();
  }
  applySelection(); // a panel left open survives the five-minute refresh

  // The short name, not the full one: "EF30" is what the header has room for,
  // and config.json already carries both. Falls back to the long name so an
  // event that never set a short one still gets a heading rather than a blank.
  const event = data.event || {};
  const shortName = event.short_name || event.name;
  if (shortName) text($('event-name'), shortName);
  text($('where'), data.location.name);

  // The subtitle is for trouble only -- it used to carry "observation HH:MM",
  // which was wrong whenever the station report was missing and the hour came
  // from MOSMIX instead. The timestamp lives on the index panel, which knows
  // which of the two it is showing.
  //
  // The one thing it does say: that these numbers are old. A payload this far
  // past its build time came out of the offline cache, so the page is up but
  // the data behind it is not what is happening outside.
  const stale = Date.now() - new Date(data.generated_at).getTime() > STALE_AFTER_MS;
  const subtitle = $('subtitle');
  subtitle.hidden = !stale;
  subtitle.classList.toggle('stale', stale);
  if (stale) {
    text(
      subtitle,
      T('app.stale', {
        when: EFW_I18N.dateTime(data.generated_at, { day: 'numeric', month: 'short' }),
      })
    );
  }

  const stamp = { day: '2-digit', month: '2-digit', year: 'numeric' };
  const meta = [`${T('footer.updated')} ${EFW_I18N.dateTime(data.generated_at, stamp)}`];
  if (data.forecast_issued) {
    meta.push(`${T('footer.mosmixRun')} ${EFW_I18N.dateTime(data.forecast_issued, stamp)}`);
  }
  if (data.degraded.length) meta.push(`⚠️ ${data.degraded.join(', ')}`);
  text($('footer-meta'), meta.join(' · '));
}

async function load() {
  try {
    const response = await EFW_LOADING.track(
      fetch(`/api/summary?lang=${EFW_I18N.getLang()}`, { cache: 'no-store' })
    );
    // Before the status check: a 429 under a rush is precisely when the visitor
    // most deserves to be told the site is busy rather than broken.
    readSiteLoad(response);
    if (!response.ok) throw new Error(`server ${response.status}`);
    const data = await response.json();

    latest = data;

    // Unhide first: the charts measure themselves as they draw -- how sparsely
    // to place the icons, which range labels still fit -- and inside a hidden
    // <main> every one of those measurements comes back zero.
    $('main').hidden = false;
    $('error').hidden = true;
    const skeleton = $('skeleton');
    if (skeleton) skeleton.hidden = true; // the real thing has arrived
    render(data);

    initMap(data);
    refreshRadar();
    initModel(); // only now that the card has a measurable size
  } catch (error) {
    console.error('EFW load failed', error);
    const box = $('error');
    box.hidden = false;
    text(box, `${T('app.error')}: ${error.message}. ${T('app.retry')}`);
    $('subtitle').hidden = false; // it only ever says something when it is bad news
    text($('subtitle'), T('app.offline'));
    // Keep the skeleton up: it says "still trying" where a blank page would
    // just look broken, and the error sits above it either way.
    const skeleton = $('skeleton');
    if (skeleton && !latest) skeleton.hidden = false;
  }
}

/* Bar widths, how sparsely the icons are drawn and which range labels still fit
   are all measured at render time, so a resize has to redraw rather than
   reflow. Debounced: a drag fires this continuously. */
let resizeTimer = null;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => latest && render(latest), 200);
});

/* The offline copy. Registered after load so it never competes with the first
   paint, and failure-tolerant: a private window, an older browser or a plain
   HTTP origin refuses service workers, and all that should cost is the offline
   copy rather than the page. See sw.js. */
function initOffline() {
  if (!('serviceWorker' in navigator)) return;
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch((error) => {
      console.warn('EFW: offline copy unavailable', error);
    });
  });
}

EFW_I18N.apply();
initPreferences();
initStorageNotice();
initOffline();
load();
setInterval(load, REFRESH_MS);
