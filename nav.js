(function () {
  var nav = document.getElementById('site-nav');
  if (!nav) return;

  var style = document.createElement('style');
  style.textContent = [
    /* ── desktop dropdown ── */
    '.nav-dropdown{position:relative;display:inline-flex;align-items:center}',
    '.nav-dropdown-btn{background:none;border:none;font-family:var(--sans);font-size:inherit;font-weight:500;color:var(--muted);cursor:pointer;display:inline-flex;align-items:center;gap:4px;padding:0;line-height:inherit;transition:color .15s;white-space:nowrap}',
    '.nav-dropdown-btn:hover{color:var(--text)}',
    '.nav-dropdown-btn svg{transition:transform .18s}',
    '.nav-dropdown:hover .nav-dropdown-btn svg,.nav-dropdown:focus-within .nav-dropdown-btn svg{transform:rotate(180deg)}',
    '.nav-dropdown-menu{display:none;position:absolute;top:100%;right:0;min-width:180px;padding-top:10px;z-index:200}',
    '.nav-dropdown-menu-inner{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:6px;box-shadow:0 8px 24px rgba(0,0,0,.4)}',
    '.nav-dropdown:hover .nav-dropdown-menu,.nav-dropdown:focus-within .nav-dropdown-menu{display:block}',
    '.nav-dropdown-menu-inner a{display:block;padding:9px 12px;border-radius:6px;color:var(--muted);font-size:.9rem;font-weight:500;text-decoration:none;white-space:nowrap;transition:background .12s,color .12s}',
    '.nav-dropdown-menu-inner a:hover{background:rgba(255,255,255,.05);color:var(--text)}',
    '.nav-dropdown-menu-inner a[aria-current="page"]{color:var(--green-lt)}',
    /* ── hamburger button (mobile only) ── */
    '.nav-burger{display:none;background:none;border:none;cursor:pointer;padding:6px;color:var(--muted);flex-shrink:0}',
    '.nav-burger:hover{color:var(--text)}',
    /* ── mobile drawer ── */
    '.nav-mobile{display:none;position:fixed;inset:0;z-index:300;flex-direction:column}',
    '.nav-mobile.open{display:flex}',
    '.nav-mobile-backdrop{position:absolute;inset:0;background:rgba(0,0,0,.6)}',
    '.nav-mobile-panel{position:relative;margin-left:auto;width:min(300px,85vw);height:100%;background:var(--card);border-left:1px solid var(--border);display:flex;flex-direction:column;overflow-y:auto}',
    '.nav-mobile-head{display:flex;align-items:center;justify-content:space-between;padding:18px 20px;border-bottom:1px solid var(--border)}',
    '.nav-mobile-close{background:none;border:none;cursor:pointer;color:var(--muted);padding:4px}',
    '.nav-mobile-close:hover{color:var(--text)}',
    '.nav-mobile-links{display:flex;flex-direction:column;padding:12px 8px}',
    '.nav-mobile-links a{display:block;padding:13px 14px;border-radius:8px;color:var(--text);font-size:1rem;font-weight:500;text-decoration:none;transition:background .12s}',
    '.nav-mobile-links a:hover{background:rgba(255,255,255,.05)}',
    '.nav-mobile-links a[aria-current="page"]{color:var(--green-lt)}',
    '.nav-mobile-divider{height:1px;background:var(--border);margin:8px 14px}',
    /* ── breakpoint ── */
    '@media(max-width:820px){.nav-burger{display:flex;align-items:center;justify-content:center}}',
  ].join('');
  document.head.appendChild(style);

  var primary = [
    { href: '/#what',     label: "What's an Elmer" },
    { href: '/#programs', label: 'Programs' },
    { href: '/#tracks',   label: 'Tracks' },
    { href: '/courses/',  label: 'Register' },
    { href: '/donate/',   label: 'Donate' },
  ];

  var secondary = [
    { href: '/contact/',   label: 'Contact' },
    { href: '/events/',    label: 'Events' },
    { href: '/census/',    label: 'License Census' },
    { href: '/#resources', label: 'Resources' },
    { href: '/#sponsor',  label: 'Sponsor' },
    { href: 'https://solar.tavaoneeducation.org', label: 'Learn Solar' },
  ];

  var all = primary.concat(secondary);
  var path = window.location.pathname.replace(/\/?$/, '/');

  function isCurrent(href) {
    return href.indexOf('#') === -1 && href !== '/' && path.indexOf(href) === 0;
  }

  function link(l) {
    return '<a href="' + l.href + '"' + (isCurrent(l.href) ? ' aria-current="page"' : '') + '>' + l.label + '</a>';
  }

  /* ── desktop nav ── */
  var anySecCurrent = secondary.some(function (l) { return isCurrent(l.href); });
  var dropItems = secondary.map(link).join('');

  nav.innerHTML = primary.map(link).join('') +
    '<div class="nav-dropdown">' +
      '<button class="nav-dropdown-btn"' + (anySecCurrent ? ' style="color:var(--green-lt)"' : '') + '>' +
        'More' +
        '<svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true"><path d="M2 3.5 5 6.5 8 3.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
      '</button>' +
      '<div class="nav-dropdown-menu"><div class="nav-dropdown-menu-inner">' + dropItems + '</div></div>' +
    '</div>';

  /* ── hamburger button (inserted after nav, inside .bar) ── */
  var burger = document.createElement('button');
  burger.className = 'nav-burger';
  burger.setAttribute('aria-label', 'Open menu');
  burger.innerHTML = '<svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true"><path d="M3 6h16M3 11h16M3 16h16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
  nav.parentNode.appendChild(burger);

  /* ── mobile drawer ── */
  var drawer = document.createElement('div');
  drawer.className = 'nav-mobile';
  drawer.setAttribute('aria-modal', 'true');
  drawer.setAttribute('role', 'dialog');
  drawer.setAttribute('aria-label', 'Site navigation');

  var mobileLinks = primary.map(link).join('') +
    '<div class="nav-mobile-divider"></div>' +
    secondary.map(link).join('');

  drawer.innerHTML =
    '<div class="nav-mobile-backdrop"></div>' +
    '<div class="nav-mobile-panel">' +
      '<div class="nav-mobile-head">' +
        '<span style="font-family:var(--mono);font-size:.85rem;color:var(--muted);">Menu</span>' +
        '<button class="nav-mobile-close" aria-label="Close menu">' +
          '<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M4 4l12 12M16 4L4 16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>' +
        '</button>' +
      '</div>' +
      '<nav class="nav-mobile-links" aria-label="Mobile navigation">' + mobileLinks + '</nav>' +
    '</div>';

  document.body.appendChild(drawer);

  function openDrawer() {
    drawer.classList.add('open');
    document.body.style.overflow = 'hidden';
    drawer.querySelector('.nav-mobile-close').focus();
  }

  function closeDrawer() {
    drawer.classList.remove('open');
    document.body.style.overflow = '';
    burger.focus();
  }

  burger.addEventListener('click', openDrawer);
  drawer.querySelector('.nav-mobile-backdrop').addEventListener('click', closeDrawer);
  drawer.querySelector('.nav-mobile-close').addEventListener('click', closeDrawer);

  // Close on link click (hash links stay on page)
  drawer.querySelectorAll('a').forEach(function (a) {
    a.addEventListener('click', closeDrawer);
  });

  // Close on Escape
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && drawer.classList.contains('open')) closeDrawer();
  });
}());
