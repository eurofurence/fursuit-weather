/* Frontend strings and user preferences (language, temperature unit).
   Static markup carries data-i18n="key"; dynamic text calls T('key'). */

window.EFW_I18N = (function () {
  const STRINGS = {
    en: {
      'app.heading': 'Weather',
      'app.offline': 'Offline',
      'app.error': 'Could not load weather data',
      'app.retry': 'Retrying shortly…',
      'app.stale': 'Saved copy from {when}. could not reach the server.',

      'load.busy': 'Busy right now. a lot of people are here, so pages may take a moment.',
      'load.crowded':
        'Very busy right now. This site runs on one small computer, so loading will be slow for a while. Everything still works. please be patient!',

      'fsi.heading': 'Fursuiting Index',
      'fsi.now': 'right now',
      'fsi.next24': 'Next 24 hours · tap a bar for details',
      'fsi.best': 'Best stretch',
      'fsi.worst': 'Worst stretch',
      'fsi.noBest': 'No good window in the next 24 hours.',
      'fsi.noWorst': 'Nothing to avoid in the next 24 hours.',
      'fsi.peaking': 'peaking at',
      'fsi.dropping': 'dropping to',
      'fsi.hours': 'h',
      'fsi.scoreHeader': 'Score',
      'fsi.explainSummary': 'How is this calculated?',
      'fsi.explainBody':
        'The Index ranks the ability to be in a fursuit outdoors, from 0 to 10. It weighs heat stress from the wet-bulb temperature plus sun load. Wet-bulb is the coolest your body can get by sweating, so it reads lower than the air temperature — and the closer the two are, the less the sweating helps, which is exactly what a suit has to cope with. Dew point is a separate figure and says how clammy the air feels: above about 15 °C it starts to feel muggy. Official DWD warnings do not change the score: they are marked on the bars over the hours they cover, so you can judge them yourself.',

      'band.excellent': 'Excellent',
      'band.good': 'Good',
      'band.fair': 'Fair',
      'band.poor': 'Poor',
      'band.bad': 'Bad',

      'now.heading': 'Right now',
      'now.conditions': 'Conditions',
      'now.temperature': 'Temperature',
      /* Not "feels like". Both of these sit *below* the air temperature, so
         labelling either as an apparent temperature reads as a mistake on a
         muggy day -- "28 °C, feels like 22 °C" is the opposite of the truth.
         They are named for what they are, and fsi.explainBody says what they
         mean. */
      'now.wetbulb': 'Wet-bulb',
      'now.dewpoint': 'Dew point',
      'now.humidity': 'Humidity',
      'now.wind': 'Wind',
      'now.gusts': 'Gusts',
      'now.rain1h': 'Rain (last hour)',
      'now.pressure': 'Pressure',

      'hour.rain': 'Rain (this hour)',
      'hour.rainChance': 'Chance of rain',
      'hour.close': 'Close',
      'hour.past': 'This hour has already passed.',
      'hour.now': 'Right now',
      'hour.at': 'At {time}',
      'hour.backToNow': 'tap the bar again for now',

      'days.heading': 'Next days',
      'days.best': 'Best',
      'days.worst': 'Worst',
      'days.average': 'Daytime average',
      'days.scoreUnit': 'FSI score',
      'days.partial': 'Only {n} h of forecast available.',
      'days.noData': 'No data',

      'warnings.more': '+{n} more',
      'warnings.advance': 'ADVANCE NOTICE',
      'warnings.advanceNote': 'Advance notice: possible severe weather, not yet a warning in force.',
      'radar.heading': 'Rain radar',
      'radar.showWarnings': 'Show warning areas',
      'radar.updated': 'Radar updated',

      'model.heading': 'Model maps from ICON (DWD)',
      'model.clouds': 'Clouds',
      'model.temperature': 'Temperature',
      'model.wind': 'Wind',
      'model.loading': 'Loading model layer…',
      'model.unavailable': 'Model layer unavailable right now.',
      'model.run': 'Model run',
      'model.step': 'Forecast hour',
      'model.now': 'now',
      'model.hoursAhead': '{n} h after the model run',
      'model.play': 'Play the forecast hours',
      'model.pause': 'Pause',
      'model.rain': 'Rain',
      'model.windNote': 'Arrows point the way the wind blows.',
      'model.pollen': 'Pollen',
      'model.daysAhead': '{n} days after the model run',
      'model.today': 'today',
      'model.stepDay': 'Forecast day',

      'pollen.label': 'Allergy',
      'pollen.none': 'None',
      'pollen.hazel': 'Hazel',
      'pollen.alder': 'Alder',
      'pollen.birch': 'Birch',
      'pollen.grasses': 'Grasses',
      'pollen.ragweed': 'Ragweed',
      'pollen.offSeason': 'out of season',
      'pollen.notInSeason':
        '{species} is out of season. DWD publishes it from {start} to {end}.',
      'pollen.pick': 'Pick an allergy above to see its forecast here.',
      'pollen.level.low': 'Low',
      'pollen.level.moderate': 'Moderate',
      'pollen.level.high': 'High',
      'pollen.level.very_high': 'Very high',
      'pollen.source': 'ICON-ART daily mean, DWD.',
      'pollen.caveat':
        'Research data. DWD states it is not suitable for clinical use. The low/high bands are this site’s own.',

      'footer.updated': 'Updated',
      'footer.mosmixRun': 'MOSMIX run',
      'footer.data': 'Weather data',
      'footer.mapData': 'Map data',
      'footer.display': 'ConOps display',
      'footer.api': 'Weather API',
      'footer.disclaimer':
        'Official Eurofurence site. Always follow the official DWD warnings, and for convention announcements the official Telegram channel:',
      'footer.notifications': 'Eurofurence Notifications',
      'footer.builtBy': 'Built by',
      'footer.source': 'github',
      'footer.units': 'Units',
      'footer.clock': 'Time',
      'footer.privacy': 'Privacy',
      'notice.text':
        'No advertising, no analytics, no tracking cookies.',
      'notice.ok': 'Got it', 
      'notice.details': 'What is stored',
      'lang.label': 'Language',
      'display.allClear': 'No active warnings',
      'display.warnings': 'Active DWD warnings',
      'display.next18': 'Next 18 hours',
    },

    de: {
      'app.heading': 'Wetter',
      'app.offline': 'Offline',
      'app.error': 'Wetterdaten konnten nicht geladen werden',
      'app.retry': 'Neuer Versuch in Kürze…',
      'app.stale': 'Gespeicherte Fassung von {when}. Server nicht erreichbar.',

      'load.busy': 'Gerade ist viel los. es sind viele Leute hier, das Laden kann etwas dauern.',
      'load.crowded':
        'Sehr viel los gerade. Diese Seite läuft auf einem einzelnen kleinen Rechner, das Laden wird eine Weile langsam sein. Es funktioniert weiterhin alles.',

      'fsi.heading': 'Fursuiting Index',
      'fsi.now': 'jetzt',
      'fsi.next24': 'Nächste 24 Stunden · Balken antippen für Details',
      'fsi.best': 'Bester Zeitraum',
      'fsi.worst': 'Ungünstigster Zeitraum',
      'fsi.noBest': 'Kein guter Zeitraum in den nächsten 24 Stunden.',
      'fsi.noWorst': 'Nichts zu vermeiden in den nächsten 24 Stunden.',
      'fsi.peaking': 'Bestwert',
      'fsi.dropping': 'Tiefstwert',
      'fsi.hours': 'Std.',
      'fsi.scoreHeader': 'Punkte',
      'fsi.explainSummary': 'Wie wird das berechnet?',
      'fsi.explainBody':
        'Der Index bewertet von 0 bis 10, wie angenehm und sicher es im Fursuit draußen ist. Er gewichtet die Hitzebelastung aus der Feuchtkugeltemperatur und der Sonneneinstrahlung, zusammen mit Wind und Niederschlagsvorhersage. Die Feuchtkugeltemperatur ist der kühlste Wert, den dein Körper durchs Schwitzen noch erreicht — sie liegt deshalb unter der Lufttemperatur, und je näher beide beieinander liegen, desto weniger bringt das Schwitzen. Genau das muss ein Fursuit aushalten. Der Taupunkt ist eine eigene Größe und sagt, wie schwül sich die Luft anfühlt: ab etwa 15 °C wird es klamm. Amtliche DWD-Warnungen verändern den Wert nicht: Sie sind über den betroffenen Stunden an den Balken markiert, damit du sie selbst einschätzen kannst.',

      'band.excellent': 'Ausgezeichnet',
      'band.good': 'Gut',
      'band.fair': 'Mäßig',
      'band.poor': 'Vorsicht',
      'band.bad': 'Kritisch',

      'now.heading': 'Jetzt gerade',
      'now.conditions': 'Wetterlage',
      'now.temperature': 'Temperatur',
      'now.wetbulb': 'Feuchtkugeltemperatur',
      'now.dewpoint': 'Taupunkt',
      'now.humidity': 'Luftfeuchte',
      'now.wind': 'Wind',
      'now.gusts': 'Böen',
      'now.rain1h': 'Regen (letzte Stunde)',
      'now.pressure': 'Luftdruck',

      'hour.rain': 'Regen (diese Stunde)',
      'hour.rainChance': 'Regenwahrscheinlichkeit',
      'hour.close': 'Schließen',
      'hour.past': 'Diese Stunde ist bereits vorbei.',
      'hour.now': 'Jetzt gerade',
      'hour.at': 'Um {time}',
      'hour.backToNow': 'Balken erneut antippen für jetzt',

      'days.heading': 'Nächste Tage',
      'days.best': 'Beste Zeit',
      'days.worst': 'Schlechteste Zeit',
      'days.average': 'Tagesdurchschnitt',
      'days.scoreUnit': 'FSI-Punkte',
      'days.partial': 'Erst {n} Std. Vorhersage verfügbar.',
      'days.noData': 'Keine Daten',

      'warnings.more': '+{n} weitere',
      'warnings.advance': 'VORABINFORMATION',
      'warnings.advanceNote': 'Vorabinformation: mögliches Unwetter, noch keine amtliche Warnung.',
      'radar.heading': 'Regenradar',
      'radar.showWarnings': 'Warngebiete anzeigen',
      'radar.updated': 'Radar aktualisiert',

      'model.heading': 'Modellkarte des ICON (DWD)',
      'model.clouds': 'Bewölkung',
      'model.temperature': 'Temperatur',
      'model.wind': 'Wind',
      'model.loading': 'Modellebene wird geladen…',
      'model.unavailable': 'Modellebene derzeit nicht verfügbar.',
      'model.run': 'Modelllauf',
      'model.step': 'Vorhersagestunde',
      'model.now': 'jetzt',
      'model.hoursAhead': '{n} Std. nach dem Modelllauf',
      'model.play': 'Vorhersagestunden abspielen',
      'model.pause': 'Pause',
      'model.rain': 'Regen',
      'model.windNote': 'Pfeile zeigen die Windrichtung.',
      'model.pollen': 'Pollen',
      'model.daysAhead': '{n} Tage nach dem Modelllauf',
      'model.today': 'heute',
      'model.stepDay': 'Vorhersagetag',

      'pollen.label': 'Allergie',
      'pollen.none': 'Keine',
      'pollen.hazel': 'Hasel',
      'pollen.alder': 'Erle',
      'pollen.birch': 'Birke',
      'pollen.grasses': 'Gräser',
      'pollen.ragweed': 'Ambrosia',
      'pollen.offSeason': 'außerhalb der Saison',
      'pollen.notInSeason':
        '{species} hat gerade keine Saison. Der DWD veröffentlicht sie vom {start} bis {end}.',
      'pollen.pick': 'Wähle oben eine Allergie, um die Vorhersage hier zu sehen.',
      'pollen.level.low': 'Gering',
      'pollen.level.moderate': 'Mäßig',
      'pollen.level.high': 'Hoch',
      'pollen.level.very_high': 'Sehr hoch',
      'pollen.source': 'ICON-ART Tagesmittel, DWD.',
      'pollen.caveat':
        'Lediglich Forschungsdaten. Der DWD weist darauf hin, dass sie für klinische Zwecke nicht geeignet sind. Die Stufen gering/hoch stammen von dieser Seite.',
      'footer.updated': 'Aktualisiert',
      'footer.mosmixRun': 'MOSMIX-Lauf',
      'footer.data': 'Wetterdaten',
      'footer.mapData': 'Kartendaten',
      'footer.display': 'ConOps-Anzeige',
      'footer.api': 'Wetter-API',
      'footer.disclaimer':
        'Offizielle Eurofurence-Seite. Befolge stets die amtlichen DWD-Warnungen, und für Ansagen der Convention den offiziellen Telegram-Kanal:',
      'footer.notifications': 'Eurofurence Notifications',
      'footer.builtBy': 'Gebaut von',
      'footer.source': 'github',
      'footer.units': 'Einheiten',
      'footer.clock': 'Uhrzeit',
      'footer.privacy': 'Datenschutz',
      'notice.text':
        'Keine Werbung, keine Analyse, keine Tracking-Cookies.',
      'notice.ok': 'Verstanden',
      'notice.details': 'Was gespeichert wird',
      'lang.label': 'Sprache',
      'display.allClear': 'Keine aktiven Warnungen',
      'display.warnings': 'Aktive DWD-Warnungen',
      'display.next18': 'Nächste 18 Stunden',
    },
  };

  const LANG_KEY = 'efw.lang';
  const UNIT_KEY = 'efw.unit';
  const CLOCK_KEY = 'efw.clock';
  const ALLERGY_KEY = 'efw.allergy';
  const NOTICE_KEY = 'efw.noticeSeen';

  /* The species DWD publishes a pollen forecast for. '' is "none", which is the
     default: most visitors have no hay fever and should not be shown a pollen
     map they never asked for. */
  const ALLERGIES = ['hazel', 'alder', 'birch', 'grasses', 'ragweed'];

  const params = new URLSearchParams(location.search);

  /* Set by a page that must not follow the stored preference -- the ConOps
     board is read by international staff and stays English. */
  let forced = null;

  function force(lang) {
    if (STRINGS[lang]) forced = lang;
  }

  function getLang() {
    if (forced) return forced;
    // ?lang= wins, so a link can pin the language for info screens and sharing.
    const asked = params.get('lang');
    if (asked && STRINGS[asked]) return asked;
    const stored = localStorage.getItem(LANG_KEY);
    if (stored && STRINGS[stored]) return stored;
    // First visit: follow the browser, since a German visitor is likely local.
    return (navigator.language || 'en').toLowerCase().startsWith('de') ? 'de' : 'en';
  }

  function setLang(lang) {
    if (STRINGS[lang]) localStorage.setItem(LANG_KEY, lang);
  }

  function getUnit() {
    const asked = (params.get('units') || '').toUpperCase();
    if (asked === 'F' || asked === 'C') return asked;
    return localStorage.getItem(UNIT_KEY) === 'F' ? 'F' : 'C';
  }

  function setUnit(unit) {
    localStorage.setItem(UNIT_KEY, unit === 'F' ? 'F' : 'C');
  }

  /* Both site languages are 24-hour by convention, so that is the default; the
     switch exists for the visitors who read a clock the other way. */
  function getClock() {
    const asked = params.get('clock');
    if (asked === '12' || asked === '24') return asked;
    return localStorage.getItem(CLOCK_KEY) === '12' ? '12' : '24';
  }

  function setClock(clock) {
    localStorage.setItem(CLOCK_KEY, clock === '12' ? '12' : '24');
  }

  /* Which pollen the visitor cares about, or '' for none. Pinnable with
     ?allergy= like the other preferences, so a link can open on it. */
  function getAllergy() {
    const asked = (params.get('allergy') || '').toLowerCase();
    if (ALLERGIES.includes(asked)) return asked;
    if (asked === 'none') return '';
    const stored = localStorage.getItem(ALLERGY_KEY);
    return ALLERGIES.includes(stored) ? stored : '';
  }

  function setAllergy(allergy) {
    if (ALLERGIES.includes(allergy)) localStorage.setItem(ALLERGY_KEY, allergy);
    else localStorage.removeItem(ALLERGY_KEY); // "none" is the absence of a setting

    // ?allergy= wins over storage, so a link can open on a species -- but once
    // the reader works the control themselves, a stale pin in the address bar
    // must not keep overriding them. Drop it, and the URL stops describing a
    // page that is no longer on screen.
    if (params.has('allergy')) {
      params.delete('allergy');
      const query = params.toString();
      history.replaceState(null, '', `${location.pathname}${query ? `?${query}` : ''}`);
    }
  }

  /* The storage notice, dismissed once and then gone. Keeping that answer is
     itself a write to the device -- the alternative is showing the same box on
     every visit, which serves nobody. Everything here is a setting the visitor
     asked for; there is nothing to consent to, so the notice informs rather
     than asks. See /privacy. */
  function noticeSeen() {
    try {
      return localStorage.getItem(NOTICE_KEY) === '1';
    } catch (error) {
      // Storage blocked or full: show the notice rather than crash the page.
      return false;
    }
  }

  function setNoticeSeen() {
    try {
      localStorage.setItem(NOTICE_KEY, '1');
    } catch (error) {
      /* Nothing to do -- it will simply appear again next time. */
    }
  }

  /** Time-of-day options honouring the clock preference, plus anything extra. */
  function clockOptions(extra) {
    const half = getClock() === '12';
    return {
      // "09:00 PM" reads as a mistake; the 12-hour clock drops the padding.
      hour: half ? 'numeric' : '2-digit',
      minute: '2-digit',
      hour12: half,
      ...extra,
    };
  }

  /** A time of day, e.g. "21:00" or "9:00 pm". */
  function time(value, extra) {
    return new Date(value).toLocaleTimeString(locale(), clockOptions(extra));
  }

  /** A date and a time, for the footer and the model card. */
  function dateTime(value, extra) {
    return new Date(value).toLocaleString(locale(), clockOptions(extra));
  }

  /** A calendar date with no time of day.
      For a figure that covers a whole day -- the pollen forecast is a daily
      mean -- an hour on the label would be an invention, and "2 Aug, 02:00"
      reads as a measurement taken at two in the morning. */
  function dateOnly(value, extra) {
    return new Date(value).toLocaleDateString(locale(), {
      day: 'numeric',
      month: 'short',
      ...extra,
    });
  }

  /** Parse a bare YYYY-MM-DD as local noon.
      `new Date('2026-08-02')` is UTC midnight, which is still 1 August for any
      reader west of Greenwich -- the whole label would name the wrong day.
      Noon is far enough from either edge that no timezone or DST jump can move
      the date. */
  function dayStart(iso) {
    return typeof iso === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(iso)
      ? new Date(`${iso}T12:00:00`)
      : new Date(iso);
  }

  function T(key, vars) {
    const table = STRINGS[getLang()] || STRINGS.en;
    let value = table[key] ?? STRINGS.en[key] ?? key;
    if (vars) for (const [k, v] of Object.entries(vars)) value = value.replace(`{${k}}`, v);
    return value;
  }

  /** Convert a Celsius value for display, honouring the unit preference. */
  function temp(celsius, digits = 1) {
    if (celsius === null || celsius === undefined) return '–';
    const value = getUnit() === 'F' ? celsius * 1.8 + 32 : celsius;
    return `${value.toFixed(digits)} °${getUnit()}`;
  }

  /** Same, but without a space -- for compact places like the day rows. */
  function tempShort(celsius) {
    if (celsius === null || celsius === undefined) return '–';
    const value = getUnit() === 'F' ? celsius * 1.8 + 32 : celsius;
    return `${Math.round(value)}°`;
  }

  /** Replace the text of every element carrying data-i18n. */
  function apply(root = document) {
    for (const el of root.querySelectorAll('[data-i18n]')) {
      el.textContent = T(el.dataset.i18n);
    }
    document.documentElement.lang = getLang();
  }

  const locale = () => (getLang() === 'de' ? 'de-DE' : 'en-GB');

  return {
    T,
    apply,
    force,
    getLang,
    setLang,
    getUnit,
    setUnit,
    getClock,
    setClock,
    getAllergy,
    setAllergy,
    ALLERGIES,
    noticeSeen,
    setNoticeSeen,
    temp,
    tempShort,
    time,
    dateOnly,
    dayStart,
    dateTime,
    locale,
  };
})();
