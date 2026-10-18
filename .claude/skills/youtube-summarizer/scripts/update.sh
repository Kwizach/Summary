#!/usr/bin/env bash
# Update the youtube-summarizer skill from its upstream GitHub source.
# Re-fetches skills/youtube-summarizer from the repo's main branch and
# overwrites the local copy. WARNING: this clobbers any local edits.

set -e

REPO="https://github.com/sickn33/antigravity-awesome-skills.git"
SUBDIR="skills/youtube-summarizer"
# Destination = the skill directory this script lives in (its parent's parent).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"          # .../skills/youtube-summarizer
SKILLS_ROOT="$(dirname "$SKILL_DIR")"          # .../skills

echo "🔄 Updating youtube-summarizer from $REPO ..."

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# This script is local-only (not shipped upstream), so back it up before we
# wipe the skill dir, then restore it afterward — otherwise it deletes itself.
SELF="$SCRIPT_DIR/update.sh"
cp "$SELF" "$TMP/update.sh.bak"

git clone --depth 1 --filter=blob:none --sparse "$REPO" "$TMP" >/dev/null 2>&1
git -C "$TMP" sparse-checkout set "$SUBDIR" >/dev/null 2>&1

if [ ! -d "$TMP/$SUBDIR" ]; then
    echo "❌ Could not find $SUBDIR in the upstream repo."
    exit 1
fi

rm -rf "$SKILL_DIR"
cp -R "$TMP/$SUBDIR" "$SKILL_DIR"

# Restore this updater script, which is not part of the upstream repo.
mkdir -p "$SCRIPT_DIR"
cp "$TMP/update.sh.bak" "$SELF"
chmod +x "$SELF"

echo "✅ Updated. Current version:"
grep -m1 -E '^##|version' "$SKILL_DIR/CHANGELOG.md" 2>/dev/null || true
echo "ℹ️  Restart Claude Code so the updated skill is re-discovered."
