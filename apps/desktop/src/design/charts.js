/* Charts drawn as inline SVG, one builder per data shape, the way Swift Charts would
   draw them: a fixed mark type per shape, values that stay visible, no chart library.

   Every builder returns a <figure> whose <figcaption> carries the same numbers in text,
   so the chart is never the only place a figure exists. */

(function (global) {
  "use strict";

  var NS = "http://www.w3.org/2000/svg";

  function svgEl(name, attrs, children) {
    var node = document.createElementNS(NS, name);
    if (attrs) {
      Object.keys(attrs).forEach(function (key) {
        if (attrs[key] === null || attrs[key] === undefined) return;
        node.setAttribute(key, String(attrs[key]));
      });
    }
    (children || []).forEach(function (child) {
      node.appendChild(child);
    });
    return node;
  }

  function el(name, attrs, children) {
    var node = document.createElement(name);
    if (attrs) {
      Object.keys(attrs).forEach(function (key) {
        if (attrs[key] === null || attrs[key] === undefined) return;
        if (key === "class") node.className = attrs[key];
        else if (key === "text") node.textContent = attrs[key];
        else node.setAttribute(key, String(attrs[key]));
      });
    }
    (children || []).forEach(function (child) {
      node.appendChild(child);
    });
    return node;
  }

  function figure(svg, captionText, ariaLabel) {
    var fig = el("figure", { class: "chart" });
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", ariaLabel || captionText);
    fig.appendChild(svg);
    var cap = el("figcaption", { text: captionText });
    fig.appendChild(cap);
    return fig;
  }

  function purposeColour(purpose) {
    return "var(--p-" + purpose + ")";
  }

  function niceMax(value) {
    if (value <= 0) return 1;
    var power = Math.pow(10, Math.floor(Math.log10(value)));
    var scaled = value / power;
    var step = scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 5 ? 5 : 10;
    return step * power;
  }

  /* --- composition of a whole: one stacked bar per period ---------------------------- */

  function stackedBars(options) {
    var columns = options.columns;
    var order = options.order || global.I18N.PURPOSE_ORDER;
    var W = 760;
    var H = options.height || 200;
    var padLeft = 8;
    var padRight = options.axisWidth === undefined ? 56 : options.axisWidth;
    var padTop = 10;
    var padBottom = 26;
    var plotW = W - padLeft - padRight;
    var plotH = H - padTop - padBottom;
    var maxTotal = niceMax(
      columns.reduce(function (acc, col) {
        return Math.max(acc, col.total);
      }, 0)
    );
    var slot = plotW / Math.max(columns.length, 1);
    var barW = Math.min(slot * 0.62, 56);

    var kids = [];
    [0, 0.25, 0.5, 0.75, 1].forEach(function (fraction) {
      var y = padTop + plotH - plotH * fraction;
      kids.push(svgEl("line", { x1: padLeft, y1: y, x2: padLeft + plotW, y2: y, class: "gridline" }));
      if (padRight > 20) {
        kids.push(
          svgEl(
            "text",
            { x: padLeft + plotW + 8, y: y + 3.5, class: "axis" },
            [document.createTextNode(options.axisFormat(maxTotal * fraction))]
          )
        );
      }
    });

    columns.forEach(function (col, index) {
      var x = padLeft + slot * index + (slot - barW) / 2;
      var group = svgEl("g", { class: "col", tabindex: "0", "data-key": col.key });
      var y = padTop + plotH;
      order.forEach(function (purpose) {
        var value = col.byPurpose[purpose] || 0;
        if (value <= 0) return;
        var h = (value / maxTotal) * plotH;
        y -= h;
        group.appendChild(
          svgEl("rect", {
            class: "bar",
            x: x,
            y: y,
            width: barW,
            height: Math.max(h, 0.75),
            fill: purposeColour(purpose),
            rx: 1.5,
          })
        );
      });
      group.appendChild(
        svgEl("rect", {
          x: padLeft + slot * index,
          y: padTop,
          width: slot,
          height: plotH,
          fill: "transparent",
        })
      );
      group.appendChild(
        svgEl("text", { x: x + barW / 2, y: H - 8, "text-anchor": "middle", class: "axis" }, [
          document.createTextNode(col.label),
        ])
      );
      kids.push(group);
    });

    var svg = svgEl("svg", { viewBox: "0 0 " + W + " " + H }, kids);

    var columnsByKey = {};
    columns.forEach(function (col) {
      columnsByKey[col.key] = col;
    });

    function mark(selectedKey, hoverKey) {
      var active = hoverKey || selectedKey;
      Array.prototype.forEach.call(svg.querySelectorAll("g.col"), function (group) {
        var key = group.getAttribute("data-key");
        group.classList.toggle("dim", Boolean(active) && key !== active);
      });
      if (options.onActive) options.onActive(active ? columnsByKey[active] : null);
    }

    Array.prototype.forEach.call(svg.querySelectorAll("g.col"), function (group) {
      var key = group.getAttribute("data-key");
      group.addEventListener("mouseenter", function () {
        mark(options.selectedKey(), key);
      });
      group.addEventListener("focus", function () {
        mark(options.selectedKey(), key);
      });
      group.addEventListener("mouseleave", function () {
        mark(options.selectedKey(), null);
      });
      group.addEventListener("blur", function () {
        mark(options.selectedKey(), null);
      });
      group.addEventListener("click", function () {
        options.onSelect(options.selectedKey() === key ? null : key);
      });
      group.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          options.onSelect(options.selectedKey() === key ? null : key);
        }
      });
    });

    mark(options.selectedKey(), null);
    return figure(svg, options.caption, options.caption);
  }

  /* --- composition of a whole, one row: the dropdown's mini stacked bar --------------- */

  function miniStack(options) {
    var order = options.order || global.I18N.PURPOSE_ORDER;
    var W = 320;
    var H = options.height || 10;
    var total = order.reduce(function (acc, purpose) {
      return acc + (options.byPurpose[purpose] || 0);
    }, 0);
    var x = 0;
    var kids = [];
    if (total <= 0) {
      kids.push(svgEl("rect", { x: 0, y: 0, width: W, height: H, rx: H / 2, fill: "var(--control-2)" }));
    } else {
      order.forEach(function (purpose) {
        var value = options.byPurpose[purpose] || 0;
        if (value <= 0) return;
        var w = (value / total) * W;
        kids.push(
          svgEl("rect", {
            x: x,
            y: 0,
            width: Math.max(w - 1.5, 1.5),
            height: H,
            rx: 2,
            fill: purposeColour(purpose),
          })
        );
        x += w;
      });
    }
    var svg = svgEl("svg", { viewBox: "0 0 " + W + " " + H, preserveAspectRatio: "none" }, kids);
    svg.style.height = H + "px";
    var fig = figure(svg, options.caption, options.caption);
    fig.querySelector("figcaption").className = "sr";
    return fig;
  }

  /* --- two groups compared: paired horizontal bars, the core Prudence chart -----------

     The marks are SVG; the label, the value and the n are HTML beside them, so the
     type stays at its real size however narrow the column gets. */

  function track(layers, height) {
    var wrap = el("div", { class: "track-wrap" });
    wrap.style.height = height + "px";
    var kids = layers.map(function (layer) {
      return svgEl("rect", {
        x: 0,
        y: 0,
        width: Math.max(layer.fraction * 1000, layer.fraction > 0 ? 4 : 0),
        height: 100,
        fill: layer.fill,
        "fill-opacity": layer.opacity === undefined ? 1 : layer.opacity,
      });
    });
    var svg = svgEl(
      "svg",
      { viewBox: "0 0 1000 100", preserveAspectRatio: "none", "aria-hidden": "true" },
      kids
    );
    svg.style.height = "100%";
    svg.style.width = "100%";
    wrap.appendChild(svg);
    return wrap;
  }

  function niceMaxShare(value) {
    if (value <= 0.25) return 0.25;
    if (value <= 0.5) return 0.5;
    if (value <= 0.75) return 0.75;
    return 1;
  }

  function pairedBars(options) {
    var max = Math.max(options.withValue, options.withoutValue, 0.01);
    var scale = options.scaleToOne ? 1 : niceMaxShare(max);
    var rows = [
      {
        label: options.labelWith,
        value: options.withValue,
        n: options.withN,
        fill: options.colourWith || "var(--accent)",
      },
      {
        label: options.labelWithout,
        value: options.withoutValue,
        n: options.withoutN,
        fill: options.colourWithout || "var(--text-3)",
      },
    ];

    var fig = el("figure", { class: "chart paired" });
    fig.setAttribute("role", "img");
    fig.setAttribute("aria-label", options.caption);
    if (options.labelWidth) {
      fig.style.setProperty("--paired-label", options.labelWidth + "px");
    }
    rows.forEach(function (row) {
      var line = el("div", { class: "paired-row" });
      line.appendChild(el("span", { class: "paired-label", text: row.label }));
      line.appendChild(
        track(
          [
            { fraction: 1, fill: "var(--surface-sunken)" },
            { fraction: row.value / scale, fill: row.fill },
          ],
          16
        )
      );
      var value = el("span", { class: "paired-value" });
      var strong = document.createElement("b");
      strong.textContent = global.I18N.percent(row.value);
      value.appendChild(strong);
      value.appendChild(document.createTextNode(" · n=" + row.n));
      line.appendChild(value);
      fig.appendChild(line);
    });

    var gapPoints = Math.abs(
      global.I18N.points(options.withValue) - global.I18N.points(options.withoutValue)
    );
    var gapRow = el("div", { class: "paired-row paired-gap" });
    gapRow.appendChild(el("span", { class: "paired-label" }));
    gapRow.appendChild(el("span", { text: global.I18N.t("gap", { n: gapPoints }) }));
    fig.appendChild(gapRow);

    fig.appendChild(el("figcaption", { class: "sr", text: options.caption }));
    return fig;
  }

  /* --- composition of a whole: a donut with the percentages beside it ---------------- */

  function donut(options) {
    var order = options.order || global.I18N.PURPOSE_ORDER;
    var size = 168;
    var radius = 66;
    var thickness = 22;
    var centre = size / 2;
    var total = order.reduce(function (acc, purpose) {
      return acc + (options.byPurpose[purpose] || 0);
    }, 0);
    var kids = [];
    var angle = -Math.PI / 2;

    if (total <= 0) {
      kids.push(
        svgEl("circle", {
          cx: centre,
          cy: centre,
          r: radius - thickness / 2,
          fill: "none",
          stroke: "var(--control-2)",
          "stroke-width": thickness,
        })
      );
    } else {
      order.forEach(function (purpose) {
        var value = options.byPurpose[purpose] || 0;
        if (value <= 0) return;
        var sweep = (value / total) * Math.PI * 2;
        var r = radius - thickness / 2;
        var x1 = centre + r * Math.cos(angle);
        var y1 = centre + r * Math.sin(angle);
        var x2 = centre + r * Math.cos(angle + sweep);
        var y2 = centre + r * Math.sin(angle + sweep);
        var large = sweep > Math.PI ? 1 : 0;
        var d =
          value / total > 0.999
            ? "M " + (centre - r) + " " + centre + " a " + r + " " + r + " 0 1 1 0 0.01"
            : "M " + x1 + " " + y1 + " A " + r + " " + r + " 0 " + large + " 1 " + x2 + " " + y2;
        kids.push(
          svgEl("path", {
            d: d,
            fill: "none",
            stroke: purposeColour(purpose),
            "stroke-width": thickness,
            "stroke-linecap": "butt",
          })
        );
        angle += sweep;
      });
    }

    kids.push(
      svgEl(
        "text",
        {
          x: centre,
          y: centre - 2,
          "text-anchor": "middle",
          "font-size": 20,
          "font-weight": 620,
          fill: "var(--text)",
        },
        [document.createTextNode(options.centreValue)]
      )
    );
    kids.push(
      svgEl(
        "text",
        { x: centre, y: centre + 16, "text-anchor": "middle", class: "axis" },
        [document.createTextNode(options.centreLabel)]
      )
    );

    var svg = svgEl("svg", { viewBox: "0 0 " + size + " " + size }, kids);
    svg.style.maxWidth = size + "px";
    return figure(svg, options.caption, options.caption);
  }

  /* --- a share with its coverage: a bar with the coverage as a pale underlay ---------- */

  function shareWithCoverage(options) {
    var fig = el("figure", { class: "chart share" });
    fig.setAttribute("role", "img");
    fig.setAttribute("aria-label", options.caption);
    var stack = el("div", { class: "share-stack" });
    var hasCoverage = options.coverage !== null && options.coverage !== undefined;
    if (hasCoverage) {
      var under = track([{ fraction: options.coverage, fill: "var(--coverage)" }], 26);
      under.classList.add("share-coverage");
      stack.appendChild(under);
    }
    var bar = track(
      [
        { fraction: 1, fill: "var(--surface-sunken)" },
        { fraction: options.value, fill: options.colour || "var(--accent)" },
      ],
      16
    );
    bar.classList.add("share-value");
    stack.appendChild(bar);
    fig.appendChild(stack);
    fig.appendChild(el("figcaption", { class: "sr", text: options.caption }));
    return fig;
  }

  /* --- over time: lines that stop at a gap rather than drawing through it ------------- */

  function lines(options) {
    var W = 760;
    var H = options.height || 220;
    var padLeft = 8;
    var padRight = 48;
    var padTop = 12;
    var padBottom = 26;
    var plotW = W - padLeft - padRight;
    var plotH = H - padTop - padBottom;
    var slots = Math.max(options.labels.length, 1);
    var step = slots === 1 ? 0 : plotW / (slots - 1);
    var kids = [];

    [0, 0.5, 1].forEach(function (fraction) {
      var y = padTop + plotH - plotH * fraction;
      kids.push(svgEl("line", { x1: padLeft, y1: y, x2: padLeft + plotW, y2: y, class: "gridline" }));
      kids.push(
        svgEl("text", { x: padLeft + plotW + 8, y: y + 3.5, class: "axis" }, [
          document.createTextNode(Math.round(fraction * 100) + "%"),
        ])
      );
    });

    function x(index) {
      return padLeft + step * index;
    }
    function y(value) {
      return padTop + plotH - value * plotH;
    }

    (options.series || []).forEach(function (series) {
      var run = [];
      function flush() {
        if (run.length === 1) {
          kids.push(
            svgEl("circle", {
              cx: x(run[0].i),
              cy: y(run[0].v),
              r: 3,
              fill: series.colour,
              opacity: series.wide ? 0.34 : 1,
            })
          );
        } else if (run.length > 1) {
          var d = run
            .map(function (point, index) {
              return (index ? "L " : "M ") + x(point.i) + " " + y(point.v);
            })
            .join(" ");
          kids.push(
            svgEl("path", {
              d: d,
              fill: "none",
              stroke: series.colour,
              "stroke-width": series.wide ? 7 : 2,
              "stroke-linecap": "round",
              "stroke-linejoin": "round",
              "stroke-dasharray": series.dashed ? "3 4" : null,
              opacity: series.wide ? 0.28 : 1,
            })
          );
          if (!series.wide) {
            run.forEach(function (point) {
              kids.push(
                svgEl("circle", { cx: x(point.i), cy: y(point.v), r: 2.6, fill: series.colour })
              );
            });
          }
        }
        run = [];
      }
      series.points.forEach(function (value, index) {
        if (value === null || value === undefined) flush();
        else run.push({ i: index, v: value });
      });
      flush();
    });

    options.labels.forEach(function (label, index) {
      if (options.labels.length > 10 && index % 2 === 1) return;
      kids.push(
        svgEl("text", { x: x(index), y: H - 8, "text-anchor": "middle", class: "axis" }, [
          document.createTextNode(label),
        ])
      );
    });

    var svg = svgEl("svg", { viewBox: "0 0 " + W + " " + H }, kids);
    return figure(svg, options.caption, options.caption);
  }

  /* --- where the hours went: one cell per day, shade is active hours ------------------ */

  function heatStrip(options) {
    var weeks = options.weeks;
    var cell = 15;
    var gapSize = 3;
    var rowLabelW = 26;
    var W = rowLabelW + weeks.length * (cell + gapSize);
    var H = 7 * (cell + gapSize) + 18;
    var kids = [];
    var max = options.max || 1;
    var dayNames =
      global.I18N.lang() === "en"
        ? ["M", "T", "W", "T", "F", "S", "S"]
        : ["一", "二", "三", "四", "五", "六", "日"];

    [0, 2, 4, 6].forEach(function (rowIndex) {
      kids.push(
        svgEl(
          "text",
          { x: 0, y: rowIndex * (cell + gapSize) + cell - 3, class: "axis", "font-size": 9 },
          [document.createTextNode(dayNames[rowIndex])]
        )
      );
    });

    weeks.forEach(function (week, weekIndex) {
      week.days.forEach(function (day, dayIndex) {
        var strength = day.hours === null ? 0 : Math.min(day.hours / max, 1);
        var opacity = day.hours ? 0.16 + 0.84 * Math.pow(strength, 0.6) : 0;
        var rect = svgEl("rect", {
          x: rowLabelW + weekIndex * (cell + gapSize),
          y: dayIndex * (cell + gapSize),
          width: cell,
          height: cell,
          rx: 3,
          fill: day.hours ? "var(--accent)" : "var(--surface-sunken)",
          "fill-opacity": day.hours ? opacity : 1,
        });
        rect.appendChild(
          svgEl("title", {}, [
            document.createTextNode(
              day.date + ": " + global.I18N.oneDecimal(day.hours || 0) + " " + global.I18N.t("hours")
            ),
          ])
        );
        kids.push(rect);
      });
      if (weekIndex % 2 === 0) {
        kids.push(
          svgEl(
            "text",
            {
              x: rowLabelW + weekIndex * (cell + gapSize),
              y: H - 4,
              class: "axis",
              "font-size": 9,
            },
            [document.createTextNode(week.label)]
          )
        );
      }
    });

    var svg = svgEl("svg", { viewBox: "0 0 " + W + " " + H }, kids);
    svg.style.maxWidth = W + "px";
    var fig = figure(svg, options.caption, options.caption);
    fig.classList.add("heat");
    return fig;
  }

  global.Charts = {
    el: el,
    svgEl: svgEl,
    figure: figure,
    purposeColour: purposeColour,
    stackedBars: stackedBars,
    miniStack: miniStack,
    pairedBars: pairedBars,
    donut: donut,
    shareWithCoverage: shareWithCoverage,
    lines: lines,
    heatStrip: heatStrip,
  };
})(window);
