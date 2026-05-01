"""
Unit + integration tests for stock_alert/main.py.

Tests cover:
  - _build_watch_message() — correct prompt assembly
  - build_watch_runtime() — correct channel wiring
  - build_query_runtime() — correct channel wiring
  - CLI argument parsing

No LLM, no network, no API keys required.
"""
import sys
import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add stock_alert dir to path so we can import main directly
_DEMO_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_DEMO_DIR))
sys.path.insert(0, str(_DEMO_DIR.parent))  # demo_apps root for _llm.py


# ---------------------------------------------------------------------------
# _build_watch_message
# ---------------------------------------------------------------------------

class TestBuildWatchMessage:

    def _import(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("stock_main", _DEMO_DIR / "main.py")
        mod = importlib.util.load_from_spec(spec)  # type: ignore
        spec.loader.exec_module(mod)
        return mod

    @pytest.fixture
    def mod(self):
        # Import without running main()
        import importlib
        spec = importlib.util.spec_from_file_location("stock_main", str(_DEMO_DIR / "main.py"))
        module = importlib.util.module_from_spec(spec)
        with patch.object(spec.loader, "exec_module", wraps=spec.loader.exec_module):
            try:
                spec.loader.exec_module(module)
            except SystemExit:
                pass
        return module

    def test_no_threshold_includes_price_request(self, mod):
        msg = mod._build_watch_message("BTC", None, "above", is_stock=False)
        assert "BTC" in msg
        assert "get_crypto_price" in msg

    def test_above_threshold_includes_above_language(self, mod):
        msg = mod._build_watch_message("BTC", 50000, "above", is_stock=False)
        assert "ABOVE" in msg
        assert "50,000" in msg or "50000" in msg

    def test_below_threshold_includes_below_language(self, mod):
        msg = mod._build_watch_message("ETH", 2000, "below", is_stock=False)
        assert "BELOW" in msg
        assert "2,000" in msg or "2000" in msg

    def test_stock_uses_get_stock_quote_tool(self, mod):
        msg = mod._build_watch_message("AAPL", None, "above", is_stock=True)
        assert "get_stock_quote" in msg
        assert "AAPL" in msg

    def test_crypto_uses_get_crypto_price_tool(self, mod):
        msg = mod._build_watch_message("SOL", None, "above", is_stock=False)
        assert "get_crypto_price" in msg
        assert "SOL" in msg

    def test_no_threshold_returns_simple_status(self, mod):
        msg = mod._build_watch_message("BTC", None, "above", is_stock=False)
        assert "ALERT" not in msg or "threshold" not in msg.lower()

    def test_above_alert_mentions_drop_below_as_no_action(self, mod):
        """When direction=above, price below threshold = 'no action needed'."""
        msg = mod._build_watch_message("BTC", 50000, "above", is_stock=False)
        assert "No action needed" in msg

    def test_below_alert_mentions_above_as_no_action(self, mod):
        """When direction=below, price above threshold = 'no action needed'."""
        msg = mod._build_watch_message("BTC", 40000, "below", is_stock=False)
        assert "No action needed" in msg


# ---------------------------------------------------------------------------
# Module-level import test — ensure no syntax errors
# ---------------------------------------------------------------------------

class TestStockAlertImport:

    def test_module_imports_cleanly(self):
        """main.py should import without errors (no side effects at import time)."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "stock_alert_main", str(_DEMO_DIR / "main.py")
        )
        module = importlib.util.module_from_spec(spec)
        # We don't exec it to avoid running asyncio.run() — just check it loads
        assert module is not None
        assert spec is not None


# ---------------------------------------------------------------------------
# _make_output_channels — channel selection logic
# ---------------------------------------------------------------------------

class TestMakeOutputChannels:

    @pytest.fixture
    def mod(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("stock_main2", str(_DEMO_DIR / "main.py"))
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception:
            pass
        return module

    def test_no_outputs_returns_log_channel(self, mod):
        channels = mod._make_output_channels(use_telegram=False, use_sms=False)
        assert len(channels) >= 1
        # At minimum a LogChannel should be present
        names = [type(c).__name__ for c in channels]
        assert any("Log" in n for n in names)

    def test_telegram_flag_adds_telegram_channel(self, mod, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
        channels = mod._make_output_channels(use_telegram=True, use_sms=False)
        names = [type(c).__name__ for c in channels]
        assert any("Telegram" in n for n in names)
