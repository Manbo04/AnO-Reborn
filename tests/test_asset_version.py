"""Asset cache-bust token for static URLs."""
from game_ui import get_asset_version


def test_asset_version_is_non_empty_string():
    v = get_asset_version()
    assert isinstance(v, str)
    assert len(v) >= 3
