// Arbitrary selections use independent fix measurements. The numbered chart keeps its build order.
'use strict';
(function () {
  const panel = document.querySelector('[data-step-sets]');
  const source = document.querySelector('[data-case-measurements]');
  if (!panel || !source) return;
  const data = JSON.parse(source.textContent);
  const sets = data.step_sets;
  const widget = panel.parentElement.querySelector('.sentier-diagnostics');
  const launcher = document.querySelector('[data-combine-steps]');
  const required = sets.required;
  const inputs = Array.from(panel.querySelectorAll('input[type=checkbox]'));
  const byId = new Map(sets.steps.map(step => [step.id, step]));
  const summary = panel.querySelector('[data-step-set-result]');
  const dataset = panel.querySelector('[data-step-dataset]');
  const categoryTable = panel.querySelector('[data-step-table]');
  const format = new Intl.NumberFormat('en', {maximumSignificantDigits: 7});
  let current;
  function node(tag, value) {
    const el = document.createElement(tag);
    el.textContent = value;
    return el;
  }
  function drawTable() {
    const row = current.rows[dataset.value];
    const head = categoryTable.createTHead();
    const labels = ['Impact category', 'Datasets changed'];
    if (row) labels.push('Before', 'After', 'Unit');
    head.replaceChildren();
    const header = head.insertRow();
    labels.forEach(label => header.append(node('th', label)));
    const body = categoryTable.tBodies[0] || categoryTable.createTBody();
    body.replaceChildren();
    for (const id of data.indicators) {
      const method = data.indicator_labels[id];
      const tr = body.insertRow();
      tr.append(node('th', method.name), node('td', format.format(current.by_indicator[id])));
      if (row) {
        for (const score of row.values[id]) {
          const cell = node('td', format.format(score));
          cell.title = String(score);
          tr.append(cell);
        }
        tr.append(node('td', method.unit || ''));
      }
    }
  }
  function show() {
    const url = new URL(location.href);
    const active = url.searchParams.has('patch');
    panel.hidden = !active;
    widget.hidden = active;
    launcher.hidden = active;
    if (!active) {
      panel.comparisonSelection = null;
      panel.dispatchEvent(new Event('comparison-steps'));
      return;
    }
    const raw = url.searchParams.getAll('patch');
    const requested = new Set(raw.filter(p => byId.has(p)));
    const patches = sets.steps.map(s => s.id).filter(id => id !== required && requested.has(id));
    const enforced = patches.length > 0;
    inputs.forEach(input => {
      input.checked = requested.has(input.value) || (enforced && input.value === required);
      input.disabled = enforced && input.value === required;
    });
    const key = sets.effective.filter(id => requested.has(id)).join(',');
    const checksum = sets.outcomes[key];
    current = data.outcomes[checksum];
    const measured = data.builds.find(record => record.patches.length === patches.length &&
      record.patches.every(id => requested.has(id)));
    const prefix = patches.every((id, i) => id === sets.steps[i + 1].id);
    const categoryCount = Object.values(current.by_indicator).reduce((a, b) => a + b, 0);
    const title = patches.length ? patches.map(id => byId.get(id).label).join(' + ') :
      requested.has(required) ? byId.get(required).label : 'Original inventory';
    summary.replaceChildren(node('h3', title), node('p', format.format(categoryCount) +
      ' changed impact results across ' + format.format(current.changed_datasets) + ' datasets. ' +
      format.format(data.datasets) + ' datasets compared across ' + data.indicators.length + ' impact categories.'));
    if (raw.some(id => id && !byId.has(id))) {
      summary.append(node('p', 'This link includes a step outside this build. Only the listed selections are shown.'));
    }
    if (patches.length) {
      summary.append(node('p', (measured || prefix ? 'This set was built and scored.' :
        'Calculated from the individual patch effects. The interaction check found no overlapping effects.') +
        ' Import preparation is included with every patch.'));
    }
    const previous = dataset.value;
    dataset.replaceChildren();
    for (const code of Object.keys(current.rows)) {
      const item = data.listed_datasets[code];
      dataset.add(new Option([item.name, item.place].filter(Boolean).join(' · '), code));
    }
    if (Object.hasOwn(current.rows, previous)) dataset.value = previous;
    panel.querySelector('[data-step-dataset-label]').hidden = !dataset.options.length;
    drawTable();
    panel.comparisonSelection = {ids: [], build: {patches}, outcome: current,
      before: 'Original inventory', after: 'Selected build steps'};
    panel.dispatchEvent(new Event('comparison-steps'));
  }
  function save(ids) {
    const url = new URL(location.href);
    url.searchParams.delete('patch');
    if (ids) {
      if (ids.length) sets.steps.forEach(s => { if (ids.includes(s.id)) url.searchParams.append('patch', s.id); });
      else url.searchParams.append('patch', '');
    }
    history.pushState(history.state, '', url);
    show();
  }
  function start(ids) {
    save(ids);
    panel.scrollIntoView({block: 'start'});
    inputs.find(input => !input.disabled).focus({preventScroll: true});
  }
  function selectedSteps() {
    const strip = widget.querySelector('[data-sd=comparison]');
    if (!strip || strip.querySelector('[data-comp=total][aria-pressed=true]')) return [];
    return Array.from(strip.querySelectorAll('[data-comp][aria-pressed=true]'), chip => chip.dataset.comp);
  }
  launcher.addEventListener('click', () => start(selectedSteps()));
  const actions = document.createElement('div');
  actions.className = 'comparison-step-actions';
  const caseLink = panel.parentElement.querySelector('[data-pick-cases]');
  if (caseLink) {
    const oldPlace = caseLink.parentElement;
    actions.append(caseLink);
    oldPlace.remove();
  }
  actions.append(launcher);
  widget.querySelector('[data-sd=step-said]').before(actions);
  widget.addEventListener('click', event => {
    const chip = event.target.closest('button[data-comp]');
    if (!chip || !(event.metaKey || event.ctrlKey) || !byId.has(chip.dataset.comp)) return;
    event.stopPropagation();
    event.preventDefault();
    const selected = new Set(selectedSteps());
    if (selected.has(chip.dataset.comp)) selected.delete(chip.dataset.comp);
    else selected.add(chip.dataset.comp);
    start(Array.from(selected));
  }, true);
  panel.querySelector('fieldset').addEventListener('change', () =>
    save(inputs.filter(input => input.checked && !input.disabled).map(input => input.value)));
  dataset.addEventListener('change', drawTable);
  panel.querySelector('[data-step-chain]').addEventListener('click', () => {
    save(null);
    launcher.focus();
  });
  window.addEventListener('popstate', show);
  document.getElementById('review-case').addEventListener('comparison-case', show);
  show();
  if (!panel.hidden) window.addEventListener('load', () => panel.scrollIntoView({block: 'start'}), {once: true});
})();
