document.addEventListener('DOMContentLoaded', () => {
  const themeStorageKey = 'theme';
  const defaultTheme = 'light';

  const savedTheme = localStorage.getItem(themeStorageKey);

  if (!savedTheme) {
    localStorage.setItem(themeStorageKey, defaultTheme);
    document.documentElement.dataset.theme = defaultTheme;
    document.querySelector('html').setAttribute('data-theme', defaultTheme);
  }
});
