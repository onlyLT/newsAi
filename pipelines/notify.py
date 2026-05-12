import sys
from typing import Optional


_toaster = None
if sys.platform == "win32":
    try:
        from win10toast import ToastNotifier
        _toaster = ToastNotifier()
    except ImportError:
        _toaster = None


def notify(*, title: str, message: str, success: bool = True) -> None:
    if sys.platform != "win32" or _toaster is None:
        # No-op on non-Windows or if package unavailable
        return
    icon_path: Optional[str] = None
    try:
        _toaster.show_toast(title, message, duration=8,
                            icon_path=icon_path, threaded=True)
    except Exception:
        # Notifications must NEVER fail the pipeline
        pass
