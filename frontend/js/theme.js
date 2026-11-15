/**
 * TerraTrend Theme Switcher — Single Source of Truth
 * Supports Light, Dark, and System preference. Persists choice in localStorage.
 */
(function() {
  const STORAGE_KEY = "teratrend_theme";

  function getStoredTheme() {
    try {
      return localStorage.getItem(STORAGE_KEY) || "system";
    } catch (e) {
      return "system";
    }
  }

  function applyTheme(theme) {
    if (theme === "dark") {
      document.documentElement.setAttribute("data-theme", "dark");
    } else if (theme === "light") {
      document.documentElement.setAttribute("data-theme", "light");
    } else {
      document.documentElement.removeAttribute("data-theme");
    }

    // Update meta theme-color for mobile browsers
    const metaThemeColor = document.querySelector('meta[name="theme-color"]');
    if (metaThemeColor) {
      const isDark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
      metaThemeColor.setAttribute("content", isDark ? "#142004" : "#FFFDDD");
    }

    // Update button text / icon if toggle exists in DOM
    const btn = document.getElementById("themeToggleBtn");
    if (btn) {
      const activeMode = theme === "system" ? "Auto" : (theme === "dark" ? "Dark" : "Light");
      const icon = theme === "dark" ? "🌙" : (theme === "light" ? "☀️" : "🌓");
      btn.setAttribute("aria-label", `Current theme: ${activeMode}. Click to toggle.`);
      btn.innerHTML = `<span style="font-size:1rem;">${icon}</span> <span class="theme-label">${activeMode}</span>`;
    }

    // Dispatch event for Chart.js and Leaflet map synchronization
    window.dispatchEvent(new CustomEvent("teratrend:theme-changed", { detail: { theme } }));
  }

  // Apply immediately before page render to avoid flash
  const initial = getStoredTheme();
  applyTheme(initial);

  // Global toggle function
  window.toggleTheme = function() {
    const current = getStoredTheme();
    let next = "dark";
    if (current === "dark") next = "light";
    else if (current === "light") next = "system";
    else next = "dark";

    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch (e) {}

    applyTheme(next);
  };

  // Listen to system changes if in system mode
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function(e) {
    if (getStoredTheme() === "system") {
      applyTheme("system");
    }
  });

  // Wire up button on DOMContentLoaded
  document.addEventListener("DOMContentLoaded", function() {
    const btn = document.getElementById("themeToggleBtn");
    if (btn) {
      btn.addEventListener("click", window.toggleTheme);
      applyTheme(getStoredTheme());
    }
  });
})();
