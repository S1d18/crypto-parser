import os
import pytest
from scalper.config import Config


class TestConfigDefaults:
    """Verify all default values of Config dataclass."""

    def test_config_defaults(self):
        cfg = Config()

        # Bybit API
        assert cfg.bybit_api_key == ''
        assert cfg.bybit_api_secret == ''
        assert cfg.bybit_demo is True

        # Balance and positions
        assert cfg.balance == 200.0
        assert cfg.leverage == 20
        assert cfg.max_risk_per_trade == 0.5

        # Risk management
        assert cfg.max_daily_loss == 30.0
        assert cfg.max_consecutive_losses == 10
        assert cfg.pause_after_losses_minutes == 60

        # Scanning
        assert cfg.scan_interval == 30
        assert cfg.scalp_timeframe == '3m'
        assert cfg.trend_timeframe == '15m'
        assert cfg.top_n_coins == 50

        # Bybit fee
        assert cfg.taker_fee == 0.00055

        # Indicators
        assert cfg.atr_sl_multiplier == 1.5
        assert cfg.tp_ratio == 2.0
        assert cfg.adx_min == 20
        assert cfg.ema_fast == 9
        assert cfg.ema_slow == 21
        assert cfg.rsi_period == 14
        assert cfg.rsi_oversold == 35
        assert cfg.rsi_overbought == 65
        assert cfg.atr_period == 14
        assert cfg.adx_period == 14
        assert cfg.volume_ma_period == 20

        # Web
        assert cfg.web_port == 5001


class TestConfigFromEnv:
    """Verify from_env() loads values from environment variables."""

    def test_config_from_env(self, monkeypatch):
        monkeypatch.setenv('BYBIT_API_KEY', 'test-key-123')
        monkeypatch.setenv('BYBIT_API_SECRET', 'test-secret-456')
        monkeypatch.setenv('BYBIT_DEMO', 'false')
        monkeypatch.setenv('BALANCE', '500.0')
        monkeypatch.setenv('LEVERAGE', '10')
        monkeypatch.setenv('MAX_DAILY_LOSS', '50.0')
        monkeypatch.setenv('MAX_CONSECUTIVE_LOSSES', '5')
        monkeypatch.setenv('SCAN_INTERVAL', '15')
        monkeypatch.setenv('SCALP_TIMEFRAME', '5m')
        monkeypatch.setenv('TOP_N_COINS', '30')
        monkeypatch.setenv('WEB_PORT', '8080')

        cfg = Config.from_env()

        assert cfg.bybit_api_key == 'test-key-123'
        assert cfg.bybit_api_secret == 'test-secret-456'
        assert cfg.bybit_demo is False
        assert cfg.balance == 500.0
        assert cfg.leverage == 10
        assert cfg.max_daily_loss == 50.0
        assert cfg.max_consecutive_losses == 5
        assert cfg.scan_interval == 15
        assert cfg.scalp_timeframe == '5m'
        assert cfg.top_n_coins == 30
        assert cfg.web_port == 8080

    def test_config_from_env_defaults_when_unset(self, monkeypatch):
        """from_env() should use defaults when env vars are not set."""
        # Clear any potentially set env vars
        for var in ['BYBIT_API_KEY', 'BYBIT_API_SECRET', 'BYBIT_DEMO',
                     'BALANCE', 'LEVERAGE', 'MAX_DAILY_LOSS',
                     'MAX_CONSECUTIVE_LOSSES', 'SCAN_INTERVAL',
                     'SCALP_TIMEFRAME', 'TOP_N_COINS', 'WEB_PORT']:
            monkeypatch.delenv(var, raising=False)

        # Prevent load_dotenv from reading .env file
        monkeypatch.setattr('scalper.config.load_dotenv', lambda: None, raising=False)

        cfg = Config.from_env()

        assert cfg.bybit_api_key == ''
        assert cfg.bybit_api_secret == ''
        assert cfg.bybit_demo is True
        assert cfg.balance == 200.0
        assert cfg.leverage == 20
        assert cfg.web_port == 5001

    def test_config_from_env_bybit_demo_variants(self, monkeypatch):
        """BYBIT_DEMO should handle various truthy/falsy values."""
        for val in ['true', 'True', 'TRUE', '1', 'yes']:
            monkeypatch.setenv('BYBIT_DEMO', val)
            cfg = Config.from_env()
            assert cfg.bybit_demo is True, f"Expected True for BYBIT_DEMO={val}"

        for val in ['false', 'False', 'FALSE', '0', 'no']:
            monkeypatch.setenv('BYBIT_DEMO', val)
            cfg = Config.from_env()
            assert cfg.bybit_demo is False, f"Expected False for BYBIT_DEMO={val}"
