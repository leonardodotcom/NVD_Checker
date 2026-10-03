// Theme bootstrap: loaded synchronously in <head> so the right theme is applied
// before first paint (no light→dark flash). Exposes window.nvdTheme for toggles.
(function () {
  var KEY = "theme";
  var media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  function saved() {
    try { var v = localStorage.getItem(KEY); return v === "light" || v === "dark" ? v : null; } catch (e) { return null; }
  }
  function system() { return media && media.matches ? "dark" : "light"; }
  function apply(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
      var dark = theme === "dark";
      btn.setAttribute("aria-pressed", String(dark));
      btn.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
      btn.title = btn.getAttribute("aria-label");
    });
  }

  apply(saved() || system());

  // Follow the OS setting until the user picks a theme explicitly.
  if (media && media.addEventListener) {
    media.addEventListener("change", function () { if (!saved()) apply(system()); });
  }

  window.nvdTheme = {
    get: function () { return document.documentElement.getAttribute("data-theme"); },
    toggle: function () {
      var next = this.get() === "dark" ? "light" : "dark";
      try { localStorage.setItem(KEY, next); } catch (e) {}
      document.documentElement.classList.add("theme-switching");
      apply(next);
      setTimeout(function () { document.documentElement.classList.remove("theme-switching"); }, 400);
    },
  };

  document.addEventListener("DOMContentLoaded", function () {
    apply(window.nvdTheme.get());
    document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
      btn.addEventListener("click", function () { window.nvdTheme.toggle(); });
    });
  });
})();
