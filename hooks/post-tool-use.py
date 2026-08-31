"""PostToolUse: lint what was just written, and confirm a push went out."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import hook_io
import doc_followup


def main() -> int:
    try:
        payload = hook_io.read_payload()
        if not payload:
            return 0
        root = hook_io.cwd_of(payload)
    except hook_io.PayloadError as exc:
        hook_io.fail_loud(str(exc))
        return 0

    tool_input = payload.get("tool_input", {}) or {}

    # A push is the other half of "commit then push immediately". Without a
    # line saying it went out, the transcript does not show whether it did.
    command = tool_input.get("command")
    if command:
        try:
            result = doc_followup.after_command(root, command, failed=hook_io.failed(payload))
        except Exception as exc:  # noqa: BLE001
            hook_io.fail_loud(f"push 확인 실패: {exc}")
            return 0
        if result.messages:
            hook_io.emit_context("PostToolUse", "[girok] " + " / ".join(result.messages))
        return 0

    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not target:
        return 0

    try:
        result = doc_followup.after_edit(root, Path(target))
    except Exception as exc:  # noqa: BLE001
        hook_io.fail_loud(f"문서 검사 실패: {exc}")
        return 0

    if result.messages:
        hook_io.emit_context(
            "PostToolUse",
            "[girok] 문서 검사: " + " / ".join(result.messages),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
