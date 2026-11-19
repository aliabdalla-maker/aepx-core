#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: deploy-aepx-root.sh <source-dir> <40-char-git-sha>" >&2
  exit 64
fi

SOURCE="$(realpath "$1")"
SHA="$2"
ROOT=/srv/aepx
RELEASES="$ROOT/releases"
RELEASE="$RELEASES/$SHA"
CURRENT="$ROOT/current"

[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "invalid git sha" >&2; exit 65; }
[[ -d "$SOURCE" ]] || { echo "source directory missing" >&2; exit 66; }
[[ "$SOURCE" == */platform/ecosystem-tracker ]] || { echo "unexpected source path" >&2; exit 67; }
[[ -f "$SOURCE/index.html" ]] || { echo "index.html missing" >&2; exit 68; }
[[ -f "$SOURCE/data/portals.json" ]] || { echo "portals.json missing" >&2; exit 69; }

# Reject symlinks in deploy input so a repository checkout cannot make the
# privileged copy follow links outside the intended static application tree.
if find "$SOURCE" -type l -print -quit | grep -q .; then
  echo "deployment source must not contain symlinks" >&2
  exit 70
fi

install -d -m 0755 "$ROOT" "$RELEASES"
rm -rf -- "$RELEASE"
install -d -m 0755 "$RELEASE"
rsync -a --delete --safe-links "$SOURCE/" "$RELEASE/"
find "$RELEASE" -type d -exec chmod 0755 {} +
find "$RELEASE" -type f -exec chmod 0644 {} +

ln -sfn "releases/$SHA" "$ROOT/current.next"
mv -Tf "$ROOT/current.next" "$CURRENT"

# Retain the five newest versioned releases for fast rollback.
mapfile -t old < <(find "$RELEASES" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' | sort -nr | awk 'NR>5 {$1=""; sub(/^ /,""); print}')
if ((${#old[@]})); then
  rm -rf -- "${old[@]}"
fi

test -f "$CURRENT/index.html"
test -f "$CURRENT/data/portals.json"
printf 'AEP-X release %s active at %s\n' "$SHA" "$CURRENT"
