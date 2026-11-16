// The page of a comparison, before and after (scripts/sitebuild/beforeafter.py): sorts and
// filters the items that moved, shows more of them, and shows the results of the one chosen.
// The page holds the comparison as data; without this script it shows the first rows as they are.
'use strict';
(function () {
  var board = document.querySelector('[data-before-after]');
  if (!board) return;
  var D;
  try { D = JSON.parse(board.querySelector('[data-ba-data]').textContent); } catch (e) { return; }
  var STEP = 100;
  var q = function (sel) { return board.querySelector(sel); };
  var state = { filter: '', cause: '', group: '', sort: null, limit: STEP, chosen: null, list: [] };
  var threshold = D.threshold || 0;
  D.moved.forEach(function (item, i) { item.i = i; });

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
  function grouped(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ','); }
  function number(x) {
    if (x === null || x === undefined) return 'not stated';
    if (x === 0) return '0';
    var a = Math.abs(x);
    if (a < 0.001 || a >= 100000) {
      var parts = x.toExponential(2).split('e');
      return parts[0] + ' × 10<sup>' + parseInt(parts[1], 10) + '</sup>';
    }
    return a < 1000 ? String(parseFloat(x.toPrecision(3))) : grouped(Math.round(x));
  }
  function moved(b, a) {
    if (b === null || a === null) return false;
    var size = Math.max(Math.abs(b), Math.abs(a));
    return size > 0 && Math.abs(a - b) / size > threshold;
  }
  function ratio(b, a) {
    if (b === null || a === null || b === 0 || a === 0 || (b > 0) !== (a > 0)) return null;
    return a / b;
  }
  // how far a pair lies from no change: -1 without a pair, 0 unchanged, 2 without a ratio
  function distance(pair) {
    if (!pair || pair[0] === null || pair[1] === null) return -1;
    if (!moved(pair[0], pair[1])) return 0;
    var r = ratio(pair[0], pair[1]);
    return r === null ? 2 : Math.abs(Math.log10(r));
  }
  function percent(b, a) {
    if (b === null || b === 0 || a === null) return '';
    var change = (a - b) / Math.abs(b) * 100, size = Math.abs(change);
    return (change > 0 ? '+' : change < 0 ? '−' : '') + size.toFixed(size >= 10 ? 0 : size >= 1 ? 1 : 2) + ' %';
  }
  function cell(pair) {
    if (!pair || pair[0] === null || pair[1] === null) return '<td class="num ba-cell is-none"></td>';
    var r = ratio(pair[0], pair[1]);
    if (!moved(pair[0], pair[1])) {
      var same = r === null || number(r) === '1';
      return '<td class="num ba-cell is-same" title="' + (same ? 'No change' : 'Within the threshold') + '">' + (same ? '1' : number(r)) + '</td>';
    }
    if (r === null) return '<td class="num ba-cell is-opposite" title="Zero, or of the other sign, on one side: no ratio">–</td>';
    var depth = Math.min(1, Math.abs(Math.max(-1, Math.min(1, Math.log10(r)))) * 2.2).toFixed(2);
    return '<td class="num ba-cell is-' + (r > 1 ? 'above' : 'below') + '" style="--d:' + depth + '">' + number(r) + '</td>';
  }
  function name(item) {
    return esc(item.name) + (item.place ? ' <span class="quiet">' + esc(item.place) + '</span>' : '');
  }

  function rows() {
    var f = state.filter.toLowerCase();
    var list = D.moved.filter(function (item) {
      return (!f || (item.name + ' ' + (item.place || '') + ' ' + item.id).toLowerCase().indexOf(f) >= 0) &&
        (!state.cause || item.causes.indexOf(state.cause) >= 0) &&
        (!state.group || item.group === state.group);
    });
    if (state.sort) {
      var s = state.sort;
      list.sort(function (x, y) { return distance(y.values[s]) - distance(x.values[s]) || x.i - y.i; });
    }
    return list;
  }

  function rowHtml(item) {
    var why = item.causes.map(function (c) { return '<code>' + esc(c) + '</code>'; }).join(', ');
    return '<tr data-i="' + item.i + '" tabindex="-1"' + (state.chosen === item ? ' aria-current="true"' : '') + '>' +
      '<th scope="row" class="ba-name" title="' + esc(item.name) + '">' +
      '<button type="button" class="linklike" data-ba-open>' + name(item) + '</button>' +
      (why ? '<span class="ba-why">' + why + '</span>' : '') + '</th>' +
      D.indicators.map(function (i) { return cell(item.values[i.id]); }).join('') + '</tr>';
  }

  function head() {
    var cells = board.querySelectorAll('.ba-grid thead th[data-indicator]');
    Array.prototype.forEach.call(cells, function (th) {
      var id = th.getAttribute('data-indicator'), abbr = th.querySelector('abbr');
      if (!th.querySelector('button')) {
        var button = document.createElement('button');
        button.type = 'button'; button.className = 'ba-sort'; button.setAttribute('data-ba-sort', id);
        button.setAttribute('aria-label', abbr.title + ': sort by the distance from 1');
        th.replaceChild(button, abbr); button.appendChild(abbr);
      }
      if (state.sort === id) th.setAttribute('aria-sort', 'descending'); else th.removeAttribute('aria-sort');
    });
  }

  function counted() {
    var all = state.list.length, shown = Math.min(all, state.limit), left = all - shown;
    var word = all === 1 ? D.items.one : D.items.many;
    q('[data-ba-count]').textContent = 'Showing ' + grouped(shown) + ' of ' + grouped(all) + ' ' + word +
      (all !== D.moved.length ? ' (' + grouped(D.moved.length) + ' listed in all)' : '') +
      (state.sort ? ', the furthest from 1 first.' : '.');
    var more = q('[data-ba-more]');
    more.hidden = left <= 0;
    more.textContent = 'Show ' + grouped(Math.min(STEP, left)) + ' more';
  }

  function render() {
    head();
    state.list = rows();
    q('.ba-grid tbody').innerHTML = state.list.length ? state.list.slice(0, state.limit).map(rowHtml).join('') :
      '<tr class="empty"><td colspan="' + (D.indicators.length + 1) + '">Nothing matches these filters.</td></tr>';
    counted();
  }

  function detail(item) {
    var word = D.word[0];
    var body = D.indicators.map(function (i) {
      var pair = item.values[i.id];
      if (!pair) return '';
      var changed = moved(pair[0], pair[1]);
      var r = ratio(pair[0], pair[1]);
      var scale = Math.max(Math.abs(pair[0] || 0), Math.abs(pair[1] || 0), 1e-300);
      var w = function (x) { return (100 * Math.abs(x || 0) / scale).toFixed(1); };
      return '<tr class="' + (changed ? 'is-moved' : 'is-still') + '"><th scope="row">' + esc(i.name) + '</th>' +
        '<td class="num">' + number(pair[0]) + '</td><td class="num">' + number(pair[1]) + '</td>' +
        '<td class="num">' + (changed ? (percent(pair[0], pair[1]) || '') : 'no change') + '</td>' +
        '<td class="ba-bars" aria-hidden="true"><span class="ba-bar is-before" style="width:' + w(pair[0]) + '%"></span>' +
        '<span class="ba-bar is-after' + (r === null && changed ? ' is-opposite' : '') + '" style="width:' + w(pair[1]) + '%"></span></td>' +
        '<td class="quiet">' + esc(i.unit || '') + '</td></tr>';
    }).join('');
    var titles = {};
    D.causes.forEach(function (c) { titles[c.id] = c; });
    var why = item.causes.map(function (c) {
      var known = titles[c] || {};
      return '<li>' + (known.kind ? '<span class="tag">' + esc(known.kind) + '</span> ' : '') + '<code>' + esc(c) + '</code>' +
        (known.title ? ' <span class="ba-about">' + esc(known.title) + '</span>' : '') + '</li>';
    }).join('');
    return '<div class="ba-detail-head"><div><p class="card-label">' + esc(D.groups && item.group ? D.groups[item.group] : D.items.one) + '</p>' +
      '<h3 id="ba-detail-title">' + name(item) + '</h3><p class="card-meta"><code>' + esc(item.id) + '</code></p></div>' +
      '<button class="button" type="button" data-ba-close>Close</button></div>' +
      (item.note ? '<p>' + esc(item.note) + '</p>' : '') +
      (why ? '<h4>Why it moved</h4><ul class="plain">' + why + '</ul>' : '<p class="list-none">No cause is named for this ' + esc(D.items.one) + '.</p>') +
      '<h4>Its results</h4><p class="ba-legend" aria-hidden="true"><span><span class="ba-key is-before"></span>' + esc(D.before.label) + '</span> ' +
      '<span><span class="ba-key is-after"></span>' + esc(D.after.label) + '</span></p>' +
      '<div class="table-wrap"><table class="ba-table ba-values"><thead><tr><th scope="col">' + esc(word.charAt(0).toUpperCase() + word.slice(1)) + '</th>' +
      '<th scope="col" class="num">' + esc(D.before.label) + '</th><th scope="col" class="num">' + esc(D.after.label) + '</th>' +
      '<th scope="col" class="num">Change</th><th scope="col" class="ba-bars-head"><span class="visually-hidden">Before and after, as bars</span></th>' +
      '<th scope="col">Unit</th></tr></thead><tbody>' + body + '</tbody></table></div>';
  }

  function open(item) {
    state.chosen = item;
    var panel = q('[data-ba-detail]');
    panel.innerHTML = detail(item);
    panel.hidden = false;
    Array.prototype.forEach.call(board.querySelectorAll('.ba-grid tbody tr'), function (tr) {
      if (+tr.getAttribute('data-i') === item.i) tr.setAttribute('aria-current', 'true'); else tr.removeAttribute('aria-current');
    });
    panel.focus({ preventScroll: true });
    panel.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  function close() {
    var panel = q('[data-ba-detail]'), item = state.chosen;
    panel.hidden = true; state.chosen = null;
    var row = item && board.querySelector('.ba-grid tbody tr[data-i="' + item.i + '"]');
    if (row) { row.removeAttribute('aria-current'); var b = row.querySelector('[data-ba-open]'); if (b) b.focus(); }
  }

  function fill(select, field, entries) {
    if (entries.length < 2) return;
    entries.forEach(function (entry) {
      var option = document.createElement('option');
      option.value = entry[0]; option.textContent = entry[1]; select.appendChild(option);
    });
    field.hidden = false;
  }

  // ------------------------------------------------------------------ start
  var used = {};
  D.moved.forEach(function (item) { item.causes.forEach(function (c) { used[c] = 1; }); });
  fill(q('[data-ba-cause]'), q('[data-ba-cause-field]'), Object.keys(used).sort().map(function (c) { return [c, c]; }));
  fill(q('[data-ba-group]'), q('[data-ba-group-field]'), Object.keys(D.groups || {}).map(function (g) { return [g, D.groups[g]]; }));
  q('.ba-controls').hidden = false;
  var fixed = board.querySelector('.ba-static');
  if (fixed) fixed.hidden = true;
  board.classList.add('is-live');
  render();

  q('[data-ba-filter]').addEventListener('input', function (e) { state.filter = e.target.value; state.limit = STEP; render(); });
  q('[data-ba-cause]').addEventListener('change', function (e) { state.cause = e.target.value; state.limit = STEP; render(); });
  q('[data-ba-group]').addEventListener('change', function (e) { state.group = e.target.value; state.limit = STEP; render(); });
  q('[data-ba-more]').addEventListener('click', function () { state.limit += STEP; render(); });
  board.addEventListener('click', function (e) {
    var sort = e.target.closest('[data-ba-sort]');
    if (sort) {
      var id = sort.getAttribute('data-ba-sort');
      state.sort = state.sort === id ? null : id; state.limit = STEP; render();
      var again = board.querySelector('[data-ba-sort="' + id.replace(/"/g, '\\"') + '"]');
      if (again) again.focus();
      return;
    }
    if (e.target.closest('[data-ba-close]')) { close(); return; }
    var row = e.target.closest('.ba-grid tbody tr[data-i]');
    if (row) open(D.moved[+row.getAttribute('data-i')]);
  });
  board.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !q('[data-ba-detail]').hidden) close();
  });
})();
