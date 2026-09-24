# SPDX-FileCopyrightText: Silex Data Solutions
# SPDX-License-Identifier: Apache-2.0
"""reusable-sync-rules.yml: mirror the skeleton-managed files into a collection."""

import os
import subprocess

import pytest
import yaml

WORKFLOW = "reusable-sync-rules.yml"
SRC_ROOT = ".skeleton-src/skeleton"
MANIFEST = ".skeleton-src/sync-manifest.txt"
BRANCH = "sync/skeleton"
FRAGMENT = "changelogs/fragments/sync-skeleton.yml"

MANIFEST_TEXT = """# What the sync mirrors.
.claude/

.yamllint
pyproject.toml
"""
# skeleton/: the managed files, plus templates and files the manifest leaves out.
SKELETON = {
    ".claude/CLAUDE.md.j2": "# {{ namespace }}.{{ collection_name }}\n",
    ".claude/rules/ci.md": "ci rules v2\n",
    ".claude/rules/licensing.md": "licensing rules\n",
    ".claude/skills/setup/SKILL.md": "setup skill\n",
    ".yamllint": "yamllint config v2\n",
    "pyproject.toml": "ruff config v2\n",
    "antsibull-nox.toml.j2": "{{ collection_name }} nox config\n",
    "README.md.j2": "# {{ collection_name }}\n",
}
# The collection, in sync, with its own CLAUDE.md and unmanaged files.
MANAGED = {
    ".claude/rules/ci.md": "ci rules v2\n",
    ".claude/rules/licensing.md": "licensing rules\n",
    ".claude/skills/setup/SKILL.md": "setup skill\n",
    ".yamllint": "yamllint config v2\n",
    "pyproject.toml": "ruff config v2\n",
}
OWN = {
    ".claude/CLAUDE.md": "# silexdata.cyberark - tailored\n",
    "antsibull-nox.toml": "the collection's own nox config\n",
    "README.md": "# silexdata.cyberark\n",
}
COLLECTION = {**MANAGED, **OWN}


def git(cwd, *args):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@localhost", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def write_tree(root, files):
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def tree(root):
    """The collection's files, leaving out git and the skeleton checkout."""
    return {
        str(p.relative_to(root)): p.read_text()
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.relative_to(root).parts[0] not in (".git", ".skeleton-src")
    }


@pytest.fixture
def collection(tmp_path):
    """A clone of a collection whose origin/main holds COLLECTION, beside a skeleton checkout."""
    origin, clone = tmp_path / "origin.git", tmp_path / "clone"
    git(tmp_path, "init", "--quiet", "--bare", "--initial-branch=main", str(origin))
    git(tmp_path, "clone", "--quiet", str(origin), str(clone))
    write_tree(clone, COLLECTION)
    git(clone, "add", "-A")
    git(clone, "commit", "--quiet", "-m", "base")
    git(clone, "push", "--quiet", "origin", "main")
    write_tree(clone / SRC_ROOT, SKELETON)
    (clone / MANIFEST).write_text(MANIFEST_TEXT)
    return clone


def mirror(step, cwd):
    return step(
        WORKFLOW,
        "sync",
        "mirror",
        {"SRC_ROOT": SRC_ROOT, "MANIFEST": MANIFEST},
        cwd=cwd,
    )


def test_in_sync_changes_nothing(step, collection):
    result = mirror(step, collection)
    assert result.returncode == 0, result.stdout
    assert result.outputs["changed"] == "false"
    assert tree(collection) == COLLECTION


@pytest.mark.parametrize(
    "drift",
    [
        lambda c: (c / ".claude/rules/ci.md").write_text(
            "ci rules v1, edited locally\n"
        ),
        lambda c: (c / ".claude/rules/licensing.md").unlink(),
        lambda c: (c / ".claude/rules/extra.md").write_text("not in the skeleton\n"),
        lambda c: (
            (c / ".claude/skills/local/SKILL.md").parent.mkdir(parents=True)
            or (c / ".claude/skills/local/SKILL.md").write_text("local skill\n")
        ),
        lambda c: (c / ".yamllint").write_text("a local yamllint tweak\n"),
        lambda c: (c / "pyproject.toml").unlink(),
    ],
    ids=[
        "edited-rule",
        "deleted-rule",
        "extra-rule",
        "extra-skill",
        "edited-file",
        "deleted-file",
    ],
)
def test_drift_is_mirrored_away(step, collection, drift):
    drift(collection)
    git(collection, "add", "-A")
    git(collection, "commit", "--quiet", "-m", "drift")
    result = mirror(step, collection)
    assert result.returncode == 0, result.stdout
    assert result.outputs["changed"] == "true"
    assert tree(collection) == COLLECTION


