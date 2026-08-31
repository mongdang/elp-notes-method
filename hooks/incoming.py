"""Noticing that a teammate has pushed something.

Without this the parallel-work rules have no trigger. The merge order, the
approval, the safety-first sequence — all of it begins with somebody
realizing there is something to merge, and realizing it by remembering to
look is exactly what does not happen.

Everything here is read-only. `git fetch` moves remote-tracking refs and
nothing else; no merge, no checkout, no write to the working tree. What to do
about the finding is a person's decision, and the rules say it is not made
without their approval.
"""
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import notes_config

# Long enough for a slow corporate remote, short enough that a session does
# not appear to hang. The SessionStart hook's own timeout is 30s.
FETCH_TIMEOUT_SEC = 12

SAFETY_NAMES = ("SAFETY_GATE.md",)
MAX_DOCUMENTS = 6


@dataclass
class Branch:
    name: str
    commits: int
    documents: list[str] = field(default_factory=list)
    touches_safety: bool = False


@dataclass
class Incoming:
    branches: list[Branch] = field(default_factory=list)
    master_ahead: int = 0
    fetch_failed: bool = False
    remote: str | None = None

    @property
    def anything(self) -> bool:
        return bool(self.branches) or self.master_ahead > 0


def _git(root: Path, *args: str, timeout: int | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _remote_name(root: Path, configured: str | None) -> str | None:
    names = _git(root, "remote").stdout.split()
    if not names:
        return None
    if configured in names:
        return configured
    return "origin" if "origin" in names else names[0]


def _default_branch(root: Path, remote: str) -> str | None:
    for candidate in ("master", "main"):
        ref = f"refs/remotes/{remote}/{candidate}"
        if _git(root, "rev-parse", "--verify", "--quiet", ref).returncode == 0:
            return f"{remote}/{candidate}"
    return None


def scan(
    start: Path | str = ".",
    worker: str | None = None,
    fetch: bool = True,
) -> Incoming:
    cfg = notes_config.load(start)
    root = cfg.repo_root
    result = Incoming()

    if not cfg.is_repository:
        return result

    remote = _remote_name(root, cfg.remote)
    if remote is None:
        return result
    result.remote = remote

    if fetch:
        try:
            fetched = _git(root, "fetch", "--quiet", remote, timeout=FETCH_TIMEOUT_SEC)
            result.fetch_failed = fetched.returncode != 0
        except (subprocess.TimeoutExpired, OSError):
            result.fetch_failed = True
        if result.fetch_failed:
            # Offline is ordinary. The refs already on disk are still worth
            # comparing, but they may be stale, so nothing is claimed.
            return result

    mine = {f"{remote}/{worker}"} if worker else set()
    default = _default_branch(root, remote)

    listed = _git(root, "for-each-ref", "--format=%(refname:short)", f"refs/remotes/{remote}")
    for ref in listed.stdout.split():
        if ref.endswith("/HEAD") or ref in mine or ref == default:
            continue
        branch = _describe(root, ref, cfg)
        if branch.commits:
            result.branches.append(branch)

    if default:
        result.master_ahead = _count(root, default)

    return result


def _count(root: Path, ref: str) -> int:
    counted = _git(root, "rev-list", "--count", f"HEAD..{ref}")
    try:
        return int(counted.stdout.strip())
    except ValueError:
        return 0


def _describe(root: Path, ref: str, cfg: notes_config.NotesConfig) -> Branch:
    branch = Branch(name=ref, commits=_count(root, ref))
    if not branch.commits:
        return branch

    changed = _git(root, "diff", "--name-only", f"HEAD...{ref}").stdout.split("\n")
    paths = [p.strip() for p in changed if p.strip()]

    branch.touches_safety = any(Path(p).name in SAFETY_NAMES for p in paths)
    branch.documents = [p for p in paths if p.lower().endswith(".md")][:MAX_DOCUMENTS]
    return branch


def summary(result: Incoming) -> list[str]:
    """One or two lines for the session-start block.

    It states what arrived and asks; it does not merge. The rules put the
    approval before the merge, and the safety-related part of the incoming
    work before the rest.
    """
    if result.fetch_failed:
        return [
            f"[주의] `{result.remote}` fetch 실패 — 오프라인이거나 인증 문제다. "
            f"상대 작업자의 새 내용이 있는지 확인하지 못했다"
        ]
    if not result.anything:
        return []

    lines = []
    for branch in result.branches:
        bits = [f"{branch.name} 새 커밋 {branch.commits}건"]
        if branch.touches_safety:
            bits.append("**안전 게이트 변경 포함 — 이것부터 본다**")
        if branch.documents:
            bits.append("문서: " + ", ".join(branch.documents))
        lines.append("[반입] " + " · ".join(bits))

    if result.master_ahead:
        lines.append(f"[반입] {result.remote} 기본 브랜치가 {result.master_ahead}건 앞서 있다")

    lines.append(
        "병합은 승인 없이 하지 않는다 — 요약을 제시하고 진행 여부를 확인할 것. "
        "미루기로 하면 그 사실을 자기 현황판에 한 줄 남긴다"
    )
    return lines
