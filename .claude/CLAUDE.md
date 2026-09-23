# silexdata.collection_skeleton

This repository is the source of truth for Ansible collection CI at Silex Data
Solutions. It performs **three distinct jobs at once**, and knowing which one
you are touching matters before you change anything.

## The three roles

| # | Role | Lives on | Consumed by |
| --- | --- | --- | --- |
| 1 | **GitHub repository template** | `main`, repo root | "Use this template" → `bootstrap.yml` |
| 2 | **`ansible-galaxy` collection skeleton** | `main`, `skeleton/` | `ansible-galaxy collection init --collection-skeleton skeleton` |
| 3 | **CI source of truth** | the orphan **`ci`** branch | every collection repo, via `uses: ...@v1` |

Roles 1 and 2 coexist because the galaxy-skeleton payload is confined to
`skeleton/`, leaving the repo root free. Role 3 lives on a separate branch
because a template copies only the default branch — see below.

```text
main
  .github/workflows/{lint,nox,coverage,docs,changelog,release}.yml
                             thin callers - copied into new repos by role 1
  .github/workflows/bootstrap.yml    role 1: one-time setup, workflow_dispatch
  .github/workflows/selfcheck.yml    proves role 2 still works, and lints `ci`
  skeleton/                  role 2: the collection init payload

ci  (orphan - no shared history with main)
  .github/workflows/reusable-*.yml   role 3: the actual CI logic
  .github/actions/                   composite actions shared cross-repo
```

## Why the CI lives on an orphan branch

A GitHub template copies **only the default branch**. If the reusable workflows
sat on `main`, every generated collection would receive six inert copies — and
`GITHUB_TOKEN` cannot delete anything under `.github/workflows/`, so no
automation could clean them up. Keeping them off `main` reduces the leftovers
in a new repo to `bootstrap.yml` and `selfcheck.yml`, which cannot move because
they need real event triggers.

A tag may point at a commit on any branch, so `@v1` resolves on `ci` while
`main` stays clean.

It is an **orphan** branch, and nothing rebases it. The reusable workflows are
self-contained — they reference nothing else in the repo, and `actions/checkout`
inside them checks out the *caller's* repo — so there is nothing on `main` to
stay in sync with. Do not add a scheduled rebase: a `schedule` trigger only
fires for workflows on the default branch, and a bot force-pushing a branch
containing workflow files hits the `GITHUB_TOKEN` restriction anyway.

## Rules

@rules/architecture.md
@rules/licensing.md

## The constraint that shapes everything

`GITHUB_TOKEN` is **categorically forbidden** from creating, updating or
deleting anything under `.github/workflows/`, and no `permissions:` key can
grant it — there is no `workflows:` key; writing one is a parse error. The
push is rejected by git's receive path:

```text
refusing to allow a GitHub App to create or update workflow
`.github/workflows/ci.yml` without `workflows` permission
```

This is why `bootstrap.yml` is built to leave that directory **untouched**: the
thin caller workflows arrive with the template copy and are byte-identical to
the copies in `skeleton/.github/workflows/`, so bootstrap's rsync produces no
diff there. `selfcheck.yml` enforces that byte-identity — if the two copies
drift, bootstrap breaks in a confusing way.

SSH pushes are *not* subject to this restriction, which is why manual cleanup
from a local clone works where automation cannot.

## Before you change anything

- **Editing a `reusable-*.yml`?** You are changing CI for every collection in
  the org. Nothing pins a SHA; they pin `@v1`, so the change lands everywhere
  as soon as you move that tag.
- **Editing a caller workflow?** Change it in **both** `.github/workflows/` and
  `skeleton/.github/workflows/`, identically.
- **Editing `skeleton/`?** Run the local verification below; `collection init`
  failures are destructive (a templating error `rmtree`s the output directory).

## Local verification

```sh
ansible-galaxy collection init silexdata.testcoll \
  --collection-skeleton skeleton --init-path /tmp/skeltest -e @vars.json
cd /tmp/skeltest/silexdata/testcoll
yamllint --strict . && reuse lint && ansible-galaxy collection build
```

Never point `--init-path` at a real repository root: `--force` deletes the
target directory's contents, `.git` included.