def test_skeleton_changes_arrive(step, collection):
    write_tree(
        collection / SRC_ROOT,
        {".claude/rules/new.md": "a new rule\n", ".yamllint": "yamllint config v3\n"},
    )
    result = mirror(step, collection)
    assert result.outputs["changed"] == "true"
    synced = tree(collection)
    assert synced[".claude/rules/new.md"] == "a new rule\n"
    assert synced[".yamllint"] == "yamllint config v3\n"


def test_files_the_manifest_leaves_out_are_the_collections_own(step, collection):
    for rel, text in (
        ("antsibull-nox.toml", "tuned locally\n"),
        ("README.md", "# rewritten\n"),
    ):
        (collection / rel).write_text(text)
    git(collection, "commit", "--quiet", "-am", "own changes")
    result = mirror(step, collection)
    assert result.outputs["changed"] == "false"
    assert (collection / "antsibull-nox.toml").read_text() == "tuned locally\n"
    assert (collection / "README.md").read_text() == "# rewritten\n"
    # Unlisted skeleton templates never arrive, rendered or not.
    assert not (collection / "README.md.j2").exists()
    assert not (collection / "antsibull-nox.toml.j2").exists()


def test_claude_md_is_the_collections_own(step, collection):
    (collection / ".claude/CLAUDE.md").write_text("# edited for this collection\n")
    git(collection, "commit", "--quiet", "-am", "tailor")
    result = mirror(step, collection)
    assert result.outputs["changed"] == "false"
    assert (
        collection / ".claude/CLAUDE.md"
    ).read_text() == "# edited for this collection\n"
    assert not (collection / ".claude/CLAUDE.md.j2").exists()


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        (
            lambda c: write_tree(
                c / SRC_ROOT, {".claude/rules/per-collection.md.j2": "x\n"}
            ),
            "Jinja templates",
        ),
        (
            lambda c: (c / MANIFEST).write_text(MANIFEST_TEXT + "README.md.j2\n"),
            "Jinja template",
        ),
        (
            lambda c: (c / MANIFEST).write_text(MANIFEST_TEXT + "noxfile.py\n"),
            "is not a file",
        ),
        (
            lambda c: (c / MANIFEST).write_text(MANIFEST_TEXT + "docs/\n"),
            "is not a directory",
        ),
        (lambda c: (c / MANIFEST).write_text("/etc/passwd\n"), "must be relative"),
        (lambda c: (c / MANIFEST).write_text("../outside\n"), "must be relative"),
        (lambda c: (c / MANIFEST).write_text("# only comments\n\n"), "lists nothing"),
        (lambda c: (c / MANIFEST).unlink(), "no sync-manifest.txt"),
    ],
    ids=[
        "template-in-dir",
        "template-entry",
        "missing-file",
        "missing-dir",
        "absolute",
        "parent",
        "empty",
        "no-manifest",
    ],
)
def test_bad_sources_are_refused_before_anything_changes(
    step, collection, setup, message
):
    setup(collection)
    result = mirror(step, collection)
    assert result.returncode != 0
    errors = result.annotations("error")
    assert errors and message in errors[0]
    assert tree(collection) == COLLECTION


def commit(step, cwd):
    return step(
        WORKFLOW,
        "sync",
        "commit",
        {"BRANCH": BRANCH, "FRAGMENT": FRAGMENT, "MANIFEST": MANIFEST},
        cwd=cwd,
    )


@pytest.fixture
def drifted(collection):
    """The collection with a drifted rule and config file committed and pushed to main."""
    (collection / ".claude/rules/ci.md").write_text("drifted\n")
    (collection / ".yamllint").write_text("drifted\n")
    git(collection, "commit", "--quiet", "-am", "drift")
    git(collection, "push", "--quiet", "origin", "main")
    return collection


def sync(step, collection):
    """One workflow run: a fresh checkout of main, mirrored, then committed."""
    git(collection, "fetch", "--quiet", "origin")
    git(collection, "switch", "--quiet", "main")
    git(collection, "reset", "--quiet", "--hard", "origin/main")
    assert mirror(step, collection).outputs["changed"] == "true"
    return commit(step, collection)


