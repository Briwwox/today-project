(function () {
  const root = document.documentElement;
  const STORAGE_KEY = 'theme';
  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

  function readSavedTheme() {
    try {
      const value = localStorage.getItem(STORAGE_KEY);
      return value === 'dark' || value === 'light' ? value : null;
    } catch (_) {
      return null;
    }
  }

  function writeSavedTheme(theme) {
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch (_) {
    }
  }

  function getSystemTheme() {
    return mediaQuery.matches ? 'dark' : 'light';
  }

  function syncToggleUI(theme) {
    const toggleBtn = document.getElementById('themeToggle');
    if (toggleBtn) {
      toggleBtn.setAttribute('aria-pressed', theme === 'dark' ? 'true' : 'false');
    }

    const metaTheme = document.querySelector('meta[name="theme-color"]');
    if (metaTheme) {
      metaTheme.setAttribute('content', theme === 'dark' ? '#17151c' : '#fffaf3');
    }
  }

  function applyTheme(theme, persist = false) {
    const normalized = theme === 'dark' ? 'dark' : 'light';
    root.setAttribute('data-theme', normalized);
    if (persist) {
      writeSavedTheme(normalized);
    }
    syncToggleUI(normalized);
  }

  const savedTheme = readSavedTheme();
  applyTheme(savedTheme || getSystemTheme(), false);

  document.addEventListener('DOMContentLoaded', () => {
    const current = root.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
    syncToggleUI(current);

    const toggleBtn = document.getElementById('themeToggle');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', () => {
        const active = root.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
        applyTheme(active === 'dark' ? 'light' : 'dark', true);
      });
    }
  });

  const handleSystemChange = (e) => {
    if (!readSavedTheme()) {
      applyTheme(e.matches ? 'dark' : 'light', false);
    }
  };

  if (typeof mediaQuery.addEventListener === 'function') {
    mediaQuery.addEventListener('change', handleSystemChange);
  } else if (typeof mediaQuery.addListener === 'function') {
    mediaQuery.addListener(handleSystemChange);
  }
})();