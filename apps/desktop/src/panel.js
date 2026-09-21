/* The menu bar panel: variant C with a caption on every block, which is the variant the
   founder settled on (M4 plan, "Variant choices", 2026-09-20 night).

   Lifted from `docs/design/mockups/dropdown.html`'s variant C with
   `window.PRUDENCE_PROTOTYPE` on, and changed only where the real thing differs from a
   mockup: there is no fake desktop and no fake menu bar, because the window is the
   popover and the menu bar is the machine's own.

   Nothing in this file knows it is inside a Tauri window. */

(function (global) {
  "use strict";

  /* Bound in `render`, not here: the design scripts are injected once the payload exists
     (see boot.js), so at the time this file is evaluated none of them is loaded yet.

     `I` is the mockups' dictionary and is down to two callers: the observation sentence
     and the review headline. Both are *composed* rather than looked up, so they move with
     their rules, in batches 3 and 6a, and `design/i18n.js` goes with the second one. */
  var T, F, I, D, el;

  function text(content, className) {
    return el("span", { class: className || "", text: content });
  }

  /* Today is the machine's today, not the last day the store has a row for.

     The mockups use `Derive.LATEST_DAY` so that a page with frozen data still has
     something to show. A real dropdown answers "what happened today", and a day with
     nothing in it is an answer. `Snapshot.read` in the Swift app does the same. */
  function localDay(date) {
    return (
      date.getFullYear() +
      "-" +
      String(date.getMonth() + 1).padStart(2, "0") +
      "-" +
      String(date.getDate()).padStart(2, "0")
    );
  }

  function startOfLocalDay(day) {
    var parts = day.split("-");
    return new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
  }

  function daysAgo(day, n) {
    var date = startOfLocalDay(day);
    date.setDate(date.getDate() - n);
    return localDay(date);
  }

  /* Rows of `app_session_list` in a window, never a sum of
     `app_usage_by_purpose_day.sessions`: that column is per purpose per day, so summing it
     counts one session once for every day and purpose it touched. */
  function sessionsBetween(fromDay, toDay) {
    var start = startOfLocalDay(fromDay).getTime();
    var end = startOfLocalDay(toDay).getTime() + 86400000;
    // `derive.js` is the mockups' file unchanged and does not expose the session list,
    // which no mockup screen needed; the block is read straight off the payload here.
    var block = D.DATA.sessions;
    if (!block) return 0;
    var at = block.columns.indexOf("started_at");
    if (at < 0) return 0;
    return block.rows.filter(function (row) {
      var stamp = Date.parse(row[at]);
      return stamp >= start && stamp < end;
    }).length;
  }

  function today() {
    var day = localDay(new Date());
    var commits = 0;
    D.commits.forEach(function (row) {
      if (row.day === day) commits += row.commits;
    });
    return { day: day, sessions: sessionsBetween(day, day), commits: commits };
  }

  /* Seven local days back from today inclusive, which is `prudence usage --last 7d`'s
     window and the one the shipping app draws. Not the ISO week: the mockups bucket by
     ISO week for the Overview chart, and the dropdown is a rolling seven days. */
  function thisWeek() {
    var end = localDay(new Date());
    var start = daysAgo(end, 6);
    var byPurpose = D.emptyPurposes();
    var total = 0;
    var minutes = 0;
    var measured = 0;
    D.usage.forEach(function (row) {
      if (row.day < start || row.day > end) return;
      if (byPurpose[row.purpose] === undefined) byPurpose[row.purpose] = 0;
      byPurpose[row.purpose] += row.total_tokens;
      total += row.total_tokens;
      minutes += row.active_minutes;
      measured += row.measured_sessions;
    });
    return {
      byPurpose: byPurpose,
      total: total,
      hours: minutes / 60,
      sessions: sessionsBetween(start, end),
      measured: measured,
    };
  }

  function purposeShares(week) {
    if (!week || !week.total) return [];
    return F.PURPOSES.filter(function (purpose) {
      return week.byPurpose[purpose] > 0;
    }).map(function (purpose) {
      return {
        purpose: purpose,
        share: week.byPurpose[purpose] / week.total,
        tokens: week.byPurpose[purpose],
      };
    });
  }

  function weekSummaryText(week) {
    return F.list(
      purposeShares(week).map(function (part) {
        return F.purpose(part.purpose) + " " + F.percent(part.share);
      })
    );
  }

  function popHead() {
    var head = el("div", { class: "pop-head" });
    var mark = global.Brand.mark(18);
    mark.classList.add("brand-mark");
    head.appendChild(mark);
    head.appendChild(el("span", { class: "name", text: global.Str.productName }));
    head.appendChild(
      el("span", { class: "ver", text: "prudence " + D.DATA.status.engine_version })
    );
    return head;
  }

  /* A caption on its own line and the content full width under it.

     The mockups draw variant C with a caption column on the left, and the prototype
     record froze that on 2026-09-20. The founder changed it the next day, during batch 3:
     "content in the centre, not titles left and values right". DESIGN.md carries the
     later answer, and the shipping Swift app draws it, so that is what this matches. */
  function block(caption, node) {
    var wrap = el("div", { class: "pop-block" });
    wrap.appendChild(el("span", { class: "k", text: caption }));
    wrap.appendChild(node);
    return wrap;
  }

  function weekBlock(week) {
    var wrap = el("div", { class: "week-row" });
    wrap.appendChild(text(weekSummaryText(week) || T("menu.noTokensThisWeek"), "obs-line"));
    wrap.appendChild(
      global.Charts.miniStack({
        byPurpose: week ? week.byPurpose : D.emptyPurposes(),
        height: 8,
        caption:
          T("menu.thisWeek") +
          ": " +
          (weekSummaryText(week) || T("menu.noTokensThisWeek")) +
          " (" +
          F.tokenPhrase(week ? week.total : 0) +
          ", " +
          F.sessions(week ? week.sessions : 0) +
          ")",
      })
    );
    if (week && week.total) {
      wrap.appendChild(
        el("div", { class: "week-figures" }, [
          text(F.tokenPhrase(week.total)),
          text(F.sessions(week.sessions)),
          text(F.hourPhrase(week.hours)),
        ])
      );
    }
    return wrap;
  }

  function observationBlock() {
    var row = D.DATA.observations[0];
    if (!row) return text(T("menu.noObservation"), "obs-line");
    var wrap = el("div");
    wrap.appendChild(text(I.observationSentence(row), "obs-sentence"));
    wrap.appendChild(el("div", { class: "coverage-chip", text: I.observationCaveat(row) }));
    return wrap;
  }

  /* `21 Sep 01:45 (12 hours ago)`. Both halves go through the locale, and the shape is
     the catalog's own `menu.stamped`, which is what the Swift popover prints. */
  function lastIngestText() {
    var iso = D.DATA.status.last_ingest_at;
    if (!iso) return T("menu.never");
    return T("menu.stamped", F.stamp(iso), F.relative(iso));
  }

  /* Batch 7 replaces this with the engine's own answer. Until then the panel says which
     batch, rather than swallowing the press. */
  function notYet(what) {
    var line = document.getElementById("pop-note");
    if (!line) return;
    line.textContent = what + ": arrives with the engine wiring, in batch 7.";
    line.hidden = false;
  }

  /* The button grid of DESIGN.md: the primary full width, two equal cells under it, and
     one baseline carrying the two quiet actions out to both outer edges. */
  function footer() {
    var open = el("button", {
      class: "btn primary wide",
      type: "button",
      text: T("menu.openPrudence"),
    });
    var review = el("button", { class: "btn", type: "button", text: T("menu.reviewNow") });
    var ingest = el("button", { class: "btn", type: "button", text: T("menu.ingestNow") });
    var settings = el("button", { class: "btn plain", type: "button", text: T("menu.settings") });
    var quit = el("button", { class: "btn plain", type: "button", text: T("menu.quit") });

    /* Open Prudence and Settings go to the window, which exists from batch 1. Review now
       and Ingest now need the engine, which is batch 7; they answer with a line rather
       than doing nothing silently, and they are **not** disabled, because a control that
       is greyed out says "not for you" when the truth is "not yet". */
    open.addEventListener("click", function () {
      global.Bridge.openWindow();
    });
    settings.addEventListener("click", function () {
      global.Bridge.openWindow();
    });
    review.addEventListener("click", function () {
      notYet(T("menu.reviewNow"));
    });
    ingest.addEventListener("click", function () {
      notYet(T("menu.ingestNow"));
    });
    quit.addEventListener("click", function () {
      global.Bridge.quit();
    });

    var pair = el("div", { class: "buttons-row" }, [review, ingest]);
    var tail = el("div", { class: "buttons-row" }, [settings, quit]);
    settings.style.flex = "none";
    quit.style.flex = "none";
    quit.style.marginLeft = "auto";
    return [open, pair, tail];
  }

  function render(container) {
    T = global.Str.t;
    F = global.Fmt;
    I = global.I18N;
    D = global.Derive;
    el = global.Charts.el;

    var week = thisWeek();
    var now = today();

    var pop = el("div", { class: "popover" });
    pop.appendChild(popHead());

    var body = el("div", { class: "pop-body" });

    /* The day's counts are the one headline on this surface, and the date sits under
       them. A day with nothing recorded keeps the caption style instead, which is batch
       2's note about a headline reading heavy, kept where it applies. */
    var headline = el("div");
    var counted = now.sessions > 0 || now.commits > 0;
    headline.appendChild(
      el("div", {
        class: counted ? "headline" : "obs-line",
        text: counted
          ? F.list([F.sessions(now.sessions), F.commits(now.commits)])
          : T("menu.noSessionsToday"),
      })
    );
    headline.appendChild(el("div", { class: "headline-sub", text: F.day(now.day) }));
    body.appendChild(block(T("menu.today"), headline));

    var weekWrap = el("div");
    weekWrap.appendChild(weekBlock(week));
    var legend = el("div", { class: "legend" });
    purposeShares(week).forEach(function (part) {
      var key = el("span", { class: "key" });
      var swatch = document.createElement("i");
      swatch.style.background = "var(--p-" + part.purpose + ")";
      key.appendChild(swatch);
      key.appendChild(document.createTextNode(F.purpose(part.purpose)));
      legend.appendChild(key);
    });
    weekWrap.appendChild(legend);
    body.appendChild(block(T("menu.thisWeek"), weekWrap));

    body.appendChild(el("div", { class: "pop-sep" }));
    body.appendChild(block(T("menu.latestObservation"), observationBlock()));
    body.appendChild(el("div", { class: "pop-sep" }));
    body.appendChild(block(T("menu.lastIngest"), text(lastIngestText(), "obs-line")));
    var review = D.DATA.reviews[0];
    body.appendChild(
      block(
        T("menu.lastReview"),
        text(review ? I.reviewHeadline(review) : T("menu.noReview"), "obs-line")
      )
    );
    pop.appendChild(body);

    var foot = el("div", { class: "pop-foot" });
    var note = el("div", { class: "coverage-chip", text: "" });
    note.id = "pop-note";
    note.hidden = true;
    foot.appendChild(note);
    footer().forEach(function (node) {
      foot.appendChild(node);
    });
    pop.appendChild(foot);

    container.innerHTML = "";
    container.appendChild(pop);
    return pop;
  }

  global.Panel = { render: render };
})(window);
