<!--
SPDX-FileCopyrightText: Silex Data Solutions
SPDX-License-Identifier: Apache-2.0
-->

# Architecture rules

## Facts established by testing, not assumption

These were each verified against the installed ansible-core / real GitHub
behaviour. Do not re-litigate them without new evidence.

### `ansible-galaxy collection init` mechanics

- A file is Jinja-rendered **iff** its extension is exactly `.j2` and it is not
  under `playbooks/**/templates/` or `roles/**/templates/`. The suffix is
  stripped. Everything else is byte-copied with `shutil.copyfile`.
  → **Any file containing `{{ ... }}` must be named `*.j2`,** or it ships
  unrendered.
- `.github/` **is** copied. The default skeleton-ignore is
  `["^.git$", "^.*/.git_keep$"]`; neither matches `.github`.
- Files named `.git_keep` are **dropped entirely**, not renamed. ansible-galaxy
  does recreate the empty directory, but git cannot track an empty directory,
  so it vanishes on first clone. **Use `.gitkeep`**, which is not ignored.
- `-e/--extra-vars` works and overrides the built-in placeholder data
  (`authors: your name <example@domain.com>`, `http://example.com` URLs).
  Always pass real values.
- Output lands in `<init-path>/<namespace>/<name>` — always nested, so a
  flatten step is required.
- The special dynamic `galaxy.yml.j2` handling applies **only** when no
  `--collection-skeleton` is passed. Never copy ansible's stock `galaxy.yml.j2`
  here: it references `comment_ify`/`required_config`, which exist only on the
  built-in path, and a templating failure `rmtree`s the output directory.
- `shutil.copyfile` does not preserve file modes — a script shipped in the
  skeleton arrives non-executable.

### GitHub template repositories

- Creating a repo from a template copies the **default branch's file tree
  only**, as a single initial commit with no history. Tags, releases, secrets,
  variables, environments and branch protection do **not** come along.
- There is **no "repo created from template" event**. `on: create` is
  unreliable and generated repos' workflows may arrive disabled. Bootstrap is
  therefore `workflow_dispatch`.
- Marking a repo as a template does **not** stop its workflows running in it.
  Every non-reusable workflow needs a `github.repository` guard.

### Reusable workflows

- They must live in `.github/workflows/` of the hosting repo. Subdirectories
  are not supported, symlinks are not resolved, and a git submodule there is
  invisible (it is a gitlink, not a tree of files). This is why they could not
  simply be moved to a path like `.silex/workflows/`; moving them to a separate
  *branch* was the only way to keep them out of generated repos.
- A workflow whose only trigger is `workflow_call` never runs on its own, so
  the `reusable-*.yml` files need no `github.repository` guard — they are inert
  by construction, wherever they live.
- A tag may point at a commit on any branch, so `@v1` resolving to a commit on
  the orphan `ci` branch is entirely normal.
- A `pull_request` workflow runs from the PR's merge commit, so it needs no
  copy on the default branch. That is how `ci` tests itself: a PR into `ci`
  runs `ci`'s own `selftest.yml`, including a PR that adds or changes it
  (verified on the PR that introduced it).
- A `run:` step with no `shell:` runs as `bash -e {0}`, **without**
  `pipefail`. Only an explicit `shell: bash` (on the step, or as a job or
  workflow default) runs `bash --noprofile --norc -eo pipefail {0}`. Both appear
  in real run logs: our reusable steps log the first, antsibull-nox's action,
  which sets `shell: bash`, logs the second. The step-test harness emulates
  exactly this; an earlier version always used pipefail and so misreported a
  non-bug as a silent failure.
- `uses:` accepts **no expressions**, so a cross-repo action reference can
  never be computed. The composite-action refs inside `reusable-docs.yml` are
  hardcoded `@v1` and must be bumped by hand when cutting a new major.

### Dependabot coverage

- For the `github-actions` ecosystem, `directory: "/"` searches
  `.github/workflows/` and a **root-level** `action.yml` only. It does **not**
  recurse, so composite actions at `.github/actions/<name>/action.yml` are
  invisible to it, and it skips local `uses: ./...` references rather than
  following them into one.
