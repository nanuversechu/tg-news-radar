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

# 1. Ask the running radar for the current board. Fails loudly if it is down.
python3 -m radar snapshot

# A truncated or empty file must never reach the web.
if [ ! -s "$PAGE" ] || [ "$(stat -c%s "$PAGE")" -lt 20000 ]; then
  echo "publish: $PAGE is missing or implausibly small — not publishing" >&2
  exit 1
fi
grep -q "SNAPSHOT_TAKEN" "$PAGE" || { echo "publish: page is not a snapshot — not publishing" >&2; exit 1; }

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
