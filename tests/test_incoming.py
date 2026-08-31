"""Noticing that a teammate has pushed something.

Without this the parallel-work rules have no trigger: the merge order, the
approval, the safety-first sequence all begin with somebody realizing there
is something to merge. Realizing it by remembering to look is exactly what
does not happen.

Everything here is read-only. The scan reports; a person decides.
"""
import subprocess

import incoming
import pytest


def git(repo, *args, **kw):
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", **kw
    )


def commit(repo, path, text, message):
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", message)


@pytest.fixture
def pair(tmp_path):
    """A bare remote with two clones, one per worker."""
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", "-q", str(bare))

    seed = tmp_path / "seed"
    seed.mkdir()
    git(seed, "init", "-q")
    git(seed, "remote", "add", "origin", str(bare))
    (seed / ".claude").mkdir()
    (seed / ".claude" / "girok.json").write_text(
        '{"notesDir": "notes", "parallelMode": true,'
        ' "workers": {"kdh": "kdh@example.invalid", "pjm": "pjm@example.invalid"}}',
        encoding="utf-8",
    )
    commit(seed, "notes/docs/PROGRESS.md", "# 현황판\n", "init")
    git(seed, "branch", "-M", "master")
    git(seed, "push", "-q", "-u", "origin", "master")

    clones = {}
    for who in ("kdh", "pjm"):
        clone = tmp_path / who
        git(tmp_path, "clone", "-q", str(bare), str(clone))
        git(clone, "config", "user.email", f"{who}@example.invalid")
        git(clone, "config", "user.name", who)
        git(clone, "checkout", "-q", "-b", who)
        clones[who] = clone
    return clones


def test_nothing_incoming_on_a_quiet_remote(pair):
    result = incoming.scan(pair["kdh"], worker="kdh", fetch=False)

    assert result.branches == []
    assert not result.anything


def test_a_teammates_pushed_branch_is_noticed(pair):
    commit(pair["pjm"], "notes/docs_pjm/PROGRESS.md", "# pjm\n", "pjm 진행")
    git(pair["pjm"], "push", "-q", "-u", "origin", "pjm")

    result = incoming.scan(pair["kdh"], worker="kdh", fetch=True)

    assert result.anything
    assert [b.name for b in result.branches] == ["origin/pjm"]
    assert result.branches[0].commits == 1


def test_it_says_which_documents_arrived(pair):
    commit(pair["pjm"], "notes/docs_pjm/PROGRESS.md", "# pjm\n", "pjm 진행")
    git(pair["pjm"], "push", "-q", "-u", "origin", "pjm")

    result = incoming.scan(pair["kdh"], worker="kdh", fetch=True)

    assert "notes/docs_pjm/PROGRESS.md" in result.branches[0].documents


def test_my_own_branch_is_not_incoming(pair):
    commit(pair["kdh"], "notes/docs_kdh/PROGRESS.md", "# kdh\n", "kdh 진행")
    git(pair["kdh"], "push", "-q", "-u", "origin", "kdh")

    result = incoming.scan(pair["kdh"], worker="kdh", fetch=True)

    assert [b.name for b in result.branches] == []


def test_a_safety_file_is_called_out_separately(pair):
    """The merge order starts with safety, so the scan has to say when the
    incoming work touches it rather than leaving it in a file list."""
    commit(pair["pjm"], "notes/docs/SAFETY_GATE.md", "# 게이트\n| 1 | OPEN |\n", "게이트 항목 추가")
    git(pair["pjm"], "push", "-q", "-u", "origin", "pjm")

    result = incoming.scan(pair["kdh"], worker="kdh", fetch=True)

    assert result.branches[0].touches_safety


def test_master_moving_ahead_is_noticed(pair):
    commit(pair["pjm"], "notes/docs/PROGRESS.md", "# 현황판\n\n갱신\n", "master 갱신")
    git(pair["pjm"], "checkout", "-q", "master")
    git(pair["pjm"], "merge", "-q", "pjm")
    git(pair["pjm"], "push", "-q", "origin", "master")

    result = incoming.scan(pair["kdh"], worker="kdh", fetch=True)

    assert result.master_ahead == 1
    assert result.anything


def test_being_offline_is_a_warning_not_a_crash(pair):
    """A hook that dies on a missing network takes the rest of the session's
    checks with it."""
    git(pair["kdh"], "remote", "set-url", "origin", "https://127.0.0.1:1/nope.git")

    result = incoming.scan(pair["kdh"], worker="kdh", fetch=True)

    assert result.fetch_failed
    assert result.branches == []


def test_a_repository_with_no_remote_is_quiet(tmp_path):
    solo = tmp_path / "solo"
    solo.mkdir()
    git(solo, "init", "-q")
    commit(solo, "a.md", "# a\n", "init")

    result = incoming.scan(solo, worker=None, fetch=True)

    assert not result.anything
    assert not result.fetch_failed


def test_the_scan_writes_nothing(pair):
    """Read-only by construction: the merge is a person's decision."""
    before = git(pair["kdh"], "status", "--porcelain").stdout
    head = git(pair["kdh"], "rev-parse", "HEAD").stdout

    incoming.scan(pair["kdh"], worker="kdh", fetch=True)

    assert git(pair["kdh"], "status", "--porcelain").stdout == before
    assert git(pair["kdh"], "rev-parse", "HEAD").stdout == head
