"""Tests for settings.settings_manager.SettingsManager."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Patch config.DATA_DIR before importing SettingsManager so it uses a temp dir
_tmp = tempfile.mkdtemp()

with patch("config.DATA_DIR", Path(_tmp)):
    from settings.settings_manager import SettingsManager, RESTART_REQUIRED_KEYS


@pytest.fixture()
def sm(tmp_path):
    """Yield a fresh SettingsManager that persists into *tmp_path*."""
    with patch("config.DATA_DIR", tmp_path):
        mgr = SettingsManager.__new__(SettingsManager)
        mgr._path = tmp_path / "settings.json"
        mgr._data = dict(SettingsManager._DEFAULTS)
        mgr._subscribers = {}
        import threading
        mgr._lock = threading.Lock()
        yield mgr


class TestGetSet:
    def test_get_returns_default(self, sm):
        assert sm.get("audio.sample_rate") == 16000

    def test_set_and_get(self, sm):
        sm.set("audio.sample_rate", 48000)
        assert sm.get("audio.sample_rate") == 48000

    def test_get_unknown_key(self, sm):
        assert sm.get("nonexistent.key") is None

    def test_get_unknown_key_with_default(self, sm):
        assert sm.get("nonexistent.key", 42) == 42


class TestSaveLoad:
    def test_save_creates_file(self, sm):
        sm.save()
        assert sm._path.exists()

    def test_save_load_roundtrip(self, sm):
        sm.set("appearance.opacity", 0.5)
        sm.save()
        # Create a new instance reading the same file
        with patch("config.DATA_DIR", sm._path.parent):
            sm2 = SettingsManager.__new__(SettingsManager)
            sm2._path = sm._path
            sm2._data = dict(SettingsManager._DEFAULTS)
            sm2._subscribers = {}
            import threading
            sm2._lock = threading.Lock()
            # Load from file
            raw = json.loads(sm._path.read_text("utf-8"))
            sm2._data.update(raw)
        assert sm2.get("appearance.opacity") == 0.5


class TestResetDefaults:
    def test_reset_restores_defaults(self, sm):
        sm.set("audio.sample_rate", 48000)
        sm.reset_to_defaults()
        assert sm.get("audio.sample_rate") == 16000


class TestSubscribe:
    def test_subscriber_called_on_set(self, sm):
        calls = []
        sm.subscribe("audio.sample_rate", lambda k, v: calls.append((k, v)))
        sm.set("audio.sample_rate", 44100)
        assert calls == [("audio.sample_rate", 44100)]

    def test_subscriber_not_called_for_other_key(self, sm):
        calls = []
        sm.subscribe("audio.sample_rate", lambda k, v: calls.append((k, v)))
        sm.set("audio.chunk_ms", 200)
        assert calls == []


class TestRestartKeys:
    def test_restart_keys_is_frozenset(self):
        assert isinstance(RESTART_REQUIRED_KEYS, frozenset)

    def test_api_keys_require_restart(self):
        assert "general.deepgram_api_key" in RESTART_REQUIRED_KEYS
        assert "general.openai_api_key" in RESTART_REQUIRED_KEYS


class TestHelpers:
    def test_all_keys(self, sm):
        keys = sm.all_keys()
        assert "audio.sample_rate" in keys
        assert "appearance.opacity" in keys

    def test_defaults_returns_copy(self, sm):
        d = sm.defaults()
        d["audio.sample_rate"] = 999
        assert sm.get("audio.sample_rate") == 16000

    def test_get_changed_from_defaults(self, sm):
        sm.set("appearance.font_size", 20)
        changed = sm.get_changed_from_defaults()
        assert "appearance.font_size" in changed
        assert changed["appearance.font_size"] == 20
