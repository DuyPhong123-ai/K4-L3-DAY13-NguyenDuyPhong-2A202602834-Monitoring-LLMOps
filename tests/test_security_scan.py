from __future__ import annotations

from scripts import security_scan


def test_security_scan_passes_repository_submission() -> None:
    assert security_scan.scan() == []
