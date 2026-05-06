"""
AlertManager — единая точка отправки алертов.

Что делает:
  1. Проверяет минимальный score
  2. Проверяет ONLY_BULLISH флаг
  3. Проверяет cooldown
  4. Считает targets (стоп/цель из стакана)
  5. Отправляет в Telegram, получает message_id
  6. Логирует в SQLite
  7. Планирует follow-up'ы
"""
import logging
import time

from config import (
    ALERT_COOLDOWN_SECONDS,
    FOLLOWUP_DELAYS_SECONDS,
    ONLY_BULLISH,
    SCORE_MIN_TO_ALERT,
)
from src.alerts.followup import FollowupScheduler
from src.alerts.formatter import format_alert
from src.alerts.targets import find_targets
from src.core.state import SymbolState
from src.detectors.volume_anomaly import mark_volume_anomaly_alerted
from src.notifier.telegram import TelegramNotifier
from src.scoring.engine import ScoringResult
from src.storage.sqlite_log import SignalLogger

logger = logging.getLogger(__name__)


class AlertManager:
    def __init__(
        self,
        notifier: TelegramNotifier,
        followup: FollowupScheduler,
        signal_logger: SignalLogger,
    ):
        self.notifier = notifier
        self.followup = followup
        self.signal_logger = signal_logger

    async def maybe_alert(
        self,
        state: SymbolState,
        result: ScoringResult,
        current_price: float,
    ) -> None:
        if result.score < SCORE_MIN_TO_ALERT:
            return
        if ONLY_BULLISH and result.direction != "BULLISH":
            return

        now = time.time()
        if now - state.last_alert_at < ALERT_COOLDOWN_SECONDS:
            return

        # Анти-спам volume-anomaly
        has_volume_anomaly = any(
            s.detector_name == "VOLUME_ANOMALY" for s in result.signals
        )

        # Считаем targets из стакана (если стакан проинициализирован)
        targets = find_targets(state, current_price)

        msg = format_alert(state.symbol, result, current_price, targets)
        api_result = await self.notifier.send(msg)
        if not api_result:
            return

        state.last_alert_at = now
        state.last_alert_score = result.score
        if has_volume_anomaly:
            mark_volume_anomaly_alerted(state)

        message_id = api_result.get("message_id")

        await self.signal_logger.log_alert(
            symbol=state.symbol,
            score=result.score,
            tier=result.tier,
            direction=result.direction,
            price=current_price,
            signals=result.signals,
            message_id=message_id,
        )

        for delay in FOLLOWUP_DELAYS_SECONDS:
            self.followup.schedule(
                symbol=state.symbol,
                entry_price=current_price,
                delay_seconds=delay,
                reply_to_message_id=message_id,
            )

        logger.info(
            f"ALERT [{result.tier} {result.score}] {state.symbol} "
            f"{result.direction} • detectors: {[s.detector_name for s in result.signals]}"
        )
