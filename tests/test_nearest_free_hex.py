from province import _nearest_free_hex

RING = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]


def test_free_neighbour_is_used():
    assert _nearest_free_hex({(0, 0)}, {(0, 0)}) in {(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)}


def test_enclosed_nation_finds_hex_beyond_ring():
    # Owner holds (0, 0); all six neighbours belong to other players.
    occupied = {(0, 0), *RING}
    got = _nearest_free_hex({(0, 0)}, occupied)
    assert got not in occupied


def test_never_returns_occupied_hex():
    occupied = {(0, 0), *RING, *{(2 * x, 2 * y) for x, y in RING}}
    assert _nearest_free_hex({(0, 0)}, occupied) not in occupied
