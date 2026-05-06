"""Тесты выбора пар: volatility ranking, min volume filter, exclude list."""
from src.data.pairs import _compute_volatility_range_pct, _ranking_score


def test_volatility_range_calc():
    # 100..120 диапазон при avg=110 = 18.18% range
    assert abs(_compute_volatility_range_pct(120, 100, 110) - 18.181818) < 0.001
    # Защита от деления на ноль
    assert _compute_volatility_range_pct(1, 0, 0) == 0.0
    # Узкий диапазон стейблкоина (float comparison через abs)
    assert abs(_compute_volatility_range_pct(1.001, 0.999, 1.0) - 0.2) < 1e-9


def test_ranking_metric_volatility():
    ticker = {
        "symbol": "ALTUSDT", "quoteVolume": "50000000",
        "highPrice": "120", "lowPrice": "100", "weightedAvgPrice": "110",
        "priceChangePercent": "15.0",
    }
    score = _ranking_score(ticker, "volatility_range")
    assert abs(score - 18.18) < 0.1


def test_ranking_metric_volume():
    ticker = {"symbol": "BTCUSDT", "quoteVolume": "5000000000",
              "highPrice": "1", "lowPrice": "1", "weightedAvgPrice": "1",
              "priceChangePercent": "0"}
    assert _ranking_score(ticker, "volume") == 5_000_000_000


def test_ranking_metric_change_uses_abs_value():
    """priceChangePercent ranking сортирует по абсолюту — не важно вверх или вниз."""
    up = {"symbol": "X", "priceChangePercent": "20", "quoteVolume": "1",
          "highPrice": "1", "lowPrice": "1", "weightedAvgPrice": "1"}
    down = {"symbol": "Y", "priceChangePercent": "-25", "quoteVolume": "1",
            "highPrice": "1", "lowPrice": "1", "weightedAvgPrice": "1"}
    assert _ranking_score(down, "price_change_abs") > _ranking_score(up, "price_change_abs")


def test_volatility_beats_volume_for_oscillator():
    """Главный поинт: PUMPUSDT с горками 40% должен побить BTC по volatility ranking."""
    btc = {"symbol": "BTC", "quoteVolume": "5e9",
           "highPrice": "68500", "lowPrice": "67000", "weightedAvgPrice": "67800",
           "priceChangePercent": "0.5"}
    pump = {"symbol": "PUMP", "quoteVolume": "5e7",
            "highPrice": "0.12", "lowPrice": "0.08", "weightedAvgPrice": "0.10",
            "priceChangePercent": "15"}
    assert _ranking_score(pump, "volatility_range") > _ranking_score(btc, "volatility_range")
