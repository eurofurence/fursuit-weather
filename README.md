# 🦊 Eurofurence 30: Fantastic Furry Festival — Weather

A small self-hosted website that answers one question for convention attendees:
**can I go outside in suit right now?**

It pulls live data straight from [DWD OpenData](https://opendata.dwd.de) (the German
national weather service) and shows three things:

- **Fursuiting Index** — a 0–10 score for how comfortable and safe suiting is, with one
  bar per hour and a weather icon above each so you can see how the day builds.
  **Click any bar** for the conditions behind it
- **Weather overview and warnings** — current conditions, official DWD warnings, and a
  five-day outlook where **every day gets its own hour-by-hour chart** plus its best and
  worst hour, because during the con every hour matters
- **Rain radar** — the DWD radar composite on an interactive dark map
- **Model maps** — ICON-D2 decoded straight from DWD's GRIB2 files: cloud cover with
  the rain rate painted on top, 2 m temperature, and 10 m wind with direction arrows.
  One button per forecast hour out to +48, or press play and watch them run
- **Pollen** — pick your allergy and the model card grows a tab for it: the DWD ICON-ART
  forecast for hazel, alder, birch, grasses or ragweed, six days ahead
- **Works offline** — the page and the last forecast are cached, so it still opens
  on a congested convention network and says how old the numbers are
