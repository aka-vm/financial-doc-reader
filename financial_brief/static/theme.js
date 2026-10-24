(() => {
  const root = document.documentElement;
  const system = window.matchMedia('(prefers-color-scheme: dark)');
  const key = 'reader-theme';
  let choice = 'auto';
  try { const saved = localStorage.getItem(key); if (['auto', 'light', 'dark'].includes(saved)) choice = saved; } catch {}
  function apply() {
    const dark = choice === 'dark' || (choice === 'auto' && system.matches);
    root.dataset.theme = dark ? 'dark' : 'light';
    root.style.colorScheme = dark ? 'dark' : 'light';
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = dark ? '#171a1f' : '#f6f2e9';
  }
  apply();
  system.addEventListener('change', apply);
  window.addEventListener('storage', event => {
    if (event.key !== key && event.key !== null) return;
    choice = ['auto', 'light', 'dark'].includes(event.newValue) ? event.newValue : 'auto';
    apply();
    const select = document.getElementById('theme-select');
    if (select) select.value = choice;
  });
  document.addEventListener('DOMContentLoaded', () => {
    const select = document.getElementById('theme-select');
    select.value = choice;
    select.addEventListener('change', () => {
      choice = select.value;
      try { localStorage.setItem(key, choice); } catch {}
      apply();
    });
  });
})();
