<!--
SPDX-FileCopyrightText: Silex Data Solutions
SPDX-License-Identifier: Apache-2.0
-->

# silexdata.collection_skeleton

The source of truth for Ansible collection CI at Silex Data Solutions.

This repository does **three** things at once:

1. **A GitHub repository template.** "Use this template" → run one workflow →
   you have a working collection repo.
2. **An `ansible-galaxy` collection skeleton.** `skeleton/` is a valid
   `--collection-skeleton` payload, usable directly from the command line.
3. **The CI source of truth.** Every collection repo's workflows are ~10-line
   callers that delegate to the reusable workflows, so CI is fixed in one place
   rather than copy-pasted into N repos. Those reusable workflows live on the
   orphan [**`ci`** branch](https://github.com/SilexDataTeam/silexdata.collection_skeleton/tree/ci),
   not on `main`.

> **Looking for the actual CI logic?** It is on the
> [`ci` branch](https://github.com/SilexDataTeam/silexdata.collection_skeleton/tree/ci).
> It is kept off `main` because a repository template copies the default branch,
> and six inert reusable workflows in every collection is worse than one extra
> branch here. A tag can point at a commit on any branch, so `@v1` resolves
> there while `main` stays clean.

## Creating a new collection

### From the template (recommended)

1. **Use this template** → create your repo, named `silexdata.<name>`.
2. Actions tab → **Bootstrap collection** → Run workflow, filling in the
   namespace, collection name, description and authors.
3. Review the commit it pushes. It generates the collection from `skeleton/`,
   renames the placeholder integration targets, and replaces the template's
   own files with the collection's.
4. Clone the repository over SSH and run **`/setup-collection-repo`** in Claude
   Code. It removes the two template-only workflows (see
   [Leftover files](#leftover-files)), stores the release secrets without
   exposing them, enables GitHub Pages, and protects the default branch. The
   cleanup push is also what starts the collection's **first CI run**:
   bootstrap's own commit is pushed with `GITHUB_TOKEN`, and those pushes do not
   trigger workflows.
5. Land real content through a pull request. Once that PR's CI has passed,
   re-run the skill's `lock-checks` step so branch protection requires those
   checks from then on.

Nothing is published to Galaxy until you choose to. The collection starts at
0.0.1, merges below 1.0.0 only accumulate changelog fragments, and the first
release, exactly 1.0.0, is cut by merging a PR that carries a `major_changes`
fragment. Until the release secrets are configured, the Release workflow skips
with a notice.

Nothing else needs a secret: lint, tests, coverage and docs all run on the
automatic `GITHUB_TOKEN`. Every step the skill performs can also be done by
hand; its scripts live in `.claude/skills/setup-collection-repo/scripts/`.

### From the command line

```sh
cat > vars.json <<'JSON'
{
  "namespace": "silexdata",
  "collection_name": "example",
  "description": "Ansible collection for Example.",
  "authors": ["Silex Data Solutions <info@silexdata.com>"],
  "repository": "https://github.com/SilexDataTeam/silexdata.example",
  "issues": "https://github.com/SilexDataTeam/silexdata.example/issues",
  "homepage": "https://www.silexdata.com/",
  "documentation": "https://galaxy.ansible.com/ui/repo/published/silexdata/example/docs/"
}
JSON

ansible-galaxy collection init silexdata.example \
  --collection-skeleton skeleton --init-path ./out -e @vars.json
```

Then rename the two placeholder target directories, which `ansible-galaxy`
cannot template (it renders file *contents*, never *names*):

```sh
cd out/silexdata/example/tests/integration/targets
mv EXAMPLE_MODULE manage_example
mv setup_EXAMPLE  setup_example
```

> **Warning**
> Never point `--init-path` at an existing repository root. With `--force`,
> `ansible-galaxy` deletes the target directory's contents — `.git` included.

## What a generated collection gets

- **CI**: thin callers for lint, nox (sanity/units/docs), coverage, docs,
  changelog enforcement and release.
- **Lint**: pre-commit with ruff, yamllint, pymarkdown, ansible-lint,
  antsibull-changelog, actionlint, antsibull-docs and a build+import check.
- **Tests**: the `setup_<collection>` integration-target convention, including
  the service-availability probe and its CI warning annotation.
- **Docs**: an antsibull-docs Sphinx site deployed to GitHub Pages with the
  coverage report nested at `/coverage/`.
- **Release**: changelog-fragment-driven semver bump, tag, and publish to
  Ansible Galaxy.
- **Licensing**: a REUSE-compliant tree (`LICENSES/`, `REUSE.toml`, per-file
  SPDX headers) that passes `reuse lint` from the first commit.
- **Claude rules**: `.claude/rules/` covering licensing, testing and CI
  conventions — excluded from the built artifact via `build_ignore`.

## How CI is wired

```yaml
# a generated collection's .github/workflows/lint.yml, in full
jobs:
  lint:
    uses: SilexDataTeam/silexdata.collection_skeleton/.github/workflows/reusable-lint.yml@v1
```

| Reusable workflow (on the [`ci` branch](https://github.com/SilexDataTeam/silexdata.collection_skeleton/tree/ci)) | Does |
| --- | --- |
| `reusable-lint.yml` | pre-commit over all files |
| `reusable-nox.yml` | antsibull-nox default sessions |
| `reusable-coverage.yml` | ansible-test units + integration across the ansible-core matrix, aggregated into one report, badge and PR comment |
| `reusable-docs.yml` | antsibull-docs site + coverage report → GitHub Pages |
| `reusable-changelog.yml` | requires a changelog fragment on every PR |
| `reusable-release.yml` | version bump, changelog, tag, publish to Galaxy |
| `reusable-sync-rules.yml` | weekly: mirrors `skeleton/.claude/` (all but `CLAUDE.md`) into the collection and proposes drift as a PR |

Nothing collection-specific is hardcoded: namespace and name are read from
`galaxy.yml`, the minimum ansible-core from `meta/runtime.yml`, and the release
tarball name is derived.

**To change CI for every collection**, open a PR into the `ci` branch; it
merges once its `Selftest result` check passes. Then move the `v1` tag.
Collection repos pin `@v1` and Dependabot bumps them. See that branch's README
for the procedure.

## Leftover files

A GitHub template copies the default branch, so a new repo also receives
`bootstrap.yml`, `refresh-galaxy-token.yml` and `selfcheck.yml`. All three are
inert — they guard on `github.repository` and skip. The reusable workflows are
*not* among the leftovers, which is the whole reason they live on the `ci` branch.

Remove them from a local clone:

```sh
git pull
git rm .github/workflows/bootstrap.yml .github/workflows/refresh-galaxy-token.yml .github/workflows/selfcheck.yml
git commit -m "chore: remove collection_skeleton template-only workflows"
git push
```

This has to be done over SSH rather than by a workflow. `GITHUB_TOKEN` is not
permitted to create, modify or delete anything under `.github/workflows/`, and
routing the change through a pull request does not help: the PR's branch must
be pushed first, and that push is rejected the same way. Automating it would
need a PAT or GitHub App holding the Workflows permission — an org-wide
credential able to rewrite CI anywhere, which is a poor trade for deleting two
inert files. See [`.claude/CLAUDE.md`](.claude/CLAUDE.md).

Nothing else from the template survives: bootstrap clears the template's own
files before laying the generated collection over the top, keeping only
`.github/workflows/`.

## Contributing to this repo

Read [`.claude/CLAUDE.md`](.claude/CLAUDE.md) first — it documents the three
roles and the constraints that shape them.

The one rule that bites hardest: the caller workflows are **duplicated**, at
`.github/workflows/` and `skeleton/.github/workflows/`, and must stay
byte-identical. `selfcheck.yml` fails the build if they drift.

Verify a change to `skeleton/` locally:

```sh
ansible-galaxy collection init silexdata.testcoll \
  --collection-skeleton skeleton --init-path /tmp/skeltest -e @vars.json
cd /tmp/skeltest/silexdata/testcoll
yamllint --strict . && reuse lint && ansible-galaxy collection build
```

`selfcheck.yml` runs exactly this on every push, plus assertions that no `.j2`
files survived, that the `.gitkeep` placeholders are git-trackable, and that
`.claude/` and `.github/` stay out of the built artifact.
