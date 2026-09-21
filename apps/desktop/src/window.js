/* The window: a sidebar, a toolbar, and one screen at a time.

   Batch 1 builds the shell and nothing that goes in it. The four screens carry
   placeholder rows on purpose: a tall scroll container per screen, switched between by
   the sidebar, is the interaction pattern wry issue 1848 reports the macOS 26 compositor
   giving up on, and the point of this batch is to find out whether it does.

   Nothing in this file knows it is inside a Tauri window. */

(function (global) {
  "use strict";

  var T, I, el;

  /* The four entries, in the order the sidebar shows them and the order Cmd-1 to Cmd-4
     follow. The keys are the ones the shell remembers, so they are not display strings. */
  var SECTIONS = [
    { key: "overview", label: "overview" },
    { key: "review", label: "review" },
    { key: "observations", label: "observations" },
    { key: "settings", label: "settings" },
  ];

  var state = { section: "overview", scroll: {} };
  var nodes = {};

  function text(content, className) {
    return el("span", { class: className || "", text: content });
  }

  /* One placeholder row. Deterministic, so two screenshots of the same screen are the
     same picture: nothing here is random and nothing animates. */
  function placeholderRow(section, index) {
    var share = ((index * 37) % 90) + 8;
    var row = el("div", { class: "placeholder" });
    row.appendChild(text(section + " placeholder row " + (index + 1), "k"));
    var bar = el("div", { class: "bar" });
    var fill = document.createElement("i");
    fill.style.width = share + "%";
    bar.appendChild(fill);
    row.appendChild(bar);
    row.appendChild(
      text(
        "Batch 1 draws the shell, not the screen. This row is here to make the container tall.",
        "k"
      )
    );
    return row;
  }

  function screenBody(section) {
    var wrap = document.createDocumentFragment();
    for (var i = 0; i < 40; i += 1) wrap.appendChild(placeholderRow(section, i));
    return wrap;
  }

  function sectionLabel(key) {
    for (var i = 0; i < SECTIONS.length; i += 1) {
      if (SECTIONS[i].key === key) return SECTIONS[i].label;
    }
    return SECTIONS[0].label;
  }

  function show(section, remember) {
    if (!sectionExists(section)) section = "overview";
    if (nodes.screen) state.scroll[state.section] = nodes.screen.scrollTop;

    state.section = section;
    nodes.buttons.forEach(function (button) {
      if (button.dataset.section === section) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
    nodes.title.textContent = T(sectionLabel(section));
    nodes.screen.classList.remove("is-probe");
    nodes.screen.innerHTML = "";
    nodes.screen.appendChild(screenBody(section));
    nodes.screen.scrollTop = state.scroll[section] || 0;

    if (remember !== false) global.Bridge.setSection(section);
  }

  function sectionExists(key) {
    return SECTIONS.some(function (entry) {
      return entry.key === key;
    });
  }

  function notYet(what) {
    nodes.note.textContent = what + ": arrives with the engine wiring, in batch 7.";
    nodes.note.hidden = false;
  }

  function sidebar() {
    var aside = el("aside", { class: "sidebar" });
    nodes.buttons = SECTIONS.map(function (entry, index) {
      var button = el("button", {
        type: "button",
        text: T(entry.label),
        title: "Cmd-" + (index + 1),
      });
      button.dataset.section = entry.key;
      button.addEventListener("click", function () {
        show(entry.key);
      });
      aside.appendChild(button);
      return button;
    });
    return aside;
  }

  /* The heading and the screen's controls on one row, fixed above the scroll area, on
     the material. That is `.content-head` in the mockups and the toolbar strip in the
     Swift window; a separate strip with the heading scrolling under it is neither. */
  function contentHead() {
    var head = el("div", { class: "content-head" });

    var titles = el("div", { class: "titles" });
    nodes.title = el("h1", { text: "" });
    nodes.sub = el("div", {
      class: "sub",
      text: "Placeholder. The screens arrive in batches 5 to 8.",
    });
    titles.appendChild(nodes.title);
    titles.appendChild(nodes.sub);
    head.appendChild(titles);

    var bar = el("div", { class: "toolbar" });
    var review = el("button", { class: "btn", type: "button", text: T("reviewNow") });
    review.addEventListener("click", function () {
      notYet(T("reviewNow"));
    });
    bar.appendChild(review);
    head.appendChild(bar);
    return head;
  }

  function titlebar() {
    var bar = el("div", { class: "titlebar" });
    var mark = global.Brand.mark(14 / global.Brand.ASPECT);
    mark.classList.add("brand-mark");
    bar.appendChild(mark);
    bar.appendChild(el("span", { class: "name", text: T("app") }));
    return bar;
  }

  function keyboard() {
    document.addEventListener("keydown", function (event) {
      if (!event.metaKey) return;
      var index = ["1", "2", "3", "4"].indexOf(event.key);
      if (index >= 0) {
        event.preventDefault();
        show(SECTIONS[index].key);
        return;
      }
      if (event.key === ",") {
        event.preventDefault();
        show("settings");
        return;
      }
      if (event.key.toLowerCase() === "r") {
        event.preventDefault();
        notYet(T("reviewNow"));
      }
    });
  }

  /* Driven by the shell, never by a user. See `src-tauri/src/stress.rs`. */
  var Stress = {
    step: function (round) {
      var section = SECTIONS[round % SECTIONS.length].key;
      show(section, false);
      var height = nodes.screen.scrollHeight - nodes.screen.clientHeight;
      nodes.screen.scrollTop = height > 0 ? (round * 137) % height : 0;
    },
    finish: function () {
      show("overview", false);
      nodes.screen.scrollTop = 0;
    },
    probe: function (colour) {
      nodes.screen.classList.add("is-probe");
      var fill = nodes.screen.querySelector(".probe-fill");
      if (!fill) {
        fill = document.createElement("div");
        fill.className = "probe-fill";
        nodes.screen.appendChild(fill);
      }
      fill.style.background = colour;
    },
  };

  function render(container, info) {
    I = global.I18N;
    T = I.t;
    el = global.Charts.el;

    var win = el("div", { class: "window" });
    win.appendChild(titlebar());
    var split = el("div", { class: "split" });
    split.appendChild(sidebar());

    var content = el("div", { class: "content" });
    content.appendChild(contentHead());
    nodes.screen = el("div", { class: "screen" });
    content.appendChild(nodes.screen);
    nodes.note = el("div", { class: "note", text: "" });
    nodes.note.hidden = true;
    content.appendChild(nodes.note);
    split.appendChild(content);
    win.appendChild(split);

    container.innerHTML = "";
    container.appendChild(win);

    keyboard();
    show((info && info.section) || "overview", false);
    global.Stress = Stress;
    return win;
  }

  global.WindowScreen = { render: render, SECTIONS: SECTIONS };
})(window);
