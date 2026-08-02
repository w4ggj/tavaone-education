(function () {
  var nav = document.getElementById('site-nav');
  if (!nav) return;

  // Inject dropdown styles once
  var style = document.createElement('style');
  style.textContent = [
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
  ].join('');
  document.head.appendChild(style);

  var primary = [
    { href: '/#what',     label: "What's an Elmer" },
    { href: '/#lab',      label: 'STEM Lab' },
    { href: '/#programs', label: 'Programs' },
    { href: '/#tracks',   label: 'Tracks' },
    { href: '/#sponsor',  label: 'Sponsor' },
    { href: '/donate/',   label: 'Donate' },
  ];

  var secondary = [
    { href: '/courses/',  label: 'Courses' },
    { href: '/events/',   label: 'Events' },
    { href: '/census/',   label: 'License Census' },
    { href: '/#resources',label: 'Resources' },
  ];

  var path = window.location.pathname.replace(/\/?$/, '/');

  function isCurrent(href) {
    return href.indexOf('#') === -1 && href !== '/' && path.indexOf(href) === 0;
  }

  var html = primary.map(function (l) {
    return '<a href="' + l.href + '"' + (isCurrent(l.href) ? ' aria-current="page"' : '') + '>' + l.label + '</a>';
  }).join('');

  // Check if any secondary item is current (to highlight the dropdown button)
  var anySecCurrent = secondary.some(function (l) { return isCurrent(l.href); });

  var dropItems = secondary.map(function (l) {
    return '<a href="' + l.href + '"' + (isCurrent(l.href) ? ' aria-current="page"' : '') + '>' + l.label + '</a>';
  }).join('');

  html += '<div class="nav-dropdown">' +
    '<button class="nav-dropdown-btn"' + (anySecCurrent ? ' style="color:var(--green-lt)"' : '') + '>' +
    'More' +
    '<svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true"><path d="M2 3.5 5 6.5 8 3.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
    '</button>' +
    '<div class="nav-dropdown-menu"><div class="nav-dropdown-menu-inner">' + dropItems + '</div></div>' +
    '</div>';

  nav.innerHTML = html;
}());
