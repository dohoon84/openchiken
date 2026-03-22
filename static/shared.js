/* ── OpenChiken shared layout injection ── */
(function () {
  const currentPage = window.location.pathname.split('/').pop() || '';
  const excludedPages = ['setup.html', ''];

  if (!excludedPages.includes(currentPage)) {
    if (localStorage.getItem('openchiken_setup_done') !== '1') {
      fetch('/api/setup/status', { signal: AbortSignal.timeout(2000) })
        .then(r => r.ok ? r.json() : null)
        .then(d => {
          if (d && d.completed) localStorage.setItem('openchiken_setup_done', '1');
          else window.location.href = '/setup.html';
        })
        .catch(() => {});
    }
  }

  if (excludedPages.includes(currentPage)) return;

  const PAGE_KEY = currentPage.replace('.html', '') || 'dashboard';

  const NAV = [
    { key: 'dashboard', icon: 'dashboard',  label: 'Dashboard',      href: 'dashboard.html' },
    { key: 'apps',      icon: 'apps',       label: 'Apps',           href: 'apps.html' },
    { key: 'tasks',     icon: 'checklist',   label: 'Tasks',          href: 'tasks.html' },
    { key: 'logs',      icon: 'database',    label: 'Memory / Logs',  href: 'logs.html' },
    { key: 'skills',    icon: 'extension',   label: 'Skills',         href: 'skills.html' },
    { key: 'settings',  icon: 'settings',    label: 'Settings',       href: 'settings.html' },
  ];

  /* ── Header ── */
  const header = document.createElement('header');
  header.id = 'oc-header';
  header.innerHTML = `<a href="dashboard.html" style="display:flex;align-items:center;gap:0.625rem;text-decoration:none;">
    <img src="/static/assets/logo.png" alt="OpenChiken" style="width:28px;height:28px;border-radius:8px;object-fit:cover;"/>
    <span style="font-size:1.25rem;font-weight:700;letter-spacing:-0.05em;color:#00daf3;font-family:'Space Grotesk',sans-serif;">OpenChiken</span>
  </a>`;
  document.body.prepend(header);

  /* ── Sidebar ── */
  const aside = document.createElement('aside');
  aside.id = 'oc-sidebar';
  aside.innerHTML = '<nav>' + NAV.map(item => {
    const active = item.key === PAGE_KEY;
    const fill = active ? ' style="font-variation-settings:\'FILL\' 1;"' : '';
    return `<a href="${item.href}" class="${active ? 'active' : ''}">
      <span class="material-symbols-outlined"${fill}>${item.icon}</span>
      <span>${item.label}</span>
    </a>`;
  }).join('') + '</nav>';
  document.body.prepend(aside);

  /* ── Mobile Bottom Nav ── */
  const bottomNav = document.createElement('nav');
  bottomNav.id = 'oc-bottom-nav';
  bottomNav.innerHTML = NAV.map(item => {
    const active = item.key === PAGE_KEY;
    const fill = active ? ' style="font-variation-settings:\'FILL\' 1;"' : '';
    const shortLabel = item.label.split('/')[0].trim();
    return `<a href="${item.href}" class="${active ? 'active' : ''}">
      <span class="material-symbols-outlined"${fill}>${item.icon}</span>
      <span>${shortLabel}</span>
    </a>`;
  }).join('');
  document.body.appendChild(bottomNav);

  /* ── main 간격 보정 (inline style — Tailwind 의존 없음) ── */
  const main = document.querySelector('main');
  if (main) {
    main.style.paddingTop = '4rem';
    main.style.paddingBottom = '5rem';
    main.style.paddingLeft = '1.25rem';
    main.style.paddingRight = '1.25rem';
    main.style.minHeight = '100vh';

    const mq = window.matchMedia('(min-width: 768px)');
    function applyDesktop(e) {
      if (e.matches) {
        main.style.marginLeft = '14rem';
        main.style.paddingLeft = '2rem';
        main.style.paddingRight = '2rem';
        main.style.paddingBottom = '2rem';
      } else {
        main.style.marginLeft = '0';
        main.style.paddingLeft = '1.25rem';
        main.style.paddingRight = '1.25rem';
        main.style.paddingBottom = '5rem';
      }
    }
    applyDesktop(mq);
    mq.addEventListener('change', applyDesktop);
  }
})();
