/* The menu bar panel: variant C with a caption on every block, which is the variant the
   founder settled on (M4 plan, "Variant choices", 2026-09-20 night).

   Lifted from `docs/design/mockups/dropdown.html`'s variant C with
   `window.PRUDENCE_PROTOTYPE` on, and changed only where the real thing differs from a
   mockup: there is no fake desktop and no fake menu bar, because the window is the
   popover and the menu bar is the machine's own.

   Nothing in this file knows it is inside a Tauri window. */

(function (global) {
  "use strict";

  /* Bound in `render`, not here: the vendor scripts are injected once the payload exists
     (see boot.js), so at the time this file is evaluated none of them is loaded yet. */
  var T, I, D, el;

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
    return I.PURPOSE_ORDER.filter(function (purpose) {
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
    return purposeShares(week)
      .map(function (part) {
        return I.purposeLabel(part.purpose) + " " + I.percent(part.share);
      })
      .join(", ");
  }

  function popHead() {
    var head = el("div", { class: "pop-head" });
    var mark = global.Brand.mark(18);
    mark.classList.add("brand-mark");
    head.appendChild(mark);
    head.appendChild(el("span", { class: "name", text: T("app") }));
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
    wrap.appendChild(text(weekSummaryText(week) || T("noSessionsYet"), "obs-line"));
    wrap.appendChild(
      global.Charts.miniStack({
        byPurpose: week ? week.byPurpose : D.emptyPurposes(),
        height: 8,
        caption:
          T("thisWeek") +
          ": " +
          (weekSummaryText(week) || T("noSessionsYet")) +
          " (" +
          I.tokens(week ? week.total : 0) +
          " " +
          T("tokens") +
          ", " +
          (week ? week.measured : 0) +
          "/" +
          (week ? week.sessions : 0) +
          " " +
          T("sessions") +
          ")",
      })
    );
    if (week && week.total) {
      wrap.appendChild(
        el("div", { class: "week-figures" }, [
          text(I.tokens(week.total) + " " + T("tokens")),
          text(week.sessions + " " + T("sessions")),
          text(I.oneDecimal(week.hours) + " " + T("hours")),
        ])
      );
    }
    return wrap;
  }

  function observationBlock() {
    var row = D.DATA.observations[0];
    if (!row) return text(T("noSessionsYet"), "obs-line");
    var wrap = el("div");
    wrap.appendChild(text(I.observationSentence(row), "obs-sentence"));
    wrap.appendChild(el("div", { class: "coverage-chip", text: I.observationCaveat(row) }));
    return wrap;
  }

  function lastIngestText() {
    var iso = D.DATA.status.last_ingest_at;
    if (!iso) return "--";
    return new Date(iso).toLocaleString(I.lang() === "en" ? "en-GB" : "zh-CN", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  /* The button grid of DESIGN.md: the primary full width, two equal cells under it, and
     one baseline carrying the two quiet actions out to both outer edges. */
  function footer() {
    var open = el("button", { class: "btn primary wide", type: "button", text: T("openPrudence") });
    var review = el("button", { class: "btn", type: "button", text: T("reviewNow") });
    var ingest = el("button", { class: "btn", type: "button", text: T("ingestNow") });
    var settings = el("button", { class: "btn plain", type: "button", text: T("settingsEllipsis") });
    var quit = el("button", { class: "btn plain", type: "button", text: T("quit") });

    /* The spike runs no commands: the four that would are inert and say so on hover, and
       only Quit is wired, because a panel you cannot leave is not a panel. */
    [open, review, ingest, settings].forEach(function (button) {
      button.disabled = true;
      button.title = "Not in the spike";
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
    I = global.I18N;
    T = I.t;
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
        text: counted ? T("sessionsCommits", { s: now.sessions, c: now.commits }) : T("noSessionsYet"),
      })
    );
    headline.appendChild(el("div", { class: "headline-sub", text: I.longDate(now.day) }));
    body.appendChild(block(T("today"), headline));

    var weekWrap = el("div");
    weekWrap.appendChild(weekBlock(week));
    var legend = el("div", { class: "legend" });
    purposeShares(week).forEach(function (part) {
      var key = el("span", { class: "key" });
      var swatch = document.createElement("i");
      swatch.style.background = "var(--p-" + part.purpose + ")";
      key.appendChild(swatch);
      key.appendChild(
        document.createTextNode(I.purposeLabel(part.purpose) + " " + I.percent(part.share))
      );
      legend.appendChild(key);
    });
    weekWrap.appendChild(legend);
    body.appendChild(block(T("thisWeek"), weekWrap));

    body.appendChild(el("div", { class: "pop-sep" }));
    body.appendChild(block(T("latestObservation"), observationBlock()));
    body.appendChild(el("div", { class: "pop-sep" }));
    body.appendChild(block(T("lastIngest"), text(lastIngestText(), "obs-line")));
    var review = D.DATA.reviews[0];
    body.appendChild(
      block(T("lastReview"), text(review ? I.reviewHeadline(review) : "--", "obs-line"))
    );
    pop.appendChild(body);

    var foot = el("div", { class: "pop-foot" });
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
