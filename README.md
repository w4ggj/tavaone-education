# TavaOne // Education — The Elmers Site

A static site that connects new and aspiring amateur radio operators with experienced
**Elmers** (mentors), offering structured learning tracks, a mentor-matching request form,
and curated resources.

## Contents

| File | Purpose |
|------|---------|
| `index.html` | Single-page site: hero, "What's an Elmer", learning tracks, featured book, resources |
| `style.css` | TavaOne brand system (dark theme, `#10b981` green, Plus Jakarta Sans + JetBrains Mono) |
| `favicon.ico` | Shared TavaOne favicon |
| `images/` | Site imagery (book cover, etc.) |

## Learning tracks

1. **Technician License Course** — complete beginner to licensed operator in four sessions
2. **POTA & Field Operating** — take the radio outdoors
3. **Digital Modes** — FT8, FT4, JS8 and beyond

## Develop / preview

It's a static site — open `index.html` directly, or serve locally:

```bash
python3 -m http.server 8000
# then visit http://localhost:8000
```

## Deploy

Designed for GitHub Pages or Netlify, like its companion app
[TavaOne Activate](https://activate.tavaone.com/). Point a custom domain
(e.g. `education.tavaone.com`) at the deployment.

> Mentorship requests currently route to `elmers@tavaone.com` via the "Ask an Elmer" links.
