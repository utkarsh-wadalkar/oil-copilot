#!/usr/bin/env bash
# Apply the tracked nao sidecar patches to a pinned checkout (Task 3N).
#
# POSIX mirror of setup-nao.ps1's patch step, for CI/containers without PowerShell.
# Idempotent: a patch already present in the working tree is detected and skipped.
#
#   infra/nao/patch/apply-patches.sh [target-checkout]
#
# Default target is ../../../vendor/nao relative to this script.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
target="${1:-$here/../../../vendor/nao}"
target="$(cd "$target" && pwd)"

if [ ! -d "$target/.git" ]; then
  echo "apply-patches: $target is not a git checkout" >&2
  exit 1
fi

shopt -s nullglob
patches=("$here"/*.patch)
if [ ${#patches[@]} -eq 0 ]; then
  echo "apply-patches: no *.patch files in $here" >&2
  exit 1
fi

for patch in "${patches[@]}"; do
  name="$(basename "$patch")"
  if git -C "$target" apply --check --reverse "$patch" >/dev/null 2>&1; then
    echo "apply-patches: $name already applied; skipping"
    continue
  fi
  if ! git -C "$target" apply --check "$patch" >/dev/null 2>&1; then
    echo "apply-patches: $name does NOT apply cleanly to $target" >&2
    exit 1
  fi
  git -C "$target" apply "$patch"
  echo "apply-patches: applied $name"
done

echo "apply-patches: done"