- **ConOps display** at `/display` — a full-screen board for the info desk
- **Public API** at `/api/v1` — versioned, documented, open (see [API](#api))

Available in **English and German**, with **°C or °F** and a **24- or 12-hour clock**.
All persist, and all can be pinned in a link: `?lang=de&units=F&clock=12&allergy=birch`.

Runs as a single Docker container. No API keys, no accounts, no database.

## The ConOps display

`/display` is a self-refreshing board sized for a screen at the ConOps desk. It shows the
current index, the next 24 hours and current conditions, with no chrome and no scrollbar.
Warnings are marked directly on the hourly bars rather than in a tile of their own. Open it fullscreen (F11) and leave it.

Clicking a bar switches the conditions strip to that hour, which is handy at the desk when
someone asks about tonight. It says so in the heading and goes back to live conditions by
itself after 90 seconds, so an unattended board never sits on a forecast.

It is **always English**, whatever language a visitor picked on the public site — staff on
shift are international. The score tile takes the colour of the band it is reporting, and
the best and worst stretches are marked **on the bars themselves** rather than in panels
of their own. Times are shown as 24-hour local clock with the am/pm reading alongside
(`14:00 (2 PM)`), and the clock ticks in seconds so a frozen board is obvious at a glance.

It fits a 1080p landscape screen exactly and falls back to a single column on portrait or
tablet displays. If DWD becomes unreachable it keeps the last good screen up and says so
in the footer rather than blanking — a desk display going blank is worse than one that is
five minutes stale.

---

## Quick start

```bash
docker compose up -d
```

Open <http://localhost:8000>.

Without Docker:

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### If the build hangs pulling `python:3.12-slim`

This is not the project — it is Docker Hub's CDN
(`production.cloudfront.docker.com`), which on some networks runs at a crawl over
IPv4 and returns nothing at all over IPv6. The build sits on
`[1/8] FROM docker.io/library/python:3.12-slim` with layers frozen at `0B` or
inching along at ~1 MB per 40 s.

Pull the identical image from a mirror instead:

```bash
# one-off
EFW_BASE_IMAGE=mirror.gcr.io/library/python:3.12-slim docker compose up -d --build

# or persist it
echo "EFW_BASE_IMAGE=mirror.gcr.io/library/python:3.12-slim" >> .env
docker compose up -d --build
```

On Windows PowerShell:

```powershell
$env:EFW_BASE_IMAGE = "mirror.gcr.io/library/python:3.12-slim"
docker compose up -d --build
```

To fix it for *every* image rather than just this one, point the Docker daemon at
the mirror — Linux `/etc/docker/daemon.json`, or Docker Desktop →
Settings → Docker Engine:

```json
{ "registry-mirrors": ["https://mirror.gcr.io"] }
```

then restart Docker (`sudo systemctl restart docker`, or Restart from Docker
Desktop).

To confirm the diagnosis on your own machine, compare throughput:

```bash
curl -sw '%{speed_download} B/s\n' -o /dev/null -r 0-5000000 \
  https://github.com/git-for-windows/git/releases/download/v2.43.0.windows.1/Git-2.43.0-64-bit.exe
```

A healthy connection there plus a stalled Docker pull confirms it is the Hub CDN.

> The `pull access denied for eurofurence-weather` line at the start is harmless.
> Compose looks for a published image before falling back to building locally;
> `pull_policy: build` in `docker-compose.yml` now suppresses it.

---

## Data sources

Everything comes from DWD, which publishes free of charge under the
[GeoNutzV](https://www.dwd.de/DE/service/copyright/copyright_node.html) terms
(attribution required — the footer does this).

| Source | What it provides | Updates |
|---|---|---|
| [MOSMIX_L](https://opendata.dwd.de/weather/local_forecasts/mos/MOSMIX_L/single_stations/) | Hourly point forecast, ~10 days, per station | 4×/day |
| [POI reports](https://opendata.dwd.de/weather/weather_reports/poi/) | Surface observations, current plus the last ~24 h | hourly |
| [WarnWetter](https://www.dwd.de/DWD/warnungen/warnapp/json/warnings.json) | Official warnings per Warncell | ~every few minutes |
| [maps.dwd.de GeoServer](https://maps.dwd.de/geoserver/dwd/wms) | Radar composite + warning areas (WMS) | every 5 min |
| [ICON-D2 GRIB2](https://opendata.dwd.de/weather/nwp/icon-d2/grib/) | Cloud cover, temperature, wind on a 2 km grid | every 3 h |
| [ICON-ART pollen NetCDF](https://opendata.dwd.de/climate_environment/health/forecasts/pollen/) | Daily mean pollen concentration, 6 days, ~6.5 km grid — **in season only** | daily, ~03:35 UTC |

Defaults are station **10147** (Hamburg-Fuhlsbüttel) and Warncell **102000000**
(Hansestadt Hamburg).

---

## Design

The site uses the festival palette, and is dark by design rather than following the
system theme — the palette is a dark one, so a light variant would not be the same brand.

| Role | Colour |
|---|---|
| Page background | Blue Black `#1A2039` |
| Panels | Midnight Teal `#222B54` |
| Text | Cool Indigo `#E7E9F2` |
| Event wordmark, alerts | Hot Pink `#F13CA3` |
| Links, active controls | Electric Cyan `#B3FFFF` |

Two deliberate departures from the raw palette:

- **Cool Slate `#4F6374` is not used for body text.** On Midnight Teal it lands near
  2:1 contrast, which is unreadable. Muted text mixes it toward Cool Indigo instead, so
  the hue survives but the text does not.
- **The index scale is not purely brand.** It runs `#40AD3E` → `#7CC243` →
  Festival Amber `#FFD633` → `#FF8A3D` → Hot Pink `#F13CA3`, because a
  green-to-alarm ramp has to stay readable as a *scale*. Official DWD warning colours
  (yellow/orange/red/violet) are left exactly as DWD defines them — those are
  standardised severity levels, not decoration.

The index colours live in one place, [`app/fsi.py`](app/fsi.py), and are published on
`/api/summary` as `bands` so the frontend never keeps a copy that can drift.

---

## The Fursuiting Index

The index rates suiting conditions from 0 (stay out of suit) to 10 (perfect). Four
weighted sub-scores feed it:

| Factor | Weight | Why it matters |
|---|---|---|
| Temperature | 50 % | **Wet-bulb temperature** plus a sun load. A suit blocks the sweat evaporation your body relies on, so this dominates. |
| Rain | 30 % | Rain rate blended with probability, plus a penalty for ground still wet from the last 24 h. |
| Wind | 12 % | U-shaped: dead calm turns a suit into an oven, a gale takes the head off. Best around 1–3 m/s. |
| Humidity | 8 % | Dew point — how clammy the air feels once you stop moving. |

**Heat ceilings** then cap the result rather than being averaged into it, so a good
sub-score can never mask a hazard: effective wet-bulb ≥ 24 °C caps the index at 3, ≥ 27 °C
caps it at 1. Without this, "it isn't raining" (10/10) would drag a dangerously hot hour up
into the middle of the scale.

**Official DWD warnings do not affect the score.** They are reported next to it and left
for the reader to weigh. A warning covers a whole region for hours at a time, so capping on
it flattened exactly the hour-by-hour detail the bars exist to show — and the hazards that
matter for suiting (heat, rain, wind) are already in the sub-scores, measured at the hour.

Warnings are shown **on the hourly bars**, over the hours they cover. A
*Vorabinformation* — DWD flagging possible severe weather before it is certain enough to
warn on — is drawn with **red diagonal hatching** so it is never mistaken for a warning in
force. On the public site the wording collapses to a single line that expands on click;
the board shows the marks only.

Overlapping warnings are packed into as few rows as they need, and the chart reserves
exactly that much space — the row count is handed to the stylesheet, so a fourth warning
grows the panel instead of landing across the bars. A band too narrow to hold its wording
(a one-hour warning is a sliver of a 24-hour chart) keeps the marker and moves its label
out to whichever side has room.

### Reading the bars

The forecast **keeps the hours of today that have already gone by**. They stay on the
chart drawn grey, with a **red line at the current minute**, so a day card is a whole day
rather than a stub by the evening. How far back that reaches depends on the MOSMIX run,
which begins at its issue time. Anything that answers *what next* — the best and worst
stretches, a day's best hour — skips them.

**Clicking any bar** opens the conditions behind that hour: weather, temperature, wet-bulb,
humidity, wind, gusts, rain and the chance of it. Every scored hour carries those, so it
works on the five-day cards too, not just the next 24 hours. On the board the conditions
strip switches to that hour and returns to live data on its own after 90 seconds.

All weights, thresholds and caps live in [`config.json`](config.json) — tune them without
touching code.

The score is reported to **one decimal**. That matters beyond precision: it is what makes
the two easter eggs in [`app/fsi.py`](app/fsi.py) reachable at all. A score of exactly
**6.9** appends "Nice." to the advice; exactly **6.7** shows `media/ravi_67.mp4` in a
panel. Both are cosmetic — neither moves the score, its band or its colour.

> The index is guidance from a community project, not a safety system. Always follow
> official DWD warnings and convention staff.

---

## Model maps, without eccodes

DWD publishes ICON-D2 as GRIB2. The usual way to read that is `eccodes`, which would
dominate the image size — awkward given how slow Docker Hub already is on some networks.

The `regular-lat-lon` products we need use only **grid template 3.0** (plain
latitude/longitude) and **data template 5.0** (simple packing), so
[`app/dwd/grib2.py`](app/dwd/grib2.py) implements exactly that in ~150 lines of
NumPy. Values are `(R + X · 2^E) / 10^D`, with a bitmap marking points outside the
domain. If DWD ever switches these products to another packing, the reader raises
`UnsupportedGrib` rather than returning silently wrong numbers.

Fields are cropped to the area around the venue, painted with an **absolute** colour ramp
(so a colour means the same thing at every forecast hour) and served as a PNG that the
frontend drapes over the map. The crop is cut to the map's wide aspect, and the map uses
fractional zoom, so the field fills the frame instead of floating inside it.

Each field is drawn in **steps**, not a smooth ramp — clouds in eighths, temperature every
2 °C, wind every 5 km/h — and `/api/model` publishes those same steps as `bands`, which is
what the legend is built from. A colour on the map is therefore always one the key names.
The numbers are resampled first and coloured second: colouring the 2 km grid first would
leave visible blocks, and smoothing the finished image would blend neighbouring bands into
shades that are in no step at all.

Per layer:

- **Clouds** carry the instantaneous rain rate (`prr_gsp`) on top, on a square-root scale
  — drizzle and downpour differ by orders of magnitude, and a linear ramp shows nothing
  until it is already pouring. Cloud opacity is capped so the coastline stays visible, and
  a genuinely clear sky (0/8) is drawn as nothing at all.
- **Wind** draws direction arrows pointing downwind. It used to carry speed isolines as
  well; with the fill itself now in 5 km/h steps they marked the same boundaries a second
  time, in white, over the arrows.

---

## Pollen, for the hay-fever half of the fandom

Pick an allergy beside the language buttons and the model card grows a fourth tab: the DWD
**ICON-ART** pollen forecast for that species. Five are published — hazel (`CORY`), alder
(`ALNU`), birch (`BETU`), grasses (`POAC`) and ragweed (`AMBR`) — as daily mean
concentrations in grains/m³, six days ahead on a ~6.5 km grid over Germany.

Three things about this source drive the design:

- **It is NetCDF, not GRIB.** Same reasoning as above: the files are NetCDF-3 classic, a
  fixed documented layout, so [`app/dwd/netcdf.py`](app/dwd/netcdf.py) reads them in ~100
  lines rather than pulling in the HDF5 C library. The one real subtlety is that variables
  along the unlimited dimension are stored *interleaved* — one slice of each per record —
  so stepping through days means striding by the record size, not walking one array.
  Read as if contiguous, every day after the first is a convincing mixture of the timestamp
  and the wrong day's grid.
- **A species only exists during its own season.** Out of season DWD publishes no file, so
  birch in August is a 404 by design. The seasons ship with the dataset, so they are in the
  code: the picker still lists every species, marked "out of season", and the card says
  *"DWD publishes it from 30 January to 10 June"* instead of failing to load a map.
- **The grid is Germany only** — narrower than the map the card draws. `pollen.map_bounds`
  clamps the window to the published domain and snaps it to grid cell centres, and the
  overlay is hung on *that* rectangle. Draped over the window that was asked for, the
  field would be stretched sideways across the coastline.

The four levels (low / moderate / high / very high) are **this site's own** and are
configurable per species, because DWD publishes concentrations and not severity. They are
per species on purpose: ragweed provokes symptoms an order of magnitude below the
concentrations that matter for birch, so one shared scale would either cry wolf about grass
or say nothing at all about ragweed. DWD's own note is repeated under the map — this is
research output and is not suitable for clinical use.

---

## Configuration

Edit `config.json`, or override the common values with environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `EFW_EVENT_NAME` | `Eurofurence 30: Fantastic Furry Festival` | Shown as the wordmark |
| `EFW_STATION_ID` | `10147` | DWD station for observations and forecast |
| `EFW_WARNCELLS` | `102000000` | Comma-separated Warncell ids to watch |
| `EFW_LOCATION_NAME` | `Hamburg` | Name shown in the header |
| `EFW_FORECAST_HOURS` | `120` | Forecast horizon |
| `EFW_RATE_LIMIT` | `100` | API requests per minute per client |
| `EFW_BUSY_AT` | `40` | Visitors at once before the page says it is busy |
| `EFW_CROWDED_AT` | `80` | Visitors at once before it warns that loading will be slow |
| `EFW_CONFIG` | `config.json` | Path to an alternative config file |

To point the site at another city, look up its
[station id](https://www.dwd.de/DE/leistungen/klimadatendeutschland/statliste/statlex_html.html)
and [Warncell id](https://www.dwd.de/DE/leistungen/opendata/help/warnungen/cap_warncellids_csv.html),
then set both plus the coordinates in `config.json`.

The pollen layer has no environment overrides, because its one interesting setting is a
table. `pollen.enabled: false` drops the picker and the map entirely; `pollen.thresholds`
sets the `[moderate, high, very high]` edges in grains/m³ per species. Anything left out
falls back to the defaults in [`app/dwd/pollen.py`](app/dwd/pollen.py). Note that the
pollen grid covers **Germany only** — the layer has nothing to show for a location
outside 47.2–56.2 °N, 5.6–15.1 °E.

---

## API

There is a public, versioned API. **Build against `/api/v1`** — those shapes are a
stable contract. Interactive docs at **`/docs`**, schema at `/openapi.json`.

Open access, no key, **100 requests per minute** per client. Responses carry
`X-RateLimit-*`; please cache, since the upstream data only changes hourly.

A human-readable summary of all of this lives on the site itself at **`/api-docs`**.

| Endpoint | Returns | Size |
|---|---|---|
| `GET /api/v1/fsi` | Current index: score, band, advice, sub-scores | ~1 kB |
| `GET /api/v1/current` | Latest station observation | ~0.7 kB |
| `GET /api/v1/forecast?hours=24` | Hourly forecast with the index per hour | ~7 kB |
| `GET /api/v1/daily` | Per-day summary with best and worst hour | ~3 kB |
| `GET /api/v1/warnings` | Active DWD warnings and advance notices | ~2 kB |
| `GET /api/v1/scale` | The index scale and its colours | ~0.6 kB |
| `GET /api/v1/overview` | All of the above in one call | ~15 kB |
| `GET /api/load` | How busy the site is right now | tiny |
| `GET /api/health` | Liveness plus cache ages | tiny |

All accept `?lang=en|de`. Every response includes a `meta` block with the event,
location, station, timestamp and attribution.

```bash
# just the number, for a bot or a status page
curl -s localhost:8000/api/v1/fsi | jq '{score, band, advice}'

# when is it worth going out today? best_window is the stretch around best_hour
curl -s localhost:8000/api/v1/daily | jq '.days[0] | {date, fsi_max, best_hour, best_window}'

# any warnings, and is it only an advance notice?
curl -s localhost:8000/api/v1/warnings | jq '.warnings[] | {label, advance, start, end}'
```

Field names carry their unit (`temperature_c`, `wind_speed_kmh`) so nothing has to be
guessed, and `band_key` stays stable across languages — switch on that, not on the
translated `band`.

**Images** (not versioned, but stable in practice):

| Endpoint | Returns |
|---|---|
| `GET /api/radar.png` | Radar composite (`?span=`, `?width=`, `?height=`, `?layer=radar\|warnings`) |
| `GET /api/model` | Available ICON fields, colour ramps, current run — plus a `pollen` block with the five species, their seasons and bands |
| `GET /api/model.png` | One ICON field as a map overlay (`?param=clouds\|temperature\|wind`, `?step=0..48`) |
| `GET /api/pollen.png` | One pollen species as a map overlay (`?species=hazel\|alder\|birch\|grasses\|ragweed`, `?step=0..5` in **days**). 404 when that species is out of season |

`GET /api/summary` also exists and is what this project's own frontend uses. It is
**not** a contract — its shape follows whatever the site needs. Do not build on it.

Every endpoint degrades rather than failing: if one upstream source is unreachable the
response still carries the rest and names what is missing in `meta.degraded`. Each source
is cached, and a failed refresh falls back to the last good value.

Rate limiting is an in-process sliding window, so with several uvicorn workers the
effective limit is the configured value times the worker count. For a single container
that is exactly right; behind a load balancer, enforce limits there. Tune with
`EFW_RATE_LIMIT` or `api.rate_limit_per_minute`, or set `api.public_api_enabled: false`
to serve only the pages.

---

## When the site gets busy

This runs on one machine at home, so a rush is a real state it can reach — and a
slow page with no explanation just looks broken. The site counts how many people
are on it and says so:

- **40 at once** → a quiet amber line: *busy, pages may take a moment*.
- **80 at once** → *very busy, loading will be slow* — still working, be patient.

Both numbers are guesses until you have watched a real rush. `GET /api/load`
reports what the machine is actually carrying, so tune against that rather than
against a feeling:

```bash
curl -s localhost:8000/api/load
{"visitors":37,"level":"normal","in_flight_requests":2,"window_seconds":360,
 "busy_at":40,"crowded_at":80,"peak_visitors":112}
```

`peak_visitors` is the high-water mark since the process started — the single
most useful number for setting the thresholds after the fact. In-flight requests
are the better distress signal of the two: visitors say how many people are
around, in-flight says how much the machine is doing about it.

Every `/api/` response carries `X-Site-Load` and `X-Site-Visitors`, which is how
the page knows without spending a request of its own. Set `capacity.enabled:
false` to switch the whole thing off.

**How the counting works, and why there is no cookie.** A visitor is a salted
hash of the client address, held in memory for six minutes. The salt is random
per process, so the values cannot be linked across a restart or turned back into
an address; nothing is written to the visitor's device and nothing reaches disk.
Same in-process scope as the rate limiter: with several workers the count splits
across them, which is fine for a single container.

**Behind Cloudflare, the address comes from `CF-Connecting-IP`** — Cloudflare
writes that header itself, so a caller cannot forge it. `X-Forwarded-For` is only
the fallback for another proxy, and its first entry is *not* trustworthy:
Cloudflare and most proxies append to whatever the client sent, so trusting it
would hand a caller a fresh identity per request — past the rate limit, and
straight into the visitor count. Both the limiter and the counter use the same
key, so this is one decision in one place ([`app/ratelimit.py`](app/ratelimit.py)).

It is a load signal, not an audience metric. Everyone behind one shared network
counts once, and a crawler counts as a person — do not publish it as traffic.

**The offline copy is the other half of this.** Counting a rush and apologising for
it only manages the symptom; [`static/sw.js`](static/sw.js) removes the request.
A service worker keeps the shell and the last `/api/summary` in the browser cache,
so a page opened inside a convention centre — several thousand phones on the same
cell towers, one residential uplink at the far end — comes up with real numbers
instead of an error box, and costs the machine nothing.

It is **network-first throughout**, deliberately. The pages and their scripts are
versioned together, and serving a cached `app.js` beside a fresh `index.html` is
the exact breakage the `no-cache` headers in [`app/main.py`](app/main.py) exist to
prevent — so the network always gets first refusal and the cache is a fallback,
never a shortcut past a deploy. It gives up after 3.5 s, which is long enough that
a merely slow connection still wins.

Not everything is kept: `/api/load` is the live busy signal and is `no-store` by
design, and the radar, model and pollen images are large and short-lived — a stale
radar picture is worse than a missing one. When the payload on screen is more than
fifteen minutes old the page says so in the subtitle rather than passing old
numbers off as current.

---

## Cookies, storage and the privacy pages

The site sets **no cookies**. It keeps up to five values in local storage — language,
unit, clock, chosen allergy and "notice dismissed" — all of them settings the visitor
chose themselves. The allergy key is written only if one is picked, and removed again on
"None", so the default state stores nothing. It also keeps an **offline copy** of the
shell and the last weather payload in the browser cache (see below). There is no
analytics, no advertising and no third-party embed beyond the map tiles.

So visitors get a **notice, not a consent gate**: a dismissible bar explaining
what is kept, linking to the privacy page, with everything usable behind it.
Under TDDDG § 25 (2) a consent banner is for storage the visitor did not ask
for, and there is none here. Add analytics or an embedded player and that stops
being true — you would then need a real consent flow, and the notice text would
be a lie.

**`/privacy` and `/datenschutz`** are the same page in both site languages; the
footer and the notice link to whichever matches the current language. They spell
out what is stored on the device, what the server does with an address, and who
else sees the visitor's IP: **Cloudflare**, which carries the tunnel and
terminates TLS (and may set its own `__cf_bm` cookie — theirs, not ours), plus
the **CARTO** and **DWD** tile servers the browser fetches from directly.

**Request logging is off.** `--no-access-log` in the [Dockerfile](Dockerfile):
uvicorn's access line carries the caller's address, and the privacy page promises
no request log is kept. Nothing here needed one — `/api/load` answers "is it
busy" — and the rate limiter's "someone is hammering the API" line names the
hash, never the address, with a test holding that in place. What is left is
bounded by a `logging:` block in compose, since Docker's json-file driver never
rotates on its own.

> **If you fork this for another event:** the controller block at the foot of both
> privacy pages — legal name, postal address, email, as GDPR Art. 13 and DDG § 5
> require — is filled in for *this* instance and is the first thing you must
> replace. Wrap yours in `<p class="todo">` while it is unfinished: that class
> exists to draw it in loud pink, so a missing Impressum is impossible to ship
> without noticing.

---

## Development

```bash
pip install -r requirements-dev.txt
pytest                                   # 177 tests, no network required
uvicorn app.main:app --reload
```

Layout:

```text
app/
  main.py            FastAPI app, pages, image endpoints
  api_v1.py          the public, versioned API
  schemas.py         its response models
  ratelimit.py       per-client sliding window
  service.py         assembles the /api/summary payload
  fsi.py             the Fursuiting Index
  meteo.py           wet-bulb, dew point, Beaufort
  weather_codes.py   WMO ww codes -> English text + icon
  config.py          config.json + env overrides
  i18n.py            English/German strings for generated text
  models.py          shared dataclasses
  dwd/
    client.py        HTTP session + TTL cache with stale fallback
    mosmix.py        MOSMIX_L KMZ/KML forecast parser
    observations.py  POI observation CSV parser
    warnings.py      WarnWetter JSONP parser
    radar.py         GeoServer WMS helper
    grib2.py         minimal GRIB2 reader (templates 3.0 + 5.0)
    netcdf.py        minimal NetCDF-3 reader (classic + 64-bit offset)
    icon.py          ICON-D2 fields -> coloured map overlays
    pollen.py        ICON-ART pollen -> coloured map overlays, seasons, bands
media/               served at /media (the 6.7 easter egg lives here)
static/
  index.html         the main site
  app.js style.css
  display.html       the ConOps board
  display.js display.css
  chart.js           hourly bar rendering + contrast maths, shared by both pages
  i18n.js            UI strings; language, unit, clock and allergy preferences
  loading.js         the top progress bar and the per-map tile meters
  sw.js              service worker: offline copy of the shell and last payload
  vendor/            Leaflet, vendored so the container needs no CDN
legacy/              the previous CLI tool, kept for reference
```

The frontend is plain HTML/CSS/JS with no build step; Leaflet is vendored in
`static/vendor/` so the container needs no CDN.

## Licence

MIT — see [LICENSE](LICENSE). Weather data © Deutscher Wetterdienst.
