"""Tests ensuring chat profiles and names link to nation pages."""
from pathlib import Path
import re
import subprocess
import sys
import pytest

pytestmark = pytest.mark.no_server

ROOT = Path(__file__).resolve().parents[1]


def test_hub_html_chat_avatar_and_name_links():
    hub_content = (ROOT / "templates" / "hub.html").read_text(encoding="utf-8")

    # In chat feed history loop:
    assert '<a href="/country/id={{ m.sender_id }}" class="game-chat-avatar"' in hub_content
    assert '<a href="/country/id={{ m.sender_id }}" class="game-chat-name-link"' in hub_content

    # In online stack loop:
    assert '<a href="/country/id={{ uid }}" class="game-online-avatar"' in hub_content

    # In client-side JS renderMessageNode:
    assert "class=\"game-chat-avatar\"" in hub_content
    assert "class=\"game-chat-name-link\"" in hub_content
    assert "renderNationFlairHTML" in hub_content


def test_dm_thread_sender_links():
    v2_content = (ROOT / "templates" / "messages_thread_v2.html").read_text(encoding="utf-8")
    assert '<a href="/country/id={{ m.sender_id }}" class="chat-message-sender-link"' in v2_content
    assert "sender.className = 'chat-message-sender chat-message-sender-link';" in v2_content

    v1_content = (ROOT / "templates" / "messages_thread.html").read_text(encoding="utf-8")
    assert '<a href="/country/id={{ m.sender_id }}" class="chat-message-sender-link"' in v1_content
    assert "sender.className = 'chat-message-sender chat-message-sender-link';" in v1_content


def test_coalition_chat_sender_links():
    coalition_content = (ROOT / "templates" / "coalition_v2.html").read_text(encoding="utf-8")
    assert "sender.className = 'chat-message-sender chat-message-sender-link';" in coalition_content
    assert "sender.href = '/country/id=' + encodeURIComponent(m.sender_id);" in coalition_content


def test_css_classes_defined_and_bundled():
    glass_css = (ROOT / "static" / "css" / "game-glass.css").read_text(encoding="utf-8")
    assert ".game-chat-avatar" in glass_css
    assert ".game-chat-name-link" in glass_css
    assert ".game-online-stack a" in glass_css

    chat_css = (ROOT / "static" / "css" / "chat.css").read_text(encoding="utf-8")
    assert ".chat-message-sender-link" in chat_css

    # Check bundle check script passes
    script = ROOT / "scripts" / "check_game_css_bundle.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
