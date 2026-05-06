"""
Pytest conftest. Замокаем talib + dotenv до того как импорт src.* загрузит их.
"""
import os
import sys
import types

# Мок TA-Lib (для контейнера где C-библиотеки нет)
_talib_mock = types.SimpleNamespace(
    CDLENGULFING=lambda *a, **kw: [0] * 60,
    EMA=lambda data, timeperiod: [0.0] * len(data),
)
sys.modules.setdefault("talib", _talib_mock)

# Установить env vars иначе TelegramNotifier при импорте может ругаться
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "TEST_TOKEN")
os.environ.setdefault("TELEGRAM_CHAT_ID", "12345")

# Чтоб src.* был импортируем
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
