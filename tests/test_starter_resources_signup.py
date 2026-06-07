"""Signup starter package includes lumber, rations, and explicit gold."""
import inspect

import pytest

pytestmark = pytest.mark.no_server

import signup


def test_starter_resources_include_onboarding_essentials():
    source = inspect.getsource(signup._init_economy_tables)
    for res in ("lumber", "coal", "iron", "rations", "steel"):
        assert f'("{res}"' in source or f"('{res}'" in source


def test_init_user_game_data_sets_explicit_gold():
    source = inspect.getsource(signup.init_user_game_data)
    assert "80_000_000" in source or "80000000" in source
