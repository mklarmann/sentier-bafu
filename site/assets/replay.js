// The last run on "Patch and release": one step at a time beside what the run printed, and a
// replay of the run. Without this script the page holds every step and every line, in order.
// The text of a line is never changed: a line is shown, hidden or dimmed, nothing else.
(function () {
  var CAP = 650, FLOOR = 38, DWELL = 1900; // waits of the run, shortened; the pause after a step
  var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  [].forEach.call(document.querySelectorAll("[data-run]"), function (run) {
    var tabs = [].slice.call(run.querySelectorAll(".run-tab")), panels = [].slice.call(run.querySelectorAll(".run-panel"));
    var lines = [].slice.call(run.querySelectorAll(".tl")), pre = run.querySelector("pre.transcript");
    var controls = run.querySelector(".run-controls"), play = run.querySelector("[data-run-play]");
    var prev = run.querySelector("[data-run-prev]"), next = run.querySelector("[data-run-next]");
    var clock = run.querySelector("[data-run-clock]"), strip = run.querySelector(".run-tabs");
    if (!tabs.length || tabs.length !== panels.length || !controls || !play || !prev || !next) return;
    var stepOf = lines.map(function (line) { return Math.min(panels.length - 1, +line.getAttribute("data-step")); });
    var time = lines.map(function (line) { return +line.getAttribute("data-t"); });
    var end = lines.length ? lines[lines.length - 1].getAttribute("data-clock") : "";
    var current = 0, at = 0, timer = null;
    run.classList.add("is-live");
    controls.hidden = false;
    if (!lines.length) play.hidden = true;

    function tell(n) {
      if (clock) clock.textContent = n && lines.length ? lines[n - 1].getAttribute("data-clock") + " of " + end : "";
    }
    function show(step, follow) {
      current = Math.max(0, Math.min(panels.length - 1, step));
      tabs.forEach(function (tab, n) {
        if (n === current) tab.setAttribute("aria-current", "step"); else tab.removeAttribute("aria-current");
      });
      panels.forEach(function (panel, n) {
        panel.classList.toggle("is-shown", n === current);
        panel.setAttribute("aria-hidden", n === current ? "false" : "true");
      });
      lines.forEach(function (line, n) { line.classList.toggle("is-on", stepOf[n] === current); });
      prev.disabled = current === 0;
      next.disabled = current === panels.length - 1;
      if (strip && strip.scrollWidth > strip.clientWidth) {
        var tab = tabs[current].parentNode;
        strip.scrollLeft = tab.offsetLeft - (strip.clientWidth - tab.offsetWidth) / 2;
      }
      if (follow !== false && pre) {
        var first = stepOf.indexOf(current);
        if (first >= 0) pre.scrollTop = Math.max(0, lines[first].offsetTop - 10);
      }
    }
    function rest(label) {
      clearTimeout(timer);
      timer = null;
      run.classList.remove("is-playing");
      play.textContent = label;
    }
    function whole() { // every line on the page again, as before a replay
      lines.forEach(function (line) { line.hidden = false; });
      at = 0;
      tell(0);
    }
    function tick() {
      if (at >= lines.length) {
        rest("Play again");
        whole();
        show(panels.length - 1, false);
        pre.scrollTop = pre.scrollHeight;
        return;
      }
      if (stepOf[at] !== current) show(stepOf[at], false);
      lines[at].hidden = false;
      pre.scrollTop = pre.scrollHeight;
      tell(at + 1);
      var wait = FLOOR;
      if (at + 1 < lines.length) {
        wait = stepOf[at + 1] !== stepOf[at] ? DWELL : Math.max(FLOOR, Math.min(CAP, (time[at + 1] - time[at]) * 1000));
      } else {
        wait = DWELL;
      }
      at += 1;
      timer = setTimeout(tick, wait);
    }
    function start() {
      if (at === 0 || at >= lines.length) {
        lines.forEach(function (line) { line.hidden = true; });
        at = 0;
        show(lines.length ? stepOf[0] : 0, false);
      }
      run.classList.add("is-playing");
      play.textContent = "Pause";
      tick();
    }
    function choose(step) { // the reader takes over: the replay ends, everything is there
      rest("Play the run");
      whole();
      show(step);
    }

    play.addEventListener("click", function () {
      if (timer) rest("Continue"); else start();
    });
    prev.addEventListener("click", function () { choose(current - 1); });
    next.addEventListener("click", function () { choose(current + 1); });
    tabs.forEach(function (tab, n) {
      tab.addEventListener("click", function (event) {
        event.preventDefault();
        choose(n);
      });
      tab.addEventListener("keydown", function (event) {
        var to = event.key === "ArrowRight" ? n + 1 : event.key === "ArrowLeft" ? n - 1 : -1;
        if (to < 0 || to >= tabs.length) return;
        event.preventDefault();
        choose(to);
        tabs[to].focus();
      });
    });
    [].forEach.call(run.querySelectorAll('a[href^="#run-step-"]:not(.run-tab)'), function (link) {
      link.addEventListener("click", function (event) {
        var n = +link.getAttribute("href").slice(10) - 1;
        if (!(n >= 0 && n < panels.length)) return;
        event.preventDefault();
        choose(n);
        run.querySelector(".run-stage").scrollIntoView({ block: "nearest" });
      });
    });

    var asked = /^#run-step-(\d+)$/.exec(location.hash);
    show(asked ? +asked[1] - 1 : 0);
    // The run plays once by itself when the page opens on it. Not for a reader who asked for
    // less motion, who followed a link to another part of the page, or who has left the tab.
    if (!still && !location.hash && lines.length && !document.hidden) {
      var top = run.getBoundingClientRect().top;
      if (top < window.innerHeight * 0.7) timer = setTimeout(function () { timer = null; start(); }, 900);
    }
  });

  // What stands beside the text for a part of the page appears once the reader is past that part.
  [].forEach.call(document.querySelectorAll("[data-show-after]"), function (box) {
    var part = document.getElementById(box.getAttribute("data-show-after"));
    if (!part || !("IntersectionObserver" in window)) return;
    box.hidden = true;
    new IntersectionObserver(function (entries) {
      var entry = entries[entries.length - 1];
      box.hidden = entry.isIntersecting || entry.boundingClientRect.top > 0;
    }).observe(part);
  });
})();
