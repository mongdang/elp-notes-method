"""Command line behaviour.

Hooks and CI call these scripts as processes and branch on the exit code, so
the codes are part of the contract: 0 passes, 1 stops the work. A check that
fails silently with 0 is worse than no check, which is why every failure
path here is asserted rather than assumed.
"""
import check_docs
import marker_scan
import method_sync
from conftest import write


def test_check_docs_exits_zero_on_a_clean_tree(notes_repo, capsys):
    code = check_docs.main(["--root", str(notes_repo)])

    assert code == 0
    assert "전부 통과" in capsys.readouterr().out


def test_check_docs_exits_one_and_names_the_file(notes_repo, capsys):
    write(
        notes_repo / "notes" / "docs" / "PROGRESS.md",
        "# 현황판\n\n---\n\n## 목차\n\n- [없음](#없음)\n\n---\n\n## 있음\n\n내용\n",
    )

    code = check_docs.main(["--root", str(notes_repo)])

    assert code == 1
    out = capsys.readouterr().out
    assert "[실패]" in out
    assert "PROGRESS.md" in out


def test_check_docs_accepts_specific_files(notes_repo, capsys):
    target = notes_repo / "notes" / "docs" / "PROGRESS.md"

    code = check_docs.main([str(target), "--root", str(notes_repo)])

    assert code == 0
    assert "1개 문서" in capsys.readouterr().out


def test_check_docs_warns_about_a_missing_file_without_failing(notes_repo, capsys):
    code = check_docs.main([str(notes_repo / "없는파일.md"), "--root", str(notes_repo)])

    assert code == 0
    assert "[주의]" in capsys.readouterr().out


def test_marker_scan_exits_one_on_an_unregistered_marker(notes_repo, capsys):
    write(notes_repo / "notes" / "docs" / "SAFETY_GATE.md", "# 게이트\n\n항목 없음\n")
    write(notes_repo / "src" / "Motion.cs", "// SAFETY-STUB\n")

    code = marker_scan.main(["--root", str(notes_repo)])

    assert code == 1
    assert "[차단]" in capsys.readouterr().out


def test_marker_scan_exits_zero_when_the_module_is_off(notes_repo, capsys):
    (notes_repo / ".claude" / "girok.json").write_text(
        '{"notesDir": "notes", "modules": {"safetyGate": false}}', encoding="utf-8"
    )
    write(notes_repo / "src" / "Motion.cs", "// SAFETY-STUB\n")

    code = marker_scan.main(["--root", str(notes_repo)])

    assert code == 0
    assert "건너뜀" in capsys.readouterr().out


def test_method_sync_round_trip_through_the_cli(notes_repo, capsys):
    assert method_sync.main(["sync", "--root", str(notes_repo)]) == 0
    assert method_sync.main(["verify", "--root", str(notes_repo)]) == 0
    assert method_sync.main(["status", "--root", str(notes_repo)]) == 0
    assert "일치" in capsys.readouterr().out


def test_method_sync_verify_exits_one_on_a_hand_edited_snapshot(notes_repo, capsys):
    method_sync.main(["sync", "--root", str(notes_repo)])
    rules = notes_repo / "notes" / ".method" / "RULES.md"
    rules.write_text(rules.read_text(encoding="utf-8") + "손댐\n", encoding="utf-8")

    code = method_sync.main(["verify", "--root", str(notes_repo)])

    assert code == 1
    assert "[실패]" in capsys.readouterr().out


def test_method_sync_status_exits_one_without_a_snapshot(notes_repo, capsys):
    code = method_sync.main(["status", "--root", str(notes_repo)])

    assert code == 1
    assert "초기화" in capsys.readouterr().out


def test_method_sync_status_exits_one_on_a_version_mismatch(notes_repo, capsys, downgrade_snapshot):
    method_sync.main(["sync", "--root", str(notes_repo)])
    version = notes_repo / "notes" / ".method" / "VERSION"
    downgrade_snapshot(version)

    code = method_sync.main(["status", "--root", str(notes_repo)])

    assert code == 1
    assert "sync" in capsys.readouterr().out
