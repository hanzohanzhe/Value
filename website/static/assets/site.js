'use strict';
function syncLanguageLink() {
  document.querySelectorAll('.language, [data-language-link]').forEach(link => {
    const destination = new URL(link.href);
    destination.search = location.search; destination.hash = location.hash;
    link.href = destination.href;
  });
}
window.addEventListener('hashchange', syncLanguageLink);
syncLanguageLink();
const menuButton = document.querySelector('.menu-toggle');
const menu = document.querySelector('#main-nav');
menuButton?.addEventListener('click', () => {
  const open = menuButton.getAttribute('aria-expanded') !== 'true';
  menuButton.setAttribute('aria-expanded', String(open));
  menu.classList.toggle('open', open);
});
document.addEventListener('keydown', event => {
  if (event.key !== 'Escape') return;
  const activeDropdown = document.activeElement?.closest('.nav-dropdown[open]');
  document.querySelectorAll('.nav-dropdown[open]').forEach(item => item.removeAttribute('open'));
  if (activeDropdown) activeDropdown.querySelector('summary').focus();
  else if (menu?.classList.contains('open')) {
    menu.classList.remove('open'); menuButton.setAttribute('aria-expanded','false'); menuButton.focus();
  }
});
document.addEventListener('click', event => {
  document.querySelectorAll('.nav-dropdown[open]').forEach(item => {
    if (!item.contains(event.target)) item.removeAttribute('open');
  });
});
document.querySelectorAll('[data-study-filter]').forEach(button => {
  button.addEventListener('click', () => {
    const product = button.dataset.studyFilter;
    document.querySelectorAll('[data-study-filter]').forEach(b => b.setAttribute('aria-pressed', String(b===button)));
    document.querySelectorAll('[data-study-product]').forEach(card => { card.hidden = product !== 'all' && card.dataset.studyProduct !== product; });
    const count = document.querySelectorAll('[data-study-product]:not([hidden])').length;
    const status = document.querySelector('[data-filter-status]');
    if (status) status.textContent = document.documentElement.lang === 'zh' ? `显示 ${count} 个案例` : `${count} studies shown`;
    const next = new URL(location.href); next.searchParams.set('product',product);
    history.replaceState(null,'',next); syncLanguageLink();
  });
});
const initialStudyFilter = new URLSearchParams(location.search).get('product');
document.querySelectorAll('[data-study-filter]').forEach(button => {
  if(button.dataset.studyFilter === initialStudyFilter) button.click();
});
const productSelect = document.querySelector('[data-product-select]');
const platformSelect = document.querySelector('[data-platform-select]');
function selectPlatform() {
  if (!platformSelect) return;
  const platform = platformSelect.value;
  document.querySelectorAll('[data-platform-note]').forEach(note => { note.hidden = note.dataset.platformNote !== platform; });
  document.querySelectorAll('[data-release-platform]').forEach(release => { release.hidden = release.dataset.releasePlatform !== platform; });
  const next = new URL(location.href); next.searchParams.set('platform', platform);
  history.replaceState(null,'',next); syncLanguageLink();
}
function selectProduct() {
  if (!productSelect) return;
  const product = productSelect.value;
  document.querySelectorAll('[data-product-panel]').forEach(panel => { panel.hidden = panel.dataset.productPanel !== product; });
  const next = new URL(location.href); next.searchParams.set('product', product);
  history.replaceState(null, '', next);
  syncLanguageLink();
}
if(productSelect) {
  const initial = new URLSearchParams(location.search).get('product');
  if (Array.from(productSelect.options).some(o => o.value === initial)) productSelect.value = initial;
  productSelect.addEventListener('change',selectProduct); selectProduct();
}
platformSelect?.addEventListener('change', selectPlatform);
if(platformSelect) {
  const initialPlatform = new URLSearchParams(location.search).get('platform');
  if (Array.from(platformSelect.options).some(o => o.value === initialPlatform)) platformSelect.value = initialPlatform;
}
selectPlatform();
document.querySelectorAll('[data-copy]').forEach(button => {
  button.addEventListener('click', async () => {
    const target = document.getElementById(button.dataset.copy);
    const status = document.getElementById(button.dataset.feedback);
    try {
      await navigator.clipboard.writeText(target.textContent);
      status.textContent = document.documentElement.lang === 'zh' ? '已复制到剪贴板。' : 'Copied to clipboard.';
    } catch {
      const range = document.createRange(); range.selectNodeContents(target);
      const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
      status.textContent = document.documentElement.lang === 'zh' ? '文本已选中，请手动复制。' : 'Text selected. Please copy it manually.';
    }
  });
});
