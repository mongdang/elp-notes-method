"""Stop: the two things people forget, while acting on them is cheap."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import hook_io
import session_close


def main() -> int:
    try:
        payload = hook_io.read_payload()
        if not payload:
            return 0
        root = hook_io.cwd_of(payload)
    except hook_io.PayloadError as exc:
        hook_io.fail_loud(str(exc))
        return 0

    try:
        report = session_close.check(root)
    except Exception as exc:  # noqa: BLE001
        hook_io.fail_loud(f"세션 마무리 검사 실패: {exc}")
        return 0

    if report.messages:
        print("[girok] 세션 마무리: " + " / ".join(report.messages), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
