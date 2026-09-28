/*
 * Indian Standards recommendations for a procurement portal's specification field.
 *
 *   <script src="https://<engine web address>/widget/standards-widget.js"
 *           data-api="https://<engine API address>"
 *           data-key="<API key from Settings>"
 *           data-target="#item-specification"></script>
 *
 * As an official types a specification, the engine's top recommendations
 * appear under the field: IS number, title, the certification the law
 * requires, and a warning when an edition has been replaced. "Insert
 * citation" appends the citation, with its amendments, to the field.
 *
 * Plain JavaScript with no dependencies, so it drops into any portal page.
 * Everything the engine returns is written with textContent, never as HTML,
 * so nothing in a response can inject markup into the portal.
 */
(function () {
  'use strict';

  var script = document.currentScript;
  if (!script) return;

  var API = (script.getAttribute('data-api') || '').replace(/\/+$/, '');
  var KEY = script.getAttribute('data-key') || '';
  var TARGET = script.getAttribute('data-target') || 'textarea';
  var MIN_CHARS = 12;      // shorter text rarely names goods
  var PAUSE_MS = 700;      // one request per pause in typing, not per keystroke
  var SHOWN = 5;

  var CERT = {
    ISI: 'ISI mark required',
    CRS: 'BIS registration (CRS) required',
    'Scheme X': 'BIS certificate required',
    Hallmark: 'BIS hallmark required'
  };

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function certificationBadge(c) {
    if (!c) return null;
    if (c.mandatory) return el('span', 'sew-badge sew-must', CERT[c.scheme] || 'Certification required');
    if (c.status === 'deferred') return el('span', 'sew-badge sew-warn', 'Certification deferred');
    if (c.status === 'voluntary') return el('span', 'sew-badge', 'Hallmarking voluntary');
    if (c.status === 'related_listed') return el('span', 'sew-badge sew-warn', 'Check related certification');
    return null;
  }

  function injectStyles() {
    if (document.getElementById('sew-styles')) return;
    var style = el('style');
    style.id = 'sew-styles';
    style.textContent = [
      '.sew{font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:#1d1b20;',
      'border:1px solid #cac4d0;border-radius:12px;padding:12px 14px;margin:8px 0;background:#fff;max-width:100%;box-sizing:border-box}',
      '.sew-head{font-weight:600;margin-bottom:6px}',
      '.sew-note{font-size:12px;color:#49454f;margin:4px 0 8px}',
      '.sew-warnnote{background:#fff4d6;border-radius:8px;padding:6px 8px}',
      '.sew-item{border-top:1px solid #e7e0ec;padding:8px 0;display:flex;gap:10px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap}',
      '.sew-item:first-of-type{border-top:0}',
      '.sew-main{min-width:0;flex:1 1 240px}',
      '.sew-num{font-family:ui-monospace,Consolas,monospace;font-weight:600}',
      '.sew-title{display:block;color:#322f37;overflow-wrap:anywhere}',
      '.sew-badges{display:flex;gap:6px;flex-wrap:wrap;margin-top:4px}',
      '.sew-badge{font-size:11px;border-radius:999px;padding:2px 8px;background:#ece6f0;color:#322f37}',
      '.sew-must{background:#e8def8;color:#21005d}',
      '.sew-warn{background:#fff4d6;color:#5c4400}',
      '.sew-btn{font:inherit;font-size:12px;border:1px solid #79747e;background:#fff;color:#1d1b20;border-radius:999px;padding:4px 10px;cursor:pointer}',
      '.sew-btn:hover{background:#f3edf7}',
      '.sew-foot{font-size:11px;color:#625b71;margin-top:6px}'
    ].join('');
    document.head.appendChild(style);
  }

  function mount(field) {
    var panel = el('div', 'sew');
    panel.setAttribute('role', 'region');
    panel.setAttribute('aria-live', 'polite');
    panel.setAttribute('aria-label', 'Indian Standards for this specification');
    panel.hidden = true;
    field.insertAdjacentElement('afterend', panel);

    var timer = null;
    var controller = null;
    var lastQuery = '';

    function insertCitation(text) {
      var sep = field.value && !/\s$/.test(field.value) ? '\n' : '';
      field.value = field.value + sep + text;
      field.dispatchEvent(new Event('change', { bubbles: true }));
      field.focus();
    }

    function render(state) {
      panel.hidden = false;
      panel.textContent = '';
      panel.appendChild(el('div', 'sew-head', 'Indian Standards for this specification'));
      if (state.loading) {
        panel.appendChild(el('div', 'sew-note', 'Finding the standards...'));
        return;
      }
      if (state.error) {
        panel.appendChild(el('div', 'sew-note sew-warnnote', 'The standards engine could not be reached: ' + state.error));
        return;
      }
      var data = state.data;
      if (data.confidence === 'none') {
        panel.appendChild(el('div', 'sew-note sew-warnnote',
          'No close match in the catalogue. These are the nearest text matches, not recommendations.'));
      } else if (data.confidence === 'uncertain') {
        panel.appendChild(el('div', 'sew-note sew-warnnote', 'Loosely related matches: check before citing.'));
      }
      (data.bis_products || []).slice(0, 2).forEach(function (p) {
        if (p.status === 'voluntary') return;
        panel.appendChild(el('div', 'sew-note',
          'BIS lists "' + p.product + '" under compulsory certification (' + p.scheme + ', ' + p.is_number + ')' +
          (p.status === 'deferred' ? ', enforcement deferred.' : '.')));
      });
      (data.results || []).slice(0, SHOWN).forEach(function (r) {
        var item = el('div', 'sew-item');
        var main = el('div', 'sew-main');
        main.appendChild(el('span', 'sew-num', r.number));
        main.appendChild(el('span', 'sew-title', r.title));
        var badges = el('div', 'sew-badges');
        var cert = certificationBadge(r.certification);
        if (cert) badges.appendChild(cert);
        if (r.replaced_by) badges.appendChild(el('span', 'sew-badge sew-warn', 'Replaced by ' + r.replaced_by));
        else if (r.withdrawn) badges.appendChild(el('span', 'sew-badge sew-warn', 'Withdrawn by BIS'));
        if (badges.childNodes.length) main.appendChild(badges);
        item.appendChild(main);
        var button = el('button', 'sew-btn', 'Insert citation');
        button.type = 'button';
        // A replaced edition is cited by the edition in force, not by itself.
        var citation = r.replaced_by ? r.replaced_by : (r.citation || r.number);
        button.setAttribute('aria-label', 'Insert citation ' + citation);
        button.addEventListener('click', function () { insertCitation(citation); });
        item.appendChild(button);
        panel.appendChild(item);
      });
      panel.appendChild(el('div', 'sew-foot',
        'From BIS records via the standards engine. Check the standard and the order before issuing a tender.'));
    }

    function run() {
      var query = field.value.trim();
      if (query.length < MIN_CHARS || query === lastQuery) return;
      lastQuery = query;
      if (controller) controller.abort();
      controller = typeof AbortController === 'function' ? new AbortController() : null;
      render({ loading: true });
      fetch(API + '/retrieve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': KEY },
        body: JSON.stringify({ query: query.slice(0, 4000), top_k: SHOWN }),
        signal: controller ? controller.signal : undefined
      })
        .then(function (res) {
          return res.json().catch(function () { return {}; }).then(function (body) {
            if (!res.ok) throw new Error(body.detail || ('HTTP ' + res.status));
            return body;
          });
        })
        .then(function (body) { render({ data: body }); })
        .catch(function (err) {
          if (err && err.name === 'AbortError') return;
          render({ error: err && err.message ? err.message : 'unknown error' });
        });
    }

    field.addEventListener('input', function () {
      clearTimeout(timer);
      timer = setTimeout(run, PAUSE_MS);
    });
  }

  function init() {
    if (!API || !KEY) {
      if (window.console) console.warn('standards-widget: data-api and data-key are required.');
      return;
    }
    injectStyles();
    Array.prototype.forEach.call(document.querySelectorAll(TARGET), function (field) {
      if (!field.getAttribute('data-sew-mounted')) {
        field.setAttribute('data-sew-mounted', 'true');
        mount(field);
      }
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
