"""Players type billions as '5m' / '1,500,000' / '2 000 000'; reject non-whole numbers."""
import pytest

from helpers import parse_player_int

pytestmark = pytest.mark.no_server


@pytest.mark.parametrize(
    "raw,expected",
    [("10000", 10000), ("10,000", 10000), ("2 000 000", 2_000_000), ("5m", 5_000_000),
     ("1.5b", 1_500_000_000), ("2.5k", 2500), (" 7K ", 7000), ("1_000", 1000), (42, 42),
     ("-5", -5), ("0", 0), ("0.4m", 400000)],
)
def test_accepts_player_formats(raw, expected):
    assert parse_player_int(raw) == expected


@pytest.mark.parametrize("raw", ["1.5", "0.4", "abc", "", "m", "1e400", "nan", "inf", "5mm", "--1"])
def test_rejects_non_whole_or_garbage(raw):
    with pytest.raises(ValueError):
        parse_player_int(raw)
