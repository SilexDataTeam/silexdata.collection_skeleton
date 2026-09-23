#!/usr/bin/env bash
# SPDX-FileCopyrightText: Silex Data Solutions
# SPDX-License-Identifier: Apache-2.0
#
# Repository settings a template copy does not carry over. Handles no secrets -
# for those, see set-release-secrets.sh.
#
# Usage:
#   bash configure-repo.sh pages       OWNER/REPO
#   bash configure-repo.sh protect     OWNER/REPO RELEASE_LOGIN [APPROVALS]
#   bash configure-repo.sh lock-checks OWNER/REPO PR_NUMBER
#   bash configure-repo.sh status      OWNER/REPO
set -euo pipefail

RULESET_NAME="protect-default-branch"

# The fixed-name checks the ruleset requires. Each is "<caller job id> /
# <reusable job name>" and deliberately excludes matrix legs, whose names
# change with the ansible-core matrix. The nox and coverage entries are
# dedicated result gates that fail explicitly when anything they depend on
# failed: GitHub reports a *skipped* job as passing a required check, so
# requiring any ordinary job that is skipped on failure would let a broken PR
# merge.
REQUIRED_CHECKS=(
  "lint / pre-commit (lint)"
  "nox / Nox result"
  "coverage / Coverage result"
  "docs / Build collection documentation"
  "changelog / Require a changelog fragment"
)

die() {
  echo "error: $*" >&2
  exit 1
}
usage() {
  sed -n '8,12p' "$0" >&2
  exit 2
}

require_admin() {
  local admin
  admin=$(gh api "repos/$1" --jq .permissions.admin) || die "cannot read $1 with your gh login"
  [ "$admin" = "true" ] || die "your gh login is not an admin of $1"
}

# Current Pages build type, or empty if Pages is not enabled. On an HTTP error
# `gh api` prints the error body to stdout even with --jq, so branch on the exit
# status and discard the output rather than capturing it with `|| true`.
pages_build_type() {
  local out
  if out=$(gh api "repos/$1/pages" --jq .build_type 2>/dev/null); then
    printf '%s' "$out"
  fi
}

# Every `gh` call whose output is captured ends in `|| die`: under `set -e` a
# failing command substitution would otherwise end the script silently.
existing_ruleset_id() {
  gh api "repos/$1/rulesets" --jq ".[] | select(.name == \"${RULESET_NAME}\") | .id" ||
    die "cannot list rulesets on $1"
}

cmd_pages() {
  local repo="$1" current
  require_admin "$repo"
  current=$(pages_build_type "$repo")
  if [ -z "$current" ]; then
    gh api -X POST "repos/${repo}/pages" -f build_type=workflow >/dev/null
    echo "GitHub Pages enabled, built by GitHub Actions."
  elif [ "$current" != "workflow" ]; then
    gh api -X PUT "repos/${repo}/pages" -f build_type=workflow >/dev/null
    echo "GitHub Pages switched from '${current}' to GitHub Actions builds."
  else
    echo "GitHub Pages already built by GitHub Actions; nothing to do."
  fi
}

cmd_protect() {
  local repo="$1" login="$2" approvals="${3:-0}" actor_id rid existing body
  require_admin "$repo"
  actor_id=$(gh api "users/${login}" --jq .id) || die "no GitHub user '${login}'"
  rid=$(existing_ruleset_id "$repo")
  existing='{}'
  if [ -n "$rid" ]; then
    existing=$(gh api "repos/${repo}/rulesets/${rid}") || die "cannot read ruleset ${rid}"
  fi

  # Built in Python so the JSON is well formed; required status checks already
  # locked in by `lock-checks` are carried over rather than dropped.
  body=$(EXISTING="$existing" ACTOR_ID="$actor_id" APPROVALS="$approvals" NAME="$RULESET_NAME" python3 - <<'PY'
import json, os
existing = json.loads(os.environ["EXISTING"])
kept = [r for r in existing.get("rules", []) if r.get("type") == "required_status_checks"]
print(json.dumps({
    "name": os.environ["NAME"],
    "target": "branch",
    "enforcement": "active",
    "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
    # Only the release identity may push straight to the default branch: the
    # release workflow's release commit and tag. Everyone else goes via PR.
    "bypass_actors": [
        {"actor_id": int(os.environ["ACTOR_ID"]), "actor_type": "User", "bypass_mode": "always"}
    ],
    "rules": [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {"type": "pull_request", "parameters": {
            "required_approving_review_count": int(os.environ["APPROVALS"]),
            "dismiss_stale_reviews_on_push": False,
            "require_code_owner_review": False,
            "require_last_push_approval": False,
            "required_review_thread_resolution": False,
        }},
    ] + kept,
}))
PY
)
  if [ -n "$rid" ]; then
    gh api -X PUT "repos/${repo}/rulesets/${rid}" --input - <<<"$body" >/dev/null
    echo "Updated ruleset '${RULESET_NAME}' on ${repo}."
  else
    gh api -X POST "repos/${repo}/rulesets" --input - <<<"$body" >/dev/null
    echo "Created ruleset '${RULESET_NAME}' on ${repo}."
  fi
  echo "The default branch now requires a PR (${approvals} approvals); ${login} may bypass, for releases."
  echo "Required checks are added separately, once they have reported: configure-repo.sh lock-checks"
}

