/* Loading feedback.

   Two separate things, because they answer two different questions:

   - one bar across the top of the page, for data the page is waiting on. It
     says "something is happening" while a fetch is out.
   - a meter over each map, for the tiles and overlays that map is still
     pulling. A map fills in piece by piece and can sit half-drawn for seconds,
     which looks broken rather than busy.

   Shared by the public page and the ConOps board. */

window.EFW_LOADING = (function () {
  /* The bar never sits at zero while work is in flight: a bar that has not
     moved reads as stuck, and the first request is the longest one. */
  const CRAWL = 12;
  const HOLD_MS = 280; // how long a finished bar stays full before it fades
  const FADE_MS = 260; // must outlast the CSS transition, or it snaps back

  let started = 0;
  let finished = 0;
  let clearTimer = null;

  function bar() {
    return document.getElementById('progress');
  }

  function paint() {
    const host = bar();
    if (!host) return;
    const fill = host.querySelector('.fill');
    if (!fill) return;

    const busy = finished < started;
    if (busy) {
      clearTimeout(clearTimer);
      host.hidden = false;
      host.classList.add('is-busy');
      fill.style.width = `${Math.max(CRAWL, (finished / started) * 92)}%`;
      return;
    }

    // Run to the end, hold it there long enough to be seen, then reset. Without
    // the pause a fast response is a flicker nobody can read.
    fill.style.width = '100%';
    host.classList.remove('is-busy');
    clearTimeout(clearTimer);
    clearTimer = setTimeout(() => {
      host.hidden = true;
      fill.style.width = '0%';
      started = 0;
      finished = 0;
    }, HOLD_MS + FADE_MS);
  }

  /** One unit of work has started. Always pair with settle(). */
  function begin() {
    started += 1;
    paint();
  }

  /** One unit of work has ended -- succeeded or failed, the bar cannot care. */
  function settle() {
    finished += 1;
    paint();
  }

  /** Run a promise with the bar up, whatever it does. */
  async function track(promise) {
    begin();
    try {
      return await promise;
    } finally {
      settle();
    }
  }

  /**
   * A meter drawn over one map.
   *
   * Counts pieces rather than guessing: every tile Leaflet starts is one more
   * to wait for, and each one that lands (or fails -- a missing tile still
   * stops being awaited) moves the bar along.
   */
  function meter(host) {
    if (!host) return null;

    const element = document.createElement('div');
    element.className = 'map-progress';
    element.hidden = true;
    const fill = document.createElement('span');
    fill.className = 'fill';
    element.append(fill);
    host.append(element);

    let total = 0;
    let done = 0;
    let timer = null;

    function render() {
      if (total === 0) return;
      if (done < total) {
        clearTimeout(timer);
        element.hidden = false;
        element.classList.add('is-busy');
        fill.style.width = `${Math.max(CRAWL, (done / total) * 100)}%`;
        return;
      }

      fill.style.width = '100%';
      element.classList.remove('is-busy');
      clearTimeout(timer);
      timer = setTimeout(() => {
        element.hidden = true;
        fill.style.width = '0%';
        // Reset per batch: panning the map starts a fresh set of tiles, and a
        // counter that only ever grew would make later batches look instant.
        total = 0;
        done = 0;
      }, HOLD_MS + FADE_MS);
    }

    const api = {
      expect(n = 1) {
        total += n;
        render();
      },
      settle(n = 1) {
        done = Math.min(total, done + n);
        render();
      },
      /** Whatever is outstanding is over -- Leaflet says the layer is done. */
      finish() {
        done = total;
        render();
      },
    };

    /** Follow a Leaflet tile layer's own events. */
    api.follow = (layer) => {
      layer.on('tileloadstart', () => api.expect());
      layer.on('tileload', () => api.settle());
      layer.on('tileerror', () => api.settle()); // a hole is still a resolved tile
      layer.on('load', () => api.finish());
      return api;
    };

    return api;
  }

  return { begin, settle, track, meter };
})();
