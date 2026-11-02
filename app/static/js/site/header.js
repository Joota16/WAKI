export function initHeader() {
  const search = document.getElementById('global-search');
  const form = document.getElementById('header-search-form');
  if (!search || !form) return;
  document.addEventListener('keydown', event => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault(); search.focus();
    }
  });
  if (/Mac|iPhone|iPad/.test(navigator.platform)) {
    document.querySelector('[data-search-shortcut]').textContent = '⌘ K';
  }
  form.addEventListener('submit', event => {
    if (location.pathname === '/') {
      event.preventDefault(); search.dispatchEvent(new Event('input'));
    }
  });
  document.addEventListener('click', event => {
    document.querySelectorAll('[data-account-menu][open]').forEach(menu => {
      if (!menu.contains(event.target)) menu.open = false;
    });
  });
}
