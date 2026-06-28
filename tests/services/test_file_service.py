"""Тесты путей хранилища с studio_id."""
from pathlib import Path
from types import SimpleNamespace
from src.services.file_service import FileService


def test_order_dir_includes_studio_id(tmp_path, monkeypatch):
    from src.services import file_service as mod
    monkeypatch.setattr(mod.settings, "photos_dir", tmp_path / "photos")
    monkeypatch.setattr(mod.settings, "temp_dir", tmp_path / "temp")
    fs = FileService(bot_token="x")
    order = SimpleNamespace(studio_id=7, order_number="240101-AAAA")
    d = fs.get_order_dir(order)
    assert d == (tmp_path / "photos" / "7" / "240101-AAAA")
    assert d.exists()
