// Review cases, their combined build measurement and the public dataset table share one selection.
'use strict';
(function () {
  const picker = document.getElementById('review-case');
  if (!picker) return;
  const opening = picker.closest('.comparison-opening');
  const filter = opening.querySelector('[data-review-filter]');
  const inputs = Array.from(picker.querySelectorAll('input[name=case]'));
  const templates = new Map(Array.from(opening.querySelectorAll('[data-result-case]'),
    template => [template.dataset.resultCase, template]));
  const result = opening.querySelector('[data-review-result]');
  const source = opening.querySelector('[data-case-measurements]');
  const sets = source && JSON.parse(source.textContent);
  const cards = Array.from(opening.querySelectorAll('.comparison-state'));
  const originalNames = cards.map(card => card.querySelector('strong').textContent);
  const number = new Intl.NumberFormat('en');
  const compareCases = (a, b) => a.localeCompare(b, 'en', {numeric: true});

  function selection(ids) {
    const patches = new Set(ids.flatMap(id => sets && sets.cases[id] || []));
    const build = patches.size && sets.builds.find(record =>
      record.patches.length === patches.size && record.patches.every(id => patches.has(id)));
    return {ids, build, outcome: build && sets.outcomes[build.score_sha256]};
  }

  function display() {
    const requested = new URL(location.href).searchParams.getAll('case').flatMap(id => id.split(','));
    inputs.forEach(input => { input.checked = requested.includes(input.value); });
    const ids = inputs.filter(input => input.checked).map(input => input.value).sort(compareCases);
    const scope = selection(ids);
    picker.comparisonSelection = scope;
    opening.querySelector('[data-case-count]').textContent = ids.length ? ids.join(', ') : 'All cases';
    picker.querySelector('[data-clear-cases]').disabled = !ids.length;
    opening.querySelector('.comparison-pair').hidden = !!(ids.length && sets && !scope.build);
    cards.forEach((card, i) => {
      card.querySelector('strong').textContent = scope.build ? [sets.base, scope.build.patches.length === 1
        ? 'One selected patch' : scope.build.patches.length + ' selected patches'][i] : originalNames[i];
      const detail = card.querySelector('.comparison-state-detail');
      if (detail) detail.hidden = !!scope.build;
    });
    result.replaceChildren();
    if (scope.build) {
      const heading = document.createElement('strong');
      heading.textContent = 'Measured together · ' + ids.filter(id => sets.cases[id]).join(', ');
      const figures = document.createElement('p');
      const changed = Object.values(scope.outcome.by_indicator).reduce((a, b) => a + b, 0);
      figures.textContent = number.format(scope.build.edits) + ' patch edits across ' +
        number.format(scope.build.datasets_edited) + ' datasets. ' + number.format(changed) +
        ' impact results changed across ' + number.format(scope.outcome.changed_datasets) +
        ' datasets. The build compared ' + number.format(sets.datasets) + ' datasets across ' +
        sets.indicators.length + ' impact categories.';
      result.append(heading, figures);
      if (scope.outcome.changed_datasets) {
        const link = document.createElement('a');
        link.href = '#moved';
        link.textContent = 'See the changed datasets';
        link.addEventListener('click', () => {
          if (new URL(location.href).searchParams.has('patch')) save();
        });
        result.append(link);
      }
      const details = document.createElement('details');
      const label = document.createElement('summary');
      label.textContent = 'Changes by impact category';
      const table = document.createElement('table');
      table.className = 'ba-table';
      const header = table.createTHead().insertRow();
      for (const title of ['Impact category', 'Datasets changed']) {
        const th = document.createElement('th');
        th.scope = 'col';
        th.textContent = title;
        header.append(th);
      }
      const body = table.createTBody();
      for (const method of sets.indicators) {
        const tr = body.insertRow();
        const th = document.createElement('th');
        th.scope = 'row';
        th.textContent = sets.indicator_labels[method].name;
        tr.append(th);
        tr.insertCell().textContent = number.format(scope.outcome.by_indicator[method]);
      }
      details.append(label, table);
      result.append(details);
    }
    for (const id of (ids.length ? ids : [''])) {
      const section = document.createElement('div');
      if (ids.length) section.className = 'comparison-case-result';
      section.append(templates.get(id).content.cloneNode(true));
      result.append(section);
    }
    picker.dispatchEvent(new Event('comparison-case'));
  }

  function save() {
    const url = new URL(location.href);
    url.searchParams.delete('case');
    url.searchParams.delete('patch');
    const ids = inputs.filter(input => input.checked).map(input => input.value).sort(compareCases);
    ids.forEach(id => url.searchParams.append('case', id));
    history.pushState(history.state, '', url);
    display();
  }
  picker.addEventListener('change', save);
  picker.querySelector('[data-clear-cases]').addEventListener('click', () => {
    inputs.forEach(input => { input.checked = false; });
    save();
    filter.querySelector('summary').focus();
  });
  document.querySelectorAll('[data-pick-cases]').forEach(link => link.addEventListener('click', event => {
    event.preventDefault();
    filter.open = true;
    filter.scrollIntoView({block: 'start'});
    (inputs.find(input => input.checked) || inputs[0] || filter.querySelector('summary')).focus({preventScroll: true});
  }));
  window.addEventListener('popstate', display);
  display();
  filter.hidden = false;

  // A widget route is a bookmark, not a native element ID. Let history restores
  // and ordinary section links keep the browser's scroll position.
  const initialHash = location.hash;
  const route = new URLSearchParams(initialHash.slice(1));
  const navigation = performance.getEntriesByType('navigation')[0];
  if ((route.has('sd.step') || route.has('sd.steps')) && !route.has('sd.item') && !new URL(location.href).searchParams.has('patch')
      && (!navigation || navigation.type !== 'back_forward')) {
    window.addEventListener('load', function () {
      requestAnimationFrame(function () {
        const selected = document.querySelector('.sentier-diagnostics [data-sd="step-said"]');
        if (selected && selected.textContent && location.hash === initialHash) {
          const controls = document.querySelector('.comparison-step-actions');
          (controls || selected).scrollIntoView({ block: 'start' });
        }
      });
    }, { once: true });
  }
})();
