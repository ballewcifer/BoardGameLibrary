# Release Notes

## Desktop/Web v7.1.1 - "In Collection" fix

- **Games with no status checked on BoardGameGeek are no longer imported as Owned.** BGG keeps a game in your collection (shown as "In Collection") when you only rated, commented on or played it, even if none of Own, Wishlist, etc. is ticked. Those games used to show up as Owned and could be checked out. They now import with an "In Collection" label and a neutral grey badge, are not loanable, and can be filtered and edited like any other status. Set a real status on the game if you do own it.
- **Duplicate rows merged.** If BGG lists the same game more than once in your collection, the statuses are now combined (Owned still wins) instead of the last row winning.
- **To correct games already in your library, run a sync again.** A status you changed by hand in the app is left alone.

---

## Desktop/Web v7.1.0 - "Not played yet"

- **Mark games you own but haven't played.** It is your call, not automatic: a game with no plays in the app may still have been played before you started using it. Mark a game "Not played yet" and it stays marked until you log a play for it, which clears the mark for you.
- **Desktop**: a "Not played yet" checkbox in the game's details window (shown only for owned games with no plays), plus right-click items to mark or clear one game, or several selected rows at once. Games that can't be marked (already played, or not owned) are skipped and you are told how many. The Games table has a new sortable "Unplayed" column, cards show an "UNPLAYED" tag on the cover, and the details window shows a "Not played yet - Log a play to clear" banner.
- **Web**: the same checkbox in Edit Game, an "Unplayed" / "Played" button in Select mode (it flips to "Played" when every selected game is already marked), an "UNPLAYED" corner ribbon on game cards, and the banner on the game page. The colour follows your chosen theme, and the text stays readable in all of them.
- **Filter and Surprise Me**: a "Not played yet" filter on the Games screen, and an "Only games I haven't played" option on the random game picker (off by default), on both desktop and web.
- **Backups** carry the mark, and older backups without it still restore. A restored mark is dropped for any game that has plays, so it can never contradict your play log.

---


Covers Desktop/Web **v6.9.0 → v6.9.5** and Mobile **v2.2.8 → v2.5.4** (2026-08-04 to 2026-08-24).

This file is duplicated in the companion [BoardGameLibrary](https://github.com/ballewcifer/BoardGameLibrary) repo (Desktop/Web) since most of this window's work spanned all three platforms.

---

## Onboarding & getting started (Mobile)

- Added a first-launch splash screen explaining what the app does and how to get started — shown once. (v2.5.0)
- The Dashboard now shows a "Let's build your library" prompt when your library is empty, instead of a blank page with no next step. Tapping it offers a choice of syncing BoardGameGeek, scanning a barcode, or adding a game manually. (v2.5.0)
- BoardGameGeek sync now runs automatically once every 24 hours in the background when a username is configured, instead of requiring a manual tap every launch. (v2.5.0)

## Adding games

- **Mobile**: added barcode scanning as a third way to add a game — scan a box's barcode, and the app looks it up and searches BoardGameGeek for a match to confirm. (v2.5.0)
- **Mobile**: added a persistent "+" button to add a game on the Games tab (previously only reachable via the "⋯" menu); later changed from a floating button to a header icon button matching the same style already used on the Plays tab. (v2.3.3, v2.5.4)
- **Desktop**: added a persistent "+ Add Game" toolbar button (previously menu-only via Library → Add Game…). (v6.9.2)

## "Members" renamed to "Friends"

Renamed throughout all three platforms' UI — tab labels, buttons, alerts, empty states, table headers — since testers found "Members" confusing for what's really "who you lend games to." Internal code and database field names are unchanged. (v2.5.0, v6.9.4)

## Crash & error reporting (Mobile)

Added Sentry crash/error reporting after a TestFlight tester hit an unrecoverable first-launch crash with no diagnostic information available. Now paired with a proper error-boundary fallback screen. Disclosed in the app's privacy policy and store listings. (v2.3.1)

## Dashboard cleanup

Recent Plays and Most Played were each a single cramped line mixing date/name/winner or rank/name/count. Recent Plays now shows the game name on its own line with date and winner below; Most Played gets an aligned rank column matching Top Winners' row style. (v2.5.2, v6.9.5)

## Bug fixes

- **Mobile**: fixed a first-launch crash race where a screen could query the database before its tables were created, on a small percentage of fresh installs. (v2.3.2)
- **Mobile**: fixed BoardGameGeek sync reporting more games "synced" than actually appeared in the library — caused by BGG occasionally listing the same game twice in a collection, which correctly collapses to one row but was inflating the reported count. Also fixed on Desktop/Web (shared sync code). (v2.3.3, v6.9.1)
- **Mobile**: fixed a visible screen flicker on Android when opening Add Game (or several other actions) from the "⋯" menu — two native modal windows briefly overlapped. (v2.3.3)
- **Mobile**: fixed the "⋯" menu on the Games tab being able to grow taller than the screen on smaller devices or with larger text sizes, cutting off the last item ("Clear Collections…") with no way to scroll to it. (v2.5.3)
- **Mobile**: fixed a gap where a library with only one collection had no way to clear/reset it. (v2.5.1)
- **All platforms**: game titles now alphabetize the way BoardGameGeek does — ignoring a leading "The", "A", or "An" (e.g. "The Castles of Burgundy" sorts under "C"). (v2.5.0, v6.9.4)

## UI polish

- **Mobile**: the Games grid now adds columns on wider screens (tablets, landscape, unfolded foldables) instead of stretching each card wider — BGG's low-resolution thumbnails were visibly blocky when stretched on larger screens. (v2.3.4)
- **Mobile**: minor icon and floating-button sizing consistency fixes, and Friends-related copy cleanup. (v2.5.1)

## Store distribution (Mobile)

Automated App Store Connect and Google Play submissions end-to-end — `eas submit` now runs non-interactively for both platforms using stored API credentials, so a tagged release can go from build to TestFlight/Play Console without manual uploads.