- Covering them needs `directories` (plural — only it supports globbing) with
  `/.github/actions/*`. The glob must match the action's **directory**, not its
  `action.yml`.
- Multiple entries for the same ecosystem must not overlap in directories, so
  prefer one entry listing several `directories` over several entries.
- The `skeleton/` payload copies of the caller workflows are **not** scanned
  (Dependabot never looks below the root `.github/`), which is safe only
  because those callers reference no third-party actions. If that ever changes,
  Dependabot would update the root copy and not the payload copy, and
  `selfcheck.yml`'s byte-identity assertion would start failing.

## Design rules

- **Detect, don't configure.** namespace/name come from `galaxy.yml`; the
  minimum ansible-core comes from `meta/runtime.yml`; the release tarball name
  is derived. Nothing collection-specific is hardcoded in a reusable workflow.
- **Callers stay thin.** A caller workflow is triggers + one `uses:`. If you
  find yourself adding steps to a caller, the logic belongs in the reusable.
- **The two caller copies stay byte-identical.** `selfcheck.yml` enforces it.
- **Anything the skeleton claims must be tested by `selfcheck.yml`.** It is the
  only thing that actually runs `collection init` against `skeleton/`; without
  a new assertion there, a new payload feature rots undetected.
- **Anything the shared CI decides must be tested by `selftest.yml` on `ci`.**
  It runs actionlint over every workflow there and pytest step tests in
  `tests/`, which extract each decision-making `run:` step by `id` and run it
  under the shell the runner would use. A tested step takes all its inputs
  through `env:`. When you add such a step, give it an `id` and a test.
- **Never add a scheduled job to keep `ci` in sync with `main`.** There is
  nothing to sync — `ci` is an orphan holding self-contained workflows. A
  `schedule` trigger only fires for workflows on the default branch, and a bot
  force-pushing a branch containing workflow files hits the `GITHUB_TOKEN`
  restriction regardless.

## Both branches are protected

Repository rulesets `protect-main` and `protect-ci` block direct pushes,
force-pushes and deletion, and require a PR whose required check has passed:
`Generate a collection from skeleton/ and lint it` (Selfcheck) on `main`,
`Selftest result` on `ci`. Both checks are pinned to the GitHub Actions app
(`integration_id` 15368), so no other app can satisfy them by posting a status
with the same name.

- The only bypass is the repository admin role in `pull_request` mode: an
  admin can merge a PR past a stuck check, but **cannot push directly**. That
  was verified on a throwaway branch before the rulesets were applied (a direct
  push and a branch deletion by an admin were both rejected with `GH013`).
- Rulesets target branches only, so moving the `v1` tag is unaffected.
- Required approvals are 0: with a single maintainer, requiring one would make
  every PR unmergeable.

## Why bootstrap cannot clean up after itself

A generated repo is left holding `bootstrap.yml` and `selfcheck.yml`. Removing
them automatically was tried and cannot work under `GITHUB_TOKEN`. Four
independent gates stand in the way, so don't reintroduce a "cleanup PR" step
without a new credential:

1. The deletion has to be made in the working tree before any PR tool runs.
   `peter-evans/create-pull-request` builds its PR from uncommitted changes,
   and on a clean tree it "exits silently" and *reports success*.
2. So if you ever do automate it, key off
   `steps.<id>.outputs.pull-request-operation == 'created'`, never the step's
   `outcome`.
3. `GITHUB_TOKEN` may open PRs only if the org enables "Allow GitHub Actions to
   create and approve pull requests". It is off here
   (`can_approve_pull_request_reviews: false`), and org repos inherit it.
4. Opening the PR means pushing a branch that deletes workflow files, which
   needs the `workflows` permission, and `GITHUB_TOKEN` can never hold it.

Two related facts:

- **Pushes made with `GITHUB_TOKEN` do not trigger workflows.** Bootstrap's own
  commit therefore does not start the new collection's CI; the operator's
  manual cleanup push is what does. Don't expect green checks immediately
  after bootstrap.
