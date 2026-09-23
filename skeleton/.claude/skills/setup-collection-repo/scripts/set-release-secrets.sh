#!/usr/bin/env bash
# SPDX-FileCopyrightText: Silex Data Solutions
# SPDX-License-Identifier: Apache-2.0
#
# Store RELEASE_TOKEN and GALAXY_API_KEY as repository secrets for OWNER/REPO
# without either value ever appearing on a command line, in any output, in
# shell history or in a file.
#
# Each value is read from the environment variable of the same name if set;
# otherwise, when run from a terminal, it is prompted for with echo off.
# Values leave this script only through the stdin of `gh secret set`, and the
# release token is validated through the GH_TOKEN environment variable of a
# single `gh` call - never as a command-line argument, which any user on the
# machine could read from the process list. `printf` is a shell builtin, so
# piping from it spawns no process carrying the value either.
#
# Usage: bash set-release-secrets.sh OWNER/REPO
set -euo pipefail
set +x # a traced command line would print the secret

repo="${1:?usage: set-release-secrets.sh OWNER/REPO}"

die() {
  echo "error: $*" >&2
  exit 1
}

# Check the operator's own gh login can manage secrets here before asking for
# anything, so nobody types a token only to hit a permission error.
admin=$(gh api "repos/${repo}" --jq .permissions.admin) ||
  die "cannot read ${repo} with your gh login (is it authenticated?)"
[ "$admin" = "true" ] || die "your gh login is not an admin of ${repo}; setting repository secrets needs admin"

obtain() {
  local name="$1" value
  if [ -n "${!name:-}" ]; then
    return 0
  fi
  if [ -t 0 ] && [ -r /dev/tty ]; then
    IFS= read -rs -p "${name}: " value </dev/tty
    printf '\n' >&2
    [ -n "$value" ] || die "no value entered for ${name}"
    printf -v "$name" '%s' "$value"
    value=
    return 0
  fi
  cat >&2 <<MSG
error: ${name} is not set, and there is no terminal to prompt on.
Run this script yourself in a terminal - it prompts with echo off - or first run
  read -rs ${name} && export ${name}
in the shell that launches it. Never paste the value into a chat or a command.
MSG
  exit 1
}

obtain RELEASE_TOKEN
obtain GALAXY_API_KEY

# Who the release token acts as. The login itself is not secret, and it is
# needed for the branch-protection bypass (configure-repo.sh protect).
release_login=$(GH_TOKEN="$RELEASE_TOKEN" gh api user --jq .login) ||
  die "GitHub rejected RELEASE_TOKEN (expired, revoked or mistyped)"
can_push=$(GH_TOKEN="$RELEASE_TOKEN" gh api "repos/${repo}" --jq .permissions.push) ||
  die "RELEASE_TOKEN (acting as ${release_login}) cannot see ${repo}"
[ "$can_push" = "true" ] ||
  die "${release_login} has no push access to ${repo}; the release workflow pushes its release commit and tag"

# The secrets are written with the operator's gh login, not the token.
printf '%s' "$RELEASE_TOKEN" | gh secret set RELEASE_TOKEN --repo "$repo"
printf '%s' "$GALAXY_API_KEY" | gh secret set GALAXY_API_KEY --repo "$repo"
RELEASE_TOKEN=
GALAXY_API_KEY=

echo
echo "RELEASE_TOKEN acts as: ${release_login}"
echo "Next: bash configure-repo.sh protect ${repo} ${release_login}"
echo
echo "Note: push access above is ${release_login}'s own role on the repo. For a"
echo "fine-grained token, also confirm the token itself grants Contents: read and write."
echo "If you exported either value in your shell, run 'unset RELEASE_TOKEN GALAXY_API_KEY'."
