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
├── workflows/reusable-{lint,nox,coverage,docs,changelog,release}.yml
└── actions/{wait-for-workflow-artifact,coverage-summary}/
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

```sh
git switch ci
# edit, then verify:
actionlint .github/workflows/*.yml
git push origin ci

# roll it out:
git tag -fa v1 -m "v1" && git push --force origin v1
```

Cut a new major (`v2`) instead of moving `v1` when a change is breaking for
callers — a new required input, a removed output, or different default
behaviour. Collection repos pin `@v1`, and Dependabot raises the bump.

Pushes here must be made over SSH. `GITHUB_TOKEN` cannot write to
`.github/workflows/`, so no workflow can maintain this branch on your behalf.

## Verification

`selfcheck.yml` on `main` checks this branch out and lints it on every push, so
a syntax error here is caught there rather than in whichever collection happens
to run CI next.
