/* Aggregations over the embedded view rows. Nothing here invents a figure: each
   function sums or filters rows that came from an app_* view, and the callers print
   the denominator next to every share. */

(function (global) {
  "use strict";

  var DATA = global.PRUDENCE_DATA;

  function asObjects(block) {
    return block.rows.map(function (row) {
      var out = {};
      block.columns.forEach(function (name, index) {
        out[name] = row[index];
      });
      return out;
    });
  }

  var usage = asObjects(DATA.usage);
  var outcomes = asObjects(DATA.outcomes);
  var commits = asObjects(DATA.commits);

  function mondayOf(isoDay) {
    var parts = String(isoDay).slice(0, 10).split("-");
    var date = new Date(Date.UTC(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2])));
    var weekday = (date.getUTCDay() + 6) % 7;
    date.setUTCDate(date.getUTCDate() - weekday);
    return date.toISOString().slice(0, 10);
  }

  function addDays(isoDay, n) {
    var parts = String(isoDay).slice(0, 10).split("-");
    var date = new Date(Date.UTC(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2])));
    date.setUTCDate(date.getUTCDate() + n);
    return date.toISOString().slice(0, 10);
  }

  function projects() {
    var seen = {};
    usage.forEach(function (row) {
      seen[row.project] = true;
    });
    return Object.keys(seen).sort();
  }

  /* The last day any view has a row for: the mockup's "today". */
  var LATEST_DAY = (function () {
    var day = "";
    usage.forEach(function (row) {
      if (row.day > day) day = row.day;
    });
    commits.forEach(function (row) {
      if (row.day > day) day = row.day;
    });
    return day;
  })();

  function usageIn(project, sinceDay) {
    return usage.filter(function (row) {
      if (project && row.project !== project) return false;
      if (sinceDay && row.day < sinceDay) return false;
      return true;
    });
  }

  function commitsIn(project, sinceDay) {
    return commits.filter(function (row) {
      if (project && row.project !== project) return false;
      if (sinceDay && row.day < sinceDay) return false;
      return true;
    });
  }

  function emptyPurposes() {
    var byPurpose = {};
    global.I18N.PURPOSE_ORDER.forEach(function (purpose) {
      byPurpose[purpose] = 0;
    });
    return byPurpose;
  }

  function weeklyUsage(project, sinceDay) {
    var buckets = {};
    usageIn(project, sinceDay).forEach(function (row) {
      var week = mondayOf(row.day);
      if (!buckets[week]) {
        buckets[week] = {
          key: week,
          weekStart: week,
          byPurpose: emptyPurposes(),
          byPurposeHours: emptyPurposes(),
          total: 0,
          sessions: 0,
          measured: 0,
          hours: 0,
        };
      }
      var bucket = buckets[week];
      var purpose = bucket.byPurpose[row.purpose] === undefined ? "unknown" : row.purpose;
      bucket.byPurpose[purpose] += row.total_tokens || 0;
      bucket.byPurposeHours[purpose] += (row.active_minutes || 0) / 60;
      bucket.total += row.total_tokens || 0;
      bucket.sessions += row.sessions || 0;
      bucket.measured += row.measured_sessions || 0;
      bucket.hours += (row.active_minutes || 0) / 60;
    });
    return Object.keys(buckets)
      .sort()
      .map(function (key) {
        return buckets[key];
      });
  }

  function totals(project, sinceDay) {
    var out = { sessions: 0, measured: 0, hours: 0, tokens: 0, byPurpose: emptyPurposes() };
    usageIn(project, sinceDay).forEach(function (row) {
      var purpose = out.byPurpose[row.purpose] === undefined ? "unknown" : row.purpose;
      out.sessions += row.sessions || 0;
      out.measured += row.measured_sessions || 0;
      out.hours += (row.active_minutes || 0) / 60;
      out.tokens += row.total_tokens || 0;
      out.byPurpose[purpose] += row.total_tokens || 0;
    });
    var counted = { commits: 0, fact: 0, inferred: 0 };
    commitsIn(project, sinceDay).forEach(function (row) {
      counted.commits += row.commits || 0;
      counted.fact += row.commits_fact || 0;
      counted.inferred += row.commits_inferred || 0;
    });
    out.commits = counted;
    return out;
  }

  function dailyHours(project, sinceDay) {
    var byDay = {};
    usageIn(project, sinceDay).forEach(function (row) {
      byDay[row.day] = (byDay[row.day] || 0) + (row.active_minutes || 0) / 60;
    });
    return byDay;
  }

  /* One column per week, seven cells per column, Monday first. */
  function heatWeeks(project, sinceDay) {
    var byDay = dailyHours(project, sinceDay);
    var start = mondayOf(sinceDay || LATEST_DAY);
    var end = mondayOf(LATEST_DAY);
    var weeks = [];
    var max = 0;
    Object.keys(byDay).forEach(function (day) {
      if (byDay[day] > max) max = byDay[day];
    });
    var cursor = start;
    var guard = 0;
    while (cursor <= end && guard < 200) {
      var days = [];
      for (var index = 0; index < 7; index += 1) {
        var day = addDays(cursor, index);
        days.push({ date: day, hours: byDay[day] || 0 });
      }
      weeks.push({ weekStart: cursor, label: global.I18N.tinyDate(cursor), days: days });
      cursor = addDays(cursor, 7);
      guard += 1;
    }
    return { weeks: weeks, max: max || 1 };
  }

  function outcomesFor(project, sinceDay) {
    return outcomes.filter(function (row) {
      if (project && row.project !== project) return false;
      if (sinceDay && row.week_start < sinceDay) return false;
      return true;
    });
  }

  function outcomeProjects(project, sinceDay) {
    var rows = outcomesFor(project, sinceDay);
    var byProject = {};
    rows.forEach(function (row) {
      if (!byProject[row.project]) byProject[row.project] = [];
      byProject[row.project].push(row);
    });
    return byProject;
  }

  /* The share block a review's outcome section prints, summed over the weeks of one
     window. Same arithmetic as reviews/build.outcome_totals, over app_outcomes_by_week. */
  function outcomeTotals(rows) {
    if (!rows.length) return null;
    var sum = {
      commits: 0,
      fact: 0,
      inferred: 0,
      lines: 0,
      measured_7d: 0,
      alive_7d: 0,
      measured_30d: 0,
      alive_30d: 0,
      measured_90d: 0,
      alive_90d: 0,
      alive_head: 0,
      reworked: 0,
    };
    var coverages = [];
    rows.forEach(function (row) {
      sum.commits += row.commits;
      sum.fact += row.commits_fact;
      sum.inferred += row.commits_inferred;
      sum.lines += row.lines;
      sum.measured_7d += row.measured_7d;
      sum.alive_7d += row.alive_7d;
      sum.measured_30d += row.measured_30d;
      sum.alive_30d += row.alive_30d;
      sum.measured_90d += row.measured_90d;
      sum.alive_90d += row.alive_90d;
      sum.alive_head += row.alive_head;
      sum.reworked += row.reworked;
      if (row.coverage !== null && row.coverage !== undefined) coverages.push(row.coverage);
    });
    sum.coverage = coverages.length
      ? coverages.reduce(function (a, b) {
          return a + b;
        }, 0) / coverages.length
      : null;
    sum.weeks = rows.length;
    return sum;
  }

  function share(alive, measured) {
    if (!measured) return null;
    return alive / measured;
  }

  function observations(project) {
    return DATA.observations.filter(function (row) {
      if (!project) return true;
      return row.project === project || row.pooled === 1;
    });
  }

  function reviewById(id) {
    var found = null;
    DATA.reviews.forEach(function (review) {
      if (review.id === id) found = review;
    });
    return found;
  }

  function sectionOf(review, key) {
    var found = null;
    review.sections.forEach(function (section) {
      if (section.key === key) found = section;
    });
    return found;
  }

  function purposeRowsOf(review) {
    var section = sectionOf(review, "did");
    var byPurpose = {};
    var rows = [];
    if (!section || !section.rows) return { byPurpose: byPurpose, rows: rows };
    section.rows.forEach(function (row) {
      if (row[0] === "all purposes") return;
      var number = null;
      section.numbers.forEach(function (entry) {
        if (entry.key === "did.tokens." + row[0]) number = entry.value;
      });
      var hours = Number(row[3]);
      byPurpose[row[0]] = number || 0;
      rows.push({
        purpose: row[0],
        sessions: Number(row[1]),
        tokensText: row[2],
        tokens: number,
        hours: hours,
      });
    });
    return { byPurpose: byPurpose, rows: rows };
  }

  global.Derive = {
    DATA: DATA,
    usage: usage,
    outcomes: outcomes,
    commits: commits,
    LATEST_DAY: LATEST_DAY,
    mondayOf: mondayOf,
    addDays: addDays,
    projects: projects,
    emptyPurposes: emptyPurposes,
    weeklyUsage: weeklyUsage,
    totals: totals,
    dailyHours: dailyHours,
    heatWeeks: heatWeeks,
    outcomesFor: outcomesFor,
    outcomeProjects: outcomeProjects,
    outcomeTotals: outcomeTotals,
    share: share,
    observations: observations,
    reviewById: reviewById,
    sectionOf: sectionOf,
    purposeRowsOf: purposeRowsOf,
  };
})(window);
