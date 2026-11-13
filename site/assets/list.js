// Filter a record list by words and stage. The list is complete without this script.
(function () {
  var q = document.getElementById("q"), stage = document.getElementById("stage");
  var count = document.getElementById("count");
  var rows = [].slice.call(document.querySelectorAll("#list tbody tr"));
  function run() {
    var words = q.value.trim().toLowerCase().split(/\s+/), shown = 0;
    rows.forEach(function (row) {
      var ok = (!stage.value || row.dataset.stage === stage.value) &&
        words.every(function (w) { return row.dataset.text.indexOf(w) >= 0; });
      row.hidden = !ok;
      if (ok) shown += 1;
    });
    count.textContent = shown + " of " + rows.length;
    [].forEach.call(document.querySelectorAll("[data-filter]"), function (tile) {
      tile.setAttribute("aria-pressed", tile.dataset.filter === stage.value ? "true" : "false");
    });
  }
  function fromHash() {
    var m = location.hash.match(/^#stage-(.+)$/);
    if (m) { stage.value = m[1]; run(); }
  }
  q.addEventListener("input", run);
  stage.addEventListener("change", run);
  [].forEach.call(document.querySelectorAll("[data-filter]"), function (tile) {
    tile.addEventListener("click", function (event) {
      event.preventDefault();
      stage.value = stage.value === tile.dataset.filter ? "" : tile.dataset.filter;
      run();
    });
  });
  window.addEventListener("hashchange", fromHash);
  run();
  fromHash();
})();
