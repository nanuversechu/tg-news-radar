#!/usr/bin/env bash
# Freeze the live board and publish it to GitHub Pages.
#
# Run by a systemd timer every 15 minutes, so the public link stays current
# without anyone touching it. Safe to run by hand too.
#
# The page is published on a `gh-pages` branch that is rebuilt from scratch
# every time and force-pushed: exactly one commit, no history. A 300 KB file
# committed four times an hour onto main would add gigabytes a year; this way
# the repository stays the size of one snapshot forever.
#
# Nothing is pushed unless the radar answered and produced a real page, so a
# stopped radar leaves the last good snapshot up rather than replacing it with
# an error.
set -euo pipefail
cd "$(dirname "$0")"

PAGE=docs/index.html

# The key that locks the published page. systemd supplies it; a hand run picks
# it up from .radar-key (gitignored, chmod 600). Publishing without one would
# put the whole board on the open web, so refuse rather than guess.
if [ -z "${RADAR_PAGE_KEY:-}" ] && [ -r .radar-key ]; then
  RADAR_PAGE_KEY=$(tr -d '\r\n' < .radar-key)
  export RADAR_PAGE_KEY
fi
if [ -z "${RADAR_PAGE_KEY:-}" ]; then
  echo "publish: no RADAR_PAGE_KEY and no .radar-key file — refusing to publish an unlocked board" >&2
  exit 1
fi

# 1. Ask the running radar for the current board. Fails loudly if it is down.
python3 -m radar snapshot

# A truncated or empty file must never reach the web.
if [ ! -s "$PAGE" ] || [ "$(stat -c%s "$PAGE")" -lt 20000 ]; then
  echo "publish: $PAGE is missing or implausibly small — not publishing" >&2
  exit 1
fi
# Either a plain snapshot, or the unlock form wrapping the ciphertext.
grep -qE "SNAPSHOT_TAKEN|crypto.subtle" "$PAGE" \
  || { echo "publish: page is neither a snapshot nor a locked page — not publishing" >&2; exit 1; }
# With a key set, the board must NOT be readable in the published file.
if [ -n "${RADAR_PAGE_KEY:-}" ] && grep -q "SNAPSHOT_TAKEN" "$PAGE"; then
  echo "publish: a key is set but the page is not encrypted — refusing to publish" >&2
  exit 1
fi

# 2. Build the branch with plumbing, so the working tree is never touched and
#    a half-finished publish cannot leave the repo on another branch.
: > docs/.nojekyll
BLOB=$(git hash-object -w "$PAGE")
NOJEKYLL=$(git hash-object -w docs/.nojekyll)
TREE=$(printf '100644 blob %s\t.nojekyll\n100644 blob %s\tindex.html\n' "$NOJEKYLL" "$BLOB" | git mktree)

TAKEN=$(TZ=Asia/Kolkata date '+%H:%M IST, %-d %B %Y')
COMMIT=$(GIT_AUTHOR_NAME="${GIT_AUTHOR_NAME:-nanuversechu}" \
         GIT_AUTHOR_EMAIL="${GIT_AUTHOR_EMAIL:-mayank161718@gmail.com}" \
         GIT_COMMITTER_NAME="${GIT_AUTHOR_NAME:-nanuversechu}" \
         GIT_COMMITTER_EMAIL="${GIT_AUTHOR_EMAIL:-mayank161718@gmail.com}" \
         git commit-tree "$TREE" -m "Snapshot taken $TAKEN")

git update-ref refs/heads/gh-pages "$COMMIT"
git push -q --force origin gh-pages
echo "published $TAKEN -> gh-pages ($(du -h "$PAGE" | cut -f1))"