- **`rsync` never deletes.** Bootstrap clears the template root, keeping
  `.git` and `.github/workflows/`, *before* overlaying the generated tree, so no
  template-only file outside `.github/workflows/` can leak into a collection.
  Inside that directory, `selfcheck.yml` enforces that every file either has a
  byte-identical payload twin or is on the `TEMPLATE_ONLY` allow-list, which is
  duplicated in bootstrap's printed cleanup command.

## What CI actually runs, and what it doesn't

- **antsibull-nox has two reusable workflows, and a collection needs both.**
  `reusable-nox-matrix.yml` runs only `matrix-generator` and the ansible-test
  sessions (sanity, units, integration, EE). `reusable-nox-run.yml` runs every
  *default* session - that is where `license-check`, `docs-check`,
  `build-import-check`, `extra-checks` and the lint sessions run.
  `reusable-nox.yml` calls both, as community.sops does. The ansible-test
  sessions must stay `default = false` (antsibull-nox's own default): the
  matrix runs them regardless, and marking them default makes the run job
  repeat the entire matrix sequentially.
- **A skipped job passes a required check.** GitHub reports a job skipped by an
  `if:` as success, so requiring a job that is skipped when something upstream
  fails lets a broken PR merge. That is why `reusable-nox.yml` and
  `reusable-coverage.yml` end in `Nox result` / `Coverage result` gate jobs
  that run `if: always()` and fail explicitly. antsibull-nox's own fixed-name
  job, `upload-coverage`, is no substitute: it runs only when Codecov upload is
  enabled.
- **Two licensing checkers, two definitions of compliant.** `reuse lint`
  honours `REUSE.toml`; antsibull-nox's `license-check.py` ignores it and reads
  every line of every file for per-file headers. `reuse lint` alone can pass
  a tree that the other fails file after file, so only the real
  `nox -e license-check` session proves compliance - which is why selfcheck
  runs that rather than `reuse lint`.

## Release gating

- `reusable-release.yml` bumps **relative to** `galaxy.yml`'s version, so the
  skeleton's starting version decides the first release. It starts at 0.0.1,
  and nothing is released below 1.0.0: only a `major_changes` fragment cuts the
  first release, which is exactly 1.0.0. Starting at 1.0.0 would have made the
  first release 1.1.0.
- The release secrets are optional. The `secrets` context is not available in
  `if:`, so their presence is exposed through `env` and a step output, and the
  job skips with a notice rather than failing when either is missing.

## The setup skill

`skeleton/.claude/skills/setup-collection-repo/` applies the settings a template
copy never carries: secrets, Pages, branch protection and required checks. Its
constraints:

- Only `set-release-secrets.sh` touches a secret. A value only ever passes
  through an environment variable or stdin - `printf` is a builtin, so piping
  from it spawns no process carrying the value. It never goes on a command
  line (the process list is visible to every user on the machine), into
  output, or into shell history.
- The branch-protection bypass is a `User` actor, the identity `RELEASE_TOKEN`
  acts as, rather than a role, so only the release workflow can push
  directly. Whether GitHub accepts a `User` bypass on a repository ruleset has
  not yet been exercised against a real repo; the skill is told to stop rather
  than broaden it.
- `lock-checks` refuses to require a check that has not been seen passing,
  because a required check that never reports blocks every PR.

## Why Dependabot can rewrite workflow files and our workflows cannot

Dependabot demonstrably opens PRs that modify `.github/workflows/*.yml`. That
is not a loophole we can borrow: `dependabot[bot]` is a **different GitHub App**,
and GitHub grants it the `Workflows: write` permission. A workflow's
`GITHUB_TOKEN` is an installation token for the *GitHub Actions* app, whose
permission set has no `workflows` key at all — it cannot be granted, only
substituted.

The capability is reachable, but only by changing identity: a PAT with
`workflow` scope, or an org GitHub App with `Workflows: write` minted via
`actions/create-github-app-token`. Both need a credential to exist before the
repo is usable, which is what the current design avoids.
