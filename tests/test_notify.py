import sys
import pytest
from unittest.mock import MagicMock, patch
from pipelines.notify import notify


def test_notify_no_op_on_non_windows(monkeypatch):
    # Force platform to not-win32; should not raise
    monkeypatch.setattr(sys, "platform", "linux")
    notify(title="t", message="m", success=True)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only path")
def test_notify_calls_toaster_on_windows():
    fake = MagicMock()
    with patch("pipelines.notify._toaster", fake):
        notify(title="t", message="m", success=True)
    fake.show_toast.assert_called_once()
