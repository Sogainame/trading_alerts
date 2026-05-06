"""Smoke test: все модули проекта импортируются."""

def test_all_modules_import():
    # Если что-то сломано — упадёт здесь
    import config
    from src.core import state
    from src.data import binance_rest, order_book_handler, pairs, warmup, ws_manager
    from src.detectors import (
        base, multi_tf_pattern, order_book_imbalance, static_wall,
        taker_imbalance, velocity, volume_anomaly, wall_absorption,
        whale_trades,
    )
    from src.scoring import engine
    from src.alerts import formatter, manager, targets
    from src.notifier import telegram
    from src.storage import sqlite_log
    from src import scanner
    assert scanner.Scanner  # класс существует


def test_config_loads():
    import config
    # Все критичные параметры на месте
    assert config.TOP_N_PAIRS > 0
    assert config.MIN_DAILY_VOLUME_USD > 0
    assert config.RANKING_METRIC in ("volatility_range", "price_change_abs", "volume")
    assert 0 < config.SCORE_MIN_TO_ALERT <= 100
    assert config.TIER_WATCH < config.TIER_STRONG < config.TIER_PREMIUM
    assert config.STATIC_WALL_MIN_LIFETIME_SECONDS > 0
    assert 0 < config.ABSORPTION_REMNANT_PCT < 1
    assert "5m" in config.TIMEFRAMES


def test_no_followup_remnants():
    """Гарантия что фолоу-ап удалён везде."""
    import config
    assert not hasattr(config, "FOLLOWUP_DELAYS_SECONDS")

    from src.alerts import formatter
    assert not hasattr(formatter, "format_followup")

    from src.alerts import manager
    src = manager.__file__
    with open(src) as f:
        content = f.read()
    assert "followup" not in content.lower()
