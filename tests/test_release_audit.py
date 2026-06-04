from __future__ import annotations

from tools import release_audit


def test_release_audit_passes():
    assert release_audit.run_audit() == []
