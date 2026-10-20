"""Fail closed before desktop acceptance when macOS drops posted input events."""

import json
import sys


ACCESS_MESSAGE = (
    "macOS does not allow this launch context to post native input events. "
    "The real mouse/keyboard acceptance tests cannot run, so the build is stopped. "
    "In System Settings > Privacy & Security > Accessibility, allow the app "
    "launching this build (for example Terminal), then quit and reopen that app "
    "and rerun this check. No test was skipped and no permission was changed. "
    "macOS 未允許本次啟動環境投遞原生輸入事件；請在系統設定 > 隱私權與安全性 > "
    "輔助使用，確認啟動建置的 App（例如終端機）權限，再完全結束並重新開啟該 App。"
)


def require_native_event_access(preflight=None):
    """Read existing permission only; never trigger a grant request or prompt."""
    if preflight is None:
        import Quartz
        preflight = Quartz.CGPreflightPostEventAccess
    if not preflight():
        raise RuntimeError(ACCESS_MESSAGE)


def main():
    if sys.platform != "darwin":
        raise SystemExit("Native macOS desktop acceptance requires macOS.")
    import Quartz
    from AppKit import NSApplication
    info = {
        "post_event_access": bool(Quartz.CGPreflightPostEventAccess()),
        "listen_event_access": bool(Quartz.CGPreflightListenEventAccess()),
        "activation_policy": int(NSApplication.sharedApplication().activationPolicy()),
    }
    print(json.dumps(info), flush=True)
    try:
        require_native_event_access(lambda: info["post_event_access"])
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