def test_sync_is_pushed_with_a_trivial_fragment(step, drifted):
    collection = drifted
    result = sync(step, collection)
    assert result.returncode == 0, result.stdout
    assert result.outputs["pushed"] == "true"
    # Exactly what the collection's yamllint and antsibull-changelog accept: a
    # document start, then a trivial section, which never triggers a release.
    fragment = git(collection, "show", f"origin/{BRANCH}:{FRAGMENT}")
    assert fragment.startswith("---\n")
    assert yaml.safe_load(fragment) == {
        "trivial": ["Sync the skeleton-managed files with the collection skeleton."]
    }
    assert (
        git(collection, "show", f"origin/{BRANCH}:.claude/rules/ci.md")
        == "ci rules v2\n"
    )
    assert (
        git(collection, "show", f"origin/{BRANCH}:.yamllint") == "yamllint config v2\n"
    )
    # Only the managed files and the fragment change; nothing else is swept in.
    changed = git(collection, "diff", "--name-only", "origin/main", f"origin/{BRANCH}")
    assert sorted(changed.split()) == [".claude/rules/ci.md", ".yamllint", FRAGMENT]


def test_an_identical_sync_is_not_re_pushed(step, drifted):
    collection = drifted
    sync(step, collection)
    first = git(collection, "rev-parse", f"origin/{BRANCH}")
    result = sync(step, collection)
    assert result.outputs["pushed"] == "false"
    assert git(collection, "rev-parse", f"origin/{BRANCH}") == first


def test_the_branch_follows_the_default_branch(step, drifted):
    collection = drifted
    sync(step, collection)
    git(collection, "switch", "--quiet", "main")
    git(collection, "reset", "--quiet", "--hard", "origin/main")
    (collection / "NOTES.md").write_text("main moved on\n")
    git(collection, "add", "NOTES.md")
    git(collection, "commit", "--quiet", "-m", "unrelated")
    git(collection, "push", "--quiet", "origin", "main")
    result = sync(step, collection)
    assert result.outputs["pushed"] == "true"
    assert "NOTES.md" in git(collection, "ls-tree", "--name-only", f"origin/{BRANCH}")


@pytest.fixture
def fake_gh(tmp_path):
    """A `gh` on PATH that logs its calls and plays back canned answers."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "gh.log"
    (bindir / "gh").write_text(
        "#!/usr/bin/env bash\n"
        'echo "$*" >> "$GH_LOG"\n'
        'case "$1 $2" in\n'
        '  "pr list") printf "%s" "$GH_EXISTING" ;;\n'
        '  "pr create") printf "%s\\n" "$GH_CREATE_OUT"; exit "$GH_CREATE_RC" ;;\n'
        "  *) exit 99 ;;\n"
        "esac\n"
    )
    (bindir / "gh").chmod(0o755)

    def runner(existing="", create_out="", create_rc=0):
        return {
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "GH_LOG": str(log),
            "GH_EXISTING": existing,
            "GH_CREATE_OUT": create_out,
            "GH_CREATE_RC": str(create_rc),
        }

    runner.calls = lambda: log.read_text().splitlines() if log.exists() else []
    return runner


PR_ENV = {
    "GH_TOKEN": "t",
    "REPO": "SilexDataTeam/silexdata.cyberark",
    "SERVER": "https://github.com",
    "BRANCH": BRANCH,
    "BASE": "main",
}


def open_pr(step, runner):
    return step(WORKFLOW, "sync", "pr", PR_ENV, runner=runner)


def test_an_open_sync_pr_is_reused(step, fake_gh):
    url = "https://github.com/SilexDataTeam/silexdata.cyberark/pull/7"
    result = open_pr(step, fake_gh(existing=url))
    assert result.returncode == 0
    assert result.outputs["url"] == url
    assert not any(c.startswith("pr create") for c in fake_gh.calls())


def test_a_new_pr_is_opened_against_the_default_branch(step, fake_gh):
    url = "https://github.com/SilexDataTeam/silexdata.cyberark/pull/8"
    result = open_pr(step, fake_gh(create_out=url))
    assert result.returncode == 0, result.stdout
    assert result.outputs["url"] == url
    assert result.annotations("notice")
    create = [c for c in fake_gh.calls() if c.startswith("pr create")]
    assert len(create) == 1 and f"--base main --head {BRANCH}" in create[0]


def test_an_org_that_forbids_actions_prs_gets_a_one_click_link(step, fake_gh):
    refusal = (
        "pull request create failed: GraphQL: "
        "GitHub Actions is not permitted to create or approve pull requests (createPullRequest)"
    )
    result = open_pr(step, fake_gh(create_out=refusal, create_rc=1))
    assert result.returncode == 0, result.stdout
    link = f"https://github.com/SilexDataTeam/silexdata.cyberark/compare/main...{BRANCH}?expand=1"
    assert result.outputs["url"] == link
    warnings = result.annotations("warning")
    assert warnings and link in warnings[0]


def test_any_other_pr_failure_fails_the_run(step, fake_gh):
    result = open_pr(step, fake_gh(create_out="HTTP 502: Bad Gateway", create_rc=1))
    assert result.returncode != 0
    assert result.annotations("error")
    assert "url" not in result.outputs
