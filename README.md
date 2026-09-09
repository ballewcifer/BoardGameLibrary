# Board Game Library

A self-hosted **board game library manager** — catalog your collection, **lend games to members** (check-out / check-in with due dates), log plays, and **compare multiple collections**. No account, no subscription, your data stays local.

> The mobile (Expo/React Native) app lives in its own repo: **[BoardGameLibraryMobile](https://github.com/ballewcifer/BoardGameLibraryMobile)**.

## Apps in this repo
- **Desktop** — Python / Tkinter (`app.pyw`), packaged as a Windows `.exe` and macOS `.dmg`.
- **Web** — Flask PWA (`web/`); self-host on your network and open it on any phone, tablet, or laptop.

Both share the same local SQLite database and the `db.py` / `bgg.py` / `config.py` modules.

## Features
- **BoardGameGeek sync** — import your collection by username (public, or private via login), including wishlist, for-trade, preordered and other BGG collection statuses, not just what you own. Read-only on Web and Mobile. On **Desktop**, an opt-in setting can also post plays you log here back to your BGG account (off by default; your BGG password is used once per post and never stored).
- **Add games** via BGG search, or import a BGG collection export CSV (desktop)
- **Cooperative / Competitive** game type — auto-detected from BGG mechanics, editable per game, and usable as a filter
- **Expansions** automatically link to their base game — "Expansion for X" on the expansion, "Expansions You Own" on the base game
- **Browse** — card and table views with filters (players, best-at, play time, complexity, status, tags, favorites, cooperative/competitive, BGG collection status) and sort
- **"Surprise Me"** random game picker, filtered by players, time, complexity, and game type
- **Lending** — check games out to named **members**, with due dates, overdue flags, and full loan history
- **Multi-collection** — sync several BGG users and compare libraries: *shared by all*, *unique to one*, or *in A but not B* (desktop, web)
- **Play log** — date, players, winner, duration, scores → win leaderboard + dashboard stats
- Favorites, tags, custom cover photos, and 3D-insert badges
- **Offline** — local SQLite, with backup export / import (including custom photos and per-game customizations)

## How it compares
| Capability | BG Stats | BG Catalog | **Board Game Library** |
|---|---|---|---|
| Platforms | iOS, Android | iOS, Android | **Windows, macOS, LAN web, iOS, Android** |
| BGG collection sync | ✅ | ✅* | ✅ (all statuses — owned, wishlist, for trade, etc.) |
| Deep play stats (H-index, charts, scoring rules) | ✅✅ | basic | basic |
| Ownership / wishlist statuses | partial | ✅✅ | ✅ synced from BGG, plus favorites + tags |
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
