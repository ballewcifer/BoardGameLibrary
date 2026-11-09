---
name: setup-new-machine
description: Fully set up Board Game Library (desktop/web + mobile) on a new machine — clone both repos outside any cloud-sync folder, install dependencies, verify GitHub/EAS auth, and place store submission credentials. Use when setting up development on a new computer, or when the user asks to set up/onboard a new machine for this project.
---

# Set up Board Game Library on a new machine

This project spans two GitHub repos: desktop/web (`BoardGameLibrary`, this
repo) and mobile (`BoardGameLibraryMobile`). This skill brings a new machine
to full parity with an existing dev machine — cloned repos, installed
dependencies, and verified access to GitHub, EAS, and (optionally) the app
stores.

## Bootstrap (only if this repo isn't cloned on this machine yet)

```bash
git clone https://github.com/ballewcifer/BoardGameLibrary.git C:\Dev\BoardGameLibrary
cd C:\Dev\BoardGameLibrary
```

Everything below runs from inside that clone. If the user is already running
this skill from within a clone of this repo, skip straight to step 1.

## Why not OneDrive/Dropbox/iCloud/etc.

Never clone into a cloud-sync folder. Git is the sync mechanism for this
project (`git pull` / `git push` between machines) — file-sync tools fight
git's internals (`.git/`, `node_modules/`) and will silently upload the
`credentials/` secrets (Apple/Google store keys) to that cloud provider. If
the user gives a path under OneDrive/Dropbox/Google Drive/iCloud, flag it and
suggest a plain local path (e.g. `C:\Dev\`) instead — don't proceed silently.

## Steps

1. **Run the automated setup script:**
   ```bash
   powershell -ExecutionPolicy Bypass -File scripts\setup-new-machine.ps1
   ```
   (add `-DevRoot <path>` to use somewhere other than `C:\Dev`). This clones
   or updates both repos, installs Python deps (desktop/web: pyinstaller,
   pillow, certifi, keyring, plus `requirements-web.txt`) and npm deps
   (mobile), and reports GitHub CLI / EAS CLI auth status. Read its output —
   every line is OK, WARN, or FAIL.

2. **Resolve any WARN/FAIL from the script, in order:**
   - Missing tool (git/node/npm/python) → tell the user what to install; stop
     until it's fixed, since nothing else will work.
   - `gh auth login` → run it if GitHub CLI isn't authenticated (needed to
     push, and to manage repo secrets like `BGG_APP_TOKEN`).
   - `npx eas-cli login` → run it if EAS isn't authenticated (needed to
     trigger mobile builds).

3. **Store submission credentials — only if this machine should be able to
   submit releases.** Skip this whole step for a machine that's just writing
   code; ask the user which they want.
   - Ask the user for the **local file path** to their existing Apple App
     Store Connect API key (`AuthKey_<KeyID>.p8`) and Google Play service
     account key (`.json`). These are one-time-downloadable secrets — never
     ask the user to paste file contents into chat, only the path (same
     pattern as finding the BGG token: ask where it's already saved).
   - Copy them into `BoardGameLibraryMobile\credentials\`:
     - Apple key → `credentials\AuthKey_<KeyID>.p8`
     - Play key → `credentials\google-play-service-account.json`
   - If the Apple Key ID doesn't match what's already in
     `BoardGameLibraryMobile\eas.json` under
     `submit.production.ios.ascApiKeyPath` / `ascApiKeyId`, update those two
     fields (and `ascApiKeyIssuerId` if it changed too) to match the new file.
   - Confirm both files are gitignored (`git check-ignore <path>`) before
     moving on — they must never be committed.
   - Validate each key actually authenticates, read-only, before trusting it
     (don't just check the file exists):
     - **Apple:** sign a short-lived ES256 JWT with the key
       (`iss`=issuer ID, `kid`=key ID, `aud`=`appstoreconnect-v1`) and call
       `GET https://api.appstoreconnect.apple.com/v1/apps` with
       `Authorization: Bearer <jwt>`. Expect HTTP 200 and the app
       (`com.ballewcifer.boardgamelibrary`) present in the results.
     - **Google:** build a JWT-bearer assertion from the service account
       (`iss`=`client_email`, `scope`=
       `https://www.googleapis.com/auth/androidpublisher`,
       `aud`=`https://oauth2.googleapis.com/token`), sign it RS256 with the
       account's `private_key`, and POST it to
       `https://oauth2.googleapis.com/token`
       (`grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer`). Expect
       HTTP 200 with an `access_token` in the response.
     Node's built-in `crypto` + `fetch` can do both without extra
     dependencies — write a small throwaway script (see this project's
     session history for a worked example), run it, then discard it. Never
     print the token/key contents, only the HTTP status and pass/fail.

4. **The BGG API token needs no local setup.** It's embedded at build time
   from GitHub Actions secrets (`BGG_APP_TOKEN`, in both repos' secrets) and
   an EAS environment variable (`EXPO_PUBLIC_BGG_TOKEN`, in the mobile
   project) — never a local `.env` or per-machine config. A code-only machine
   doesn't need it at all; don't ask the user for it unless they're
   specifically debugging BGG auth.

5. **Report a clear summary** to the user: what's fully working (repos,
   dependencies, GitHub, EAS), what's optional and still pending (store
   credentials, if skipped), and any manual step still outstanding. Don't
   claim something works without having verified it in the steps above.

## Notes for maintaining this skill

- `scripts/setup-new-machine.ps1` is idempotent — re-running it on a machine
  that already has both repos just pulls latest and re-verifies rather than
  re-cloning or failing.
- If the project's dependency list changes (a new Python package for
  desktop/web, a new required CLI tool), update both this file and the
  script together so they stay in sync.
- `eas.json`'s `submit.production` block is the single source of truth for
  which credential filenames/IDs are expected — read it rather than assuming
  the names used in this file, in case it's changed since this was written.