cmd_lock_checks() {
  local repo="$1" pr="$2" sha rid runs missing=0 app_id="" name
  require_admin "$repo"
  rid=$(existing_ruleset_id "$repo")
  [ -n "$rid" ] || die "no '${RULESET_NAME}' ruleset yet; run 'configure-repo.sh protect' first"
  sha=$(gh pr view "$pr" --repo "$repo" --json headRefOid --jq .headRefOid) ||
    die "cannot read PR #${pr} on ${repo}"
  runs=$(gh api "repos/${repo}/commits/${sha}/check-runs?per_page=100" \
    --jq '.check_runs[] | [.name, (.conclusion // "pending"), (.app.id | tostring)] | @tsv') ||
    die "cannot read check runs for ${sha}"

  # Refuse to require a check that has not been seen passing: a required
  # check that never reports blocks every PR.
  for name in "${REQUIRED_CHECKS[@]}"; do
    local line
    line=$(awk -F'\t' -v n="$name" '$1 == n' <<<"$runs" | head -n1)
    if [ -z "$line" ]; then
      echo "  missing: ${name}" >&2
      missing=1
    elif [ "$(cut -f2 <<<"$line")" != "success" ]; then
      echo "  not passing ($(cut -f2 <<<"$line")): ${name}" >&2
      missing=1
    else
      app_id=$(cut -f3 <<<"$line")
    fi
  done
  if [ "$missing" -ne 0 ]; then
    echo "Checks reported on PR #${pr} (${sha:0:8}):" >&2
    cut -f1,2 <<<"$runs" | sed 's/^/    /' >&2
    die "not locking in required checks until every one above has passed on this PR"
  fi

  gh api "repos/${repo}/rulesets/${rid}" |
    CHECKS="$(printf '%s\n' "${REQUIRED_CHECKS[@]}")" APP_ID="$app_id" python3 -c '
import json, os, sys
rs = json.load(sys.stdin)
rules = [r for r in rs["rules"] if r["type"] != "required_status_checks"]
rules.append({"type": "required_status_checks", "parameters": {
    # Pinning integration_id to the GitHub Actions app stops anything else
    # satisfying a required check by posting a status with the same name.
    "required_status_checks": [
        {"context": c, "integration_id": int(os.environ["APP_ID"])}
        for c in os.environ["CHECKS"].splitlines() if c
    ],
    "strict_required_status_checks_policy": False,
    "do_not_enforce_on_create": False,
}})
print(json.dumps({k: rs[k] for k in ("name", "target", "enforcement", "conditions", "bypass_actors")} | {"rules": rules}))
' | gh api -X PUT "repos/${repo}/rulesets/${rid}" --input - >/dev/null
  echo "Locked in ${#REQUIRED_CHECKS[@]} required checks on '${RULESET_NAME}':"
  printf '  %s\n' "${REQUIRED_CHECKS[@]}"
}

cmd_status() {
  local repo="$1" rid
  echo "Secrets (names only):"
  gh secret list --repo "$repo" | sed 's/^/  /' || true
  local build
  build=$(pages_build_type "$repo")
  echo "Pages: ${build:-not enabled}"
  rid=$(existing_ruleset_id "$repo")
  if [ -n "$rid" ]; then
    echo "Ruleset '${RULESET_NAME}':"
    gh api "repos/${repo}/rulesets/${rid}" \
      --jq '"  enforcement: \(.enforcement)", "  rules: \([.rules[].type] | join(", "))", "  bypass: \([.bypass_actors[] | "\(.actor_type) \(.actor_id)"] | join(", "))", "  required checks: \([.rules[] | select(.type == "required_status_checks") | .parameters.required_status_checks[].context] | join("; "))"'
  else
    echo "Ruleset '${RULESET_NAME}': not created"
  fi
}

[ $# -ge 2 ] || usage
sub="$1"
shift
case "$sub" in
pages) [ $# -eq 1 ] || usage; cmd_pages "$@" ;;
protect) [ $# -ge 2 ] || usage; cmd_protect "$@" ;;
lock-checks) [ $# -eq 2 ] || usage; cmd_lock_checks "$@" ;;
status) [ $# -eq 1 ] || usage; cmd_status "$@" ;;
*) usage ;;
esac
