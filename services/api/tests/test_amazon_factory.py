import pytest
from services.api.app.services.amazon_factory import get_amazon_adapter


def test_get_amazon_adapter_defaults_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HALO_AMAZON_ADAPTER", raising=False)
    adapter = get_amazon_adapter()
    assert adapter.vendor == "AMAZON_MOCK"


def test_get_amazon_adapter_rejects_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HALO_AMAZON_ADAPTER", "nope")
    with pytest.raises(ValueError, match="Unknown HALO_AMAZON_ADAPTER"):
        get_amazon_adapter()
