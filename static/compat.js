/* Feature detection for browsers older than the CSS this site is written in.
   Deliberately ES5: this is the one file that must run on anything.

   It sets classes on <html> and does nothing else. compat.css hangs every
   legacy fallback off those classes, so a current browser matches none of them
   and is completely unaffected -- and dropping support later is deleting two
   files and two <link>/<script> tags, not unpicking the stylesheets.

   Loaded from <head>, before the page is painted: a class arriving after first
   paint would show the broken layout and then correct it. */

(function () {
  'use strict';

  var root = document.documentElement;
  var flags = [];

  function mark(name) {
    flags.push(name);
    // classList exists everywhere we care about, but className is what works
    // on an SVG root and in genuinely ancient engines.
    root.className = root.className ? root.className + ' ' + name : name;
  }

  var supports =
    window.CSS && typeof window.CSS.supports === 'function'
      ? function (property, value) {
          try {
            return window.CSS.supports(property, value);
          } catch (error) {
            return false;
          }
        }
      : function () {
          return false;
        };

  /* color-mix() landed in Chrome 111. The palette leans on it for --muted and
     --border, so without a fallback the quiet greys resolve to nothing and the
     text they carry inherits full-strength white. */
  if (!supports('color', 'color-mix(in srgb, #fff 50%, #000)')) mark('no-color-mix');

  /* clamp() landed in Chrome 79. The ConOps board sizes almost every glyph
     with it, so on an older browser the type has no size of its own at all. */
  if (!supports('width', 'clamp(1px, 2px, 3px)')) mark('no-clamp');

  /* The `inset` shorthand landed in Chrome 87. Two fixed-position bars use it,
     and without it they have no position and land wherever they fall. */
  if (!supports('inset', '0')) mark('no-inset');

  /* :focus-visible landed in Chrome 86. An unparsable selector takes its whole
     rule with it, so keyboard focus rings simply vanish. */
  try {
    document.querySelector(':focus-visible');
  } catch (error) {
    mark('no-focus-visible');
  }

  /* gap on a flex container landed in Chrome 84 -- five years after it worked
     on grid, so CSS.supports('gap', '1px') answers yes on a browser where flex
     items still sit flush against each other. It has to be measured: two 10px
     items in a column with a 10px row-gap stack to 30px if the gap took and
     20px if it did not.

     Answers 'yes' | 'no' | 'unknown'. Anything but a clean 20 or 30 is a
     measurement we do not trust -- running this from <head> means there may be
     no <body> to measure inside yet -- and a wrong 'no' would apply the
     fallback margins on a current browser, doubling every gap on the page. */
  function flexGapSupport() {
    var probe = document.createElement('div');
    probe.style.cssText =
      'display:flex;flex-direction:column;row-gap:10px;position:absolute;' +
      'top:-9999px;left:-9999px;visibility:hidden;padding:0;border:0';
    for (var i = 0; i < 2; i++) {
      var child = document.createElement('div');
      child.style.cssText = 'height:10px;width:10px;flex:none;margin:0;padding:0;border:0';
      probe.appendChild(child);
    }

    var host = document.body || root;
    host.appendChild(probe);
    var height = probe.offsetHeight;
    host.removeChild(probe);

    if (height === 30) return 'yes';
    if (height === 20) return 'no';
    return 'unknown';
  }

  function checkFlexGap() {
    var answer;
    try {
      answer = flexGapSupport();
    } catch (error) {
      answer = 'unknown';
    }
    if (answer === 'no') mark('no-flex-gap');
    return answer;
  }

  // If <head> was too early to get a trustworthy measurement, take it again as
  // soon as there is a document to measure in.
  if (checkFlexGap() === 'unknown') {
    document.addEventListener('DOMContentLoaded', function () {
      checkFlexGap();
    });
  }

  // Reported once the last check has had its chance, so the list is complete.
  document.addEventListener('DOMContentLoaded', function () {
    if (flags.length && window.console && console.info) {
      console.info('EFW: legacy CSS fallbacks active -', flags.join(', '));
    }
  });
})();
