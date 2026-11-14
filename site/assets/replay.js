// Replays what a run printed (the lines of a .transcript), in the order and with the time
// the run recorded. Without this script every line is on the page, as it is after a replay.
// The text of a line is never changed: a line is shown or hidden, nothing else.
(function () {
  var CAP = 900, FLOOR = 45; // a wait of the run, shortened to at most 0.9 s; never below 45 ms
  [].forEach.call(document.querySelectorAll("[data-replay]"), function (box) {
    var lines = [].slice.call(box.querySelectorAll(".tl")), bar = box.querySelector(".replay-bar");
    var play = box.querySelector("[data-replay-play]"), all = box.querySelector("[data-replay-all]");
    var clock = box.querySelector("[data-replay-clock]"), pre = box.querySelector("pre");
    if (!lines.length || !bar || !play || !all || !pre) return;
    var last = lines[lines.length - 1].getAttribute("data-clock") || "", timer = null, at = 0;
    bar.hidden = false;

    function tell(n) {
      clock.textContent = n ? "Time of the run: " + lines[n - 1].getAttribute("data-clock") + " of " + last
        + " · line " + n + " of " + lines.length : "";
    }
    function end() {
      clearTimeout(timer);
      timer = null;
      lines.forEach(function (line) { line.hidden = false; });
      play.textContent = "Replay";
      all.hidden = true;
      tell(0);
    }
    function step() {
      if (at >= lines.length) return end();
      lines[at].hidden = false;
      pre.scrollTop = pre.scrollHeight;
      tell(at + 1);
      var wait = at + 1 < lines.length ? (lines[at + 1].getAttribute("data-t") - lines[at].getAttribute("data-t")) * 1000 : 0;
      at += 1;
      timer = setTimeout(step, Math.max(FLOOR, Math.min(CAP, wait)));
    }
    play.addEventListener("click", function () {
      if (timer) return end();
      lines.forEach(function (line) { line.hidden = true; });
      at = 0;
      play.textContent = "Stop";
      all.hidden = false;
      step();
    });
    all.addEventListener("click", end);
  });
})();
