/* The interface's strings, from one source.

   `strings.en.json` and `strings.zh-Hans.json` are generated once from the Swift String
   Catalog (see `Scripts/strings.py`) and are the source of truth from then on. This is the
   runtime the Swift `Str` enum is on the other side of: look a key up, fill its
   placeholders, choose a plural form.

   Three rules it keeps, each one a Swift test that moves here with it:

   * **A missing key is a bug, not a fallback.** `t` returns the key itself so a screen
     still draws, and the test suite fails on it, which is the Swift behaviour.
   * **Placeholders are numbered and are filled in each language's own order.** That is
     the whole reason they are `%1$@` rather than `%@`: Chinese puts them elsewhere.
   * **Plurals are a plural entry, not a suffix.** English says "1 session" and
     "3 sessions"; Chinese has one form and says "1 个会话" either way. The form is chosen
     by `Intl.PluralRules` in the language in force, not by `n === 1`. */

(function (global) {
  "use strict";

  var DEFAULT = "en";
  var tables = {};
  var state = { lang: DEFAULT };
  var pluralRules = {};

  function table() {
    return (tables[state.lang] && tables[state.lang].strings) || {};
  }

  function load(language, payload) {
    tables[language] = payload;
  }

  function loaded() {
    return Object.keys(tables);
  }

  /* Both tables, always. The app ships two languages and the setting switches between
     them without a reload, so loading only the one in force would make that setting a
     relaunch. 30 kB of JSON, once. */
  var LANGUAGES = ["en", "zh-Hans"];

  function loadAll() {
    return Promise.all(
      LANGUAGES.map(function (language) {
        return fetch("design/strings." + language + ".json")
          .then(function (response) {
            if (!response.ok) throw new Error("strings." + language + ": " + response.status);
            return response.json();
          })
          .then(function (payload) {
            load(language, payload);
          });
      })
    );
  }

  function lang() {
    return state.lang;
  }

  function setLang(next) {
    state.lang = tables[next] ? next : DEFAULT;
    document.documentElement.setAttribute("lang", state.lang);
    return state.lang;
  }

  /* `%1$@`, `%2$@`, in whatever order this language wrote them. */
  function fill(template, args) {
    if (!args || !args.length) return template;
    return template.replace(/%(\d+)\$@/g, function (whole, index) {
      var value = args[Number(index) - 1];
      return value === undefined ? whole : String(value);
    });
  }

  function t(key) {
    var value = table()[key];
    if (typeof value !== "string") return key;
    return fill(value, Array.prototype.slice.call(arguments, 1));
  }

  function rules() {
    if (!pluralRules[state.lang]) {
      pluralRules[state.lang] = new Intl.PluralRules(state.lang);
    }
    return pluralRules[state.lang];
  }

  /* `%1$lld` carries the count, and the count is formatted in the reader's own locale
     before it goes in: `1,248 sessions`, not `1248 sessions`. */
  function plural(key, count, formatted) {
    var entry = table()[key];
    if (!entry || typeof entry !== "object") return key;
    var form = rules().select(count);
    var template = entry[form] || entry.other || entry.one;
    if (typeof template !== "string") return key;
    var text = formatted === undefined ? String(count) : String(formatted);
    return template.replace(/%\d+\$lld/g, text);
  }

  function has(key) {
    return Object.prototype.hasOwnProperty.call(table(), key);
  }

  global.Str = {
    /* The product is named in exactly two places: the bundle's display name and this
       constant. The name research is still open, so renaming has to be two edits and not
       two hundred. It is not a catalog key, because it is not translated. */
    productName: "Prudence",
    LANGUAGES: LANGUAGES,
    load: load,
    loadAll: loadAll,
    loaded: loaded,
    lang: lang,
    setLang: setLang,
    t: t,
    plural: plural,
    has: has,
    /* For the tests, which read both tables at once rather than one at a time. */
    tableFor: function (language) {
      return (tables[language] && tables[language].strings) || {};
    },
  };
})(window);
