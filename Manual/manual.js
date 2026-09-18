(() => {
  document.documentElement.classList.add('js');
  const language = document.documentElement.lang === 'en' ? 'en' : 'zh-Hant';
  const pages = { 'zh-Hant': 'index.html', en: 'index-en.html' };
  const storageKey = 'b518-manual-language';
  const explicitLanguage = new URLSearchParams(location.search).get('lang');
  const saveLanguage = (value) => {
    try { localStorage.setItem(storageKey, value); } catch (_) { /* Offline storage may be unavailable. */ }
  };
  // Explicit language links take precedence over a saved preference, even on file://.
  // Only the default Chinese entry auto-restores a preference; direct English links stay English.
  if (Object.prototype.hasOwnProperty.call(pages, explicitLanguage)) {
    saveLanguage(explicitLanguage);
    if (explicitLanguage !== language) {
      location.replace(pages[explicitLanguage] + '?lang=' + explicitLanguage + location.hash);
      return;
    }
  } else if (language === 'zh-Hant') {
    let savedLanguage;
    try { savedLanguage = localStorage.getItem(storageKey); } catch (_) { /* Keep the default. */ }
    if (savedLanguage === 'en') {
      location.replace(pages.en + '?lang=en' + location.hash);
      return;
    }
  }

  const messages = language === 'en' ? {
    copied: 'Copied. Paste the template into WeChat.',
    fallback: 'Text selected. Press Command+C on Mac or Ctrl+C on Windows to copy.',
    enlarge: 'Enlarge image: '
  } : {
    copied: '已複製，可貼到 WeChat。',
    fallback: '已選取文字，請按 Command+C（Mac）或 Ctrl+C（Windows）複製。',
    enlarge: '放大圖片：'
  };
  const languageLinks = document.querySelectorAll('[data-language]');
  const sections = Array.from(document.querySelectorAll('main section[id]'));
  const currentSection = () => {
    const boundary = (document.querySelector('.language-switch')?.getBoundingClientRect().bottom || 0) + 24;
    let current = '';
    for (const section of sections) {
      if (section.getBoundingClientRect().top <= boundary) current = section.id;
      else break;
    }
    return current;
  };
  const updateLanguageLinks = () => {
    const section = currentSection();
    languageLinks.forEach((link) => {
      const target = link.dataset.language;
      link.href = pages[target] + '?lang=' + target + (section ? '#' + section : '');
    });
  };
  languageLinks.forEach((link) => link.addEventListener('click', () => {
    updateLanguageLinks();
    saveLanguage(link.dataset.language);
  }));
  let scrollPending = false;
  window.addEventListener('scroll', () => {
    if (scrollPending) return;
    scrollPending = true;
    requestAnimationFrame(() => { updateLanguageLinks(); scrollPending = false; });
  }, { passive: true });
  window.addEventListener('load', updateLanguageLinks);
  window.addEventListener('hashchange', updateLanguageLinks);

  const navButton = document.querySelector('.nav-toggle');
  const nav = document.querySelector('nav');
  if (navButton && nav) navButton.addEventListener('click', () => {
    const open = nav.classList.toggle('open');
    navButton.setAttribute('aria-expanded', String(open));
  });

  const dialog = document.querySelector('#image-dialog');
  const dialogImage = document.querySelector('#dialog-image');
  const dialogCaption = document.querySelector('#dialog-caption');
  document.querySelectorAll('.manual-image').forEach((image) => {
    image.tabIndex = 0;
    image.setAttribute('role', 'button');
    image.setAttribute('aria-label', messages.enlarge + image.alt);
    const enlarge = () => {
      dialogImage.src = image.src;
      dialogImage.alt = image.alt;
      dialogCaption.textContent = image.dataset.caption || image.alt;
      dialog.showModal();
    };
    image.addEventListener('click', enlarge);
    image.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); enlarge(); }
    });
  });
  document.querySelector('.close-dialog').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', (event) => { if (event.target === dialog) dialog.close(); });

  const copyButton = document.querySelector('#copy-report');
  const template = document.querySelector('#report-template');
  const status = document.querySelector('#copy-status');
  copyButton.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(template.value); status.textContent = messages.copied; }
    catch (_) { template.focus(); template.select(); status.textContent = messages.fallback; }
  });

  // Include collapsed troubleshooting text in print, then restore the reader's state.
  let closedDetails = [];
  window.addEventListener('beforeprint', () => {
    closedDetails = Array.from(document.querySelectorAll('details:not([open])'));
    closedDetails.forEach((detail) => { detail.open = true; });
  });
  window.addEventListener('afterprint', () => {
    closedDetails.forEach((detail) => { detail.open = false; });
    closedDetails = [];
  });
})();
