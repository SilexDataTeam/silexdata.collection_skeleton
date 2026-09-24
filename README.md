<!--
SPDX-FileCopyrightText: Silex Data Solutions
SPDX-License-Identifier: Apache-2.0
-->

# `ci` branch — shared CI for Silex Data collections

> **You are on an orphan branch.** It shares no history with `main` and holds
> no collection content. See
> [`main`](https://github.com/SilexDataTeam/silexdata.collection_skeleton/tree/main)
> for the repository template and the `ansible-galaxy` collection skeleton.

This branch holds the reusable workflows and composite actions that every
`silexdata.*` collection calls:

```
.github/
├── workflows/reusable-{lint,nox,coverage,docs,changelog,release,sync-rules}.yml
├── workflows/reusable-refresh-galaxy-token.yml   called only by the skeleton repo itself
├── workflows/selftest.yml     tests this branch; never called by a collection
└── actions/{wait-for-workflow-artifact,coverage-summary}/
tests/                         step-logic tests run by selftest.yml
```

Collection repos reference them by tag, never by branch:

```yaml
jobs:
  lint:
    uses: SilexDataTeam/silexdata.collection_skeleton/.github/workflows/reusable-lint.yml@v1
```

## Why these live on their own branch

A GitHub repository template copies **only the default branch**. Keeping the
reusable workflows off `main` means a repo created from this template never
receives them — they would otherwise arrive as six inert files in every
collection, and `GITHUB_TOKEN` is not permitted to delete anything under
`.github/workflows/`, so automated cleanup is not possible.

A tag may point at a commit on any branch, so `@v1` resolves here perfectly
well while `main` stays clean.

## Why it is an orphan, and why nothing rebases it

These workflows are self-contained: they reference nothing else in the
repository, and `actions/checkout` inside them checks out the *caller's* repo,
not this one. So there is nothing on `main` for this branch to stay in sync
with, and no rebase — scheduled or otherwise — is needed or wanted.

That is deliberate. A scheduled workflow only runs from the default branch, and
a bot force-pushing a rebased branch containing workflow files would run
straight into the `GITHUB_TOKEN` restriction described above.

## Changing CI

Editing anything here changes CI for **every** collection in the org as soon as
the `v1` tag moves. There is no per-repo pinning below the major version.

Changes land like any other: branch from `ci`, open a PR **into `ci`**, and
merge once the `Selftest result` check passes. A ruleset requires both.

```sh
git switch -c fix/my-change origin/ci
# edit, then verify:
actionlint .github/workflows/*.yml
python -m pytest tests
git push -u origin fix/my-change
gh pr create --base ci

# after the merge, roll it out:
git fetch origin && git tag -a v1.0.1 -m v1.0.1 origin/ci
git tag -fa v1 -m v1 origin/ci
git push origin v1.0.1 && git push --force origin v1
```

Cut a new major (`v2`) instead of moving `v1` when a change is breaking for
callers — a new required input, a removed output, or different default
behaviour. Collection repos pin `@v1`, and Dependabot raises the bump.

Pushes here must be made over SSH. `GITHUB_TOKEN` cannot write to
`.github/workflows/`, so no workflow can maintain this branch on your behalf.

## Verification

`selftest.yml` runs on every PR into, and push to, this branch:

- **actionlint** (with shellcheck) over every workflow here.
- **Step tests** in `tests/`. Each decision-making `run:` step is extracted
  from its workflow by step `id` and run against fixtures under the shell the
  runner would use: `bash -e` when `shell:` is unset, `bash -eo pipefail`
  only for an explicit `shell: bash`. They cover the ansible-core floor and
  coverage matrix, the release version and pre-1.0 hold, the release-secrets
  skip, the changelog-fragment check, the badge thresholds, the
  service-unavailable warning, the `Nox result` / `Coverage result` gates,
  the `.claude/` mirror, sync branch and sync PR of the rules sync, the
  Galaxy token refresh (including that the token never reaches curl's
  command line), and resuming a release from its tag.
  `tests/test_harness.py` pins that shell choice.

A tested step takes all of its inputs through `env:`, never `${{ }}` in the
script, and the test must supply exactly the variables it declares, so a new
input cannot go untested unnoticed. When you add a step that decides
something, give it an `id` and a test.

Nothing here runs the reusable workflows end to end against a collection;
that happens in the first collection to pick up a moved tag.
