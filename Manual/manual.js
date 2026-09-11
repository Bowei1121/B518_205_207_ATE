(() => {
  const navButton = document.querySelector('.nav-toggle');
  const nav = document.querySelector('nav');
  if (navButton && nav) navButton.addEventListener('click', () => {
    const open = nav.classList.toggle('open');
    navButton.setAttribute('aria-expanded', String(open));
  });

  const dialog = document.querySelector('#image-dialog');
  const dialogImage = document.querySelector('#dialog-image');
  const dialogCaption = document.querySelector('#dialog-caption');
  document.querySelectorAll('.manual-image').forEach((image) => image.addEventListener('click', () => {
    dialogImage.src = image.src;
    dialogImage.alt = image.alt;
    dialogCaption.textContent = image.dataset.caption || image.alt;
    dialog.showModal();
  }));
  document.querySelector('.close-dialog').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', (event) => { if (event.target === dialog) dialog.close(); });

  const copyButton = document.querySelector('#copy-report');
  const template = document.querySelector('#report-template');
  const status = document.querySelector('#copy-status');
  copyButton.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(template.value); status.textContent = '已複製，可貼到 WeChat。'; }
    catch (_) { template.focus(); template.select(); status.textContent = '請按 Command+C 複製。'; }
  });
})();
