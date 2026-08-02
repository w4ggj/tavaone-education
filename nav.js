(function () {
  var nav = document.getElementById('site-nav');
  if (!nav) return;

  var links = [
    { href: '/#what',     label: "What’s an Elmer" },
    { href: '/#lab',      label: 'STEM Lab' },
    { href: '/#programs', label: 'Programs' },
    { href: '/#tracks',   label: 'Tracks' },
    { href: '/#sponsor',  label: 'Sponsor' },
    { href: '/#resources',label: 'Resources' },
    { href: '/events/',   label: 'Events' },
    { href: '/census/',   label: 'License Census' },
    { href: '/courses/',  label: 'Courses' },
    { href: '/donate/',   label: 'Donate' },
  ];

  var path = window.location.pathname.replace(/\/?$/, '/'); // normalize trailing slash

  nav.innerHTML = links.map(function (l) {
    // Only mark page-level links (not hash anchors) as current
    var current = l.href.indexOf('#') === -1 &&
                  l.href !== '/' &&
                  path.indexOf(l.href) === 0;
    return '<a href="' + l.href + '"' + (current ? ' aria-current="page"' : '') + '>' + l.label + '</a>';
  }).join('');
}());
