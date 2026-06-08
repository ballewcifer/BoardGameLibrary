# Board Game Library

A self-hosted **board game library manager** — catalog your collection, **lend games to members** (check-out / check-in with due dates), log plays, and **compare multiple collections**. No account, no subscription, your data stays local.

> The mobile (Expo/React Native) app lives in its own repo: **[BoardGameLibraryMobile](https://github.com/ballewcifer/BoardGameLibraryMobile)**.

## Apps in this repo
- **Desktop** — Python / Tkinter (`app.pyw`), packaged as a Windows `.exe` and macOS `.dmg`.
- **Web** — Flask PWA (`web/`); self-host on your network and open it on any phone, tablet, or laptop.

Both share the same local SQLite database and the `db.py` / `bgg.py` / `config.py` modules.

## Features
- **BoardGameGeek sync** — import your collection by username (public, or private via login)
- **Browse** — card and table views with filters (players, best-at, play time, complexity, status, tags, favorites) and sort
- **Lending** — check games out to named **members**, with due dates, overdue flags, and full loan history
- **Multi-collection** — sync several BGG users and compare libraries: *shared by all*, *unique to one*, or *in A but not B* (desktop)
- **Play log** — date, players, winner, duration, scores → win leaderboard + dashboard stats
- **Add games** via BGG search; favorites, tags, expansion and 3D-insert badges
- **Offline** — local SQLite, with backup export / import

## How it compares
| Capability | BG Stats | BG Catalog | **Board Game Library** |
|---|---|---|---|
| Platforms | iOS, Android | iOS, Android | **Windows, macOS, LAN web, Android** |
| BGG collection sync | ✅ | ✅* | ✅ |
| Deep play stats (H-index, charts, scoring rules) | ✅✅ | basic | basic |
| Ownership / wishlist statuses | partial | ✅✅ | favorites + tags |
| **Lend / check-out to members** | — | — | ✅ **unique** |
| **Compare multiple collections** | — | — | ✅ **unique** |
| Social sharing (QR, victory images) | some | ✅✅ | — |
| Account / cloud / cost | account · freemium | account · freemium | **none · self-hosted · free** |

\* BG Catalog's BGG sync has reportedly been disabled by BGG policy changes.

**What makes this one different:** it's an actual *library* — lending to members and comparing collections — and you **own and host it** across desktop + web (+ mobile), fully offline. See **[ROADMAP.md](ROADMAP.md)** for where it's headed.

## Build & release
Push a `desktop-v*` tag (e.g. `desktop-v6.3.3`) to build Windows + macOS installers and publish a GitHub Release. Version lives in `version.py`.

```bash
# bump version.py, commit, then:
git tag -a desktop-v6.3.3 -m "Desktop v6.3.3: ..."
git push origin desktop-v6.3.3
```
