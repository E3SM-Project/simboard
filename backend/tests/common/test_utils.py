from app.common.utils import _normalize_hpc_username


class TestNormalizeHpcUsername:
    def test_returns_trimmed_username(self) -> None:
        assert _normalize_hpc_username("  test-user  ") == "test-user"

    def test_returns_none_for_blank_username(self) -> None:
        assert _normalize_hpc_username("   ") is None
