"""服薬確認のスケジューリングと再確認ロジック。

流れ:
  1. 予定時刻(cron ジョブ)になったら確認メッセージをプッシュし、確認待ち状態にする。
  2. 同時に「無返答タイムアウト」を RETRY_INTERVAL_MINUTES 後に予約する。
  3. 「はい」が来たら確認待ちを解除し、タイムアウトも取り消す(次の予定時刻まで何もしない)。
  4. 「いいえ」が来たら RETRY_INTERVAL_MINUTES 後に再確認を予約する。
  5. 無返答のままタイムアウトしたら「いいえ」と同じ扱いで再確認する。

ジョブ ID は決め打ちにしてあり、同じ ID で上書きすることで
「ユーザーごとに追いかけ確認は常に1件だけ」を保証する。
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger

import messages

logger = logging.getLogger(__name__)

# タイムアウト時の挙動
TIMEOUT_IMMEDIATE = "immediate"  # 5分間無返答なら、その時点で即再送
TIMEOUT_DELAYED = "delayed"  # 5分間無返答のあと、さらに待ってから再送


class ReminderService:
    def __init__(
        self,
        scheduler,
        storage,
        line_client,
        timezone: str = "Asia/Tokyo",
        retry_interval_minutes: int = 5,
        max_retry_count: int = 0,
        timeout_behavior: str = TIMEOUT_IMMEDIATE,
    ):
        self._scheduler = scheduler
        self._storage = storage
        self._line = line_client
        self._timezone_name = timezone
        self._tz = ZoneInfo(timezone)
        self._retry_interval = retry_interval_minutes
        self._max_retry_count = max_retry_count
        self._timeout_behavior = timeout_behavior

    # ------------------------------------------------------------------
    # ジョブ ID
    # ------------------------------------------------------------------
    @staticmethod
    def _reminder_job_id(user_id: str, hhmm: str) -> str:
        return f"remind:{user_id}:{hhmm}"

    @staticmethod
    def _followup_job_id(user_id: str) -> str:
        return f"followup:{user_id}"

    # ------------------------------------------------------------------
    # 起動・同期
    # ------------------------------------------------------------------
    def restore_jobs(self) -> None:
        """保存済みの予定時刻から cron ジョブを組み直す(起動時に呼ぶ)。"""
        # プロセス停止中に宙に浮いた確認待ちは、追いかけジョブが失われているため破棄する
        self._storage.clear_all_pending()
        for user_id in self._storage.user_ids():
            self.sync_user_jobs(user_id)
        logger.info("restored reminder jobs for %d user(s)", len(self._storage.user_ids()))

    def sync_user_jobs(self, user_id: str) -> None:
        """そのユーザーの cron ジョブを、保存済みの予定時刻と一致させる。"""
        prefix = f"remind:{user_id}:"
        for job in self._scheduler.get_jobs():
            if job.id.startswith(prefix):
                job.remove()

        for hhmm in self._storage.get_times(user_id):
            hour, minute = hhmm.split(":")
            self._scheduler.add_job(
                self._fire_scheduled_reminder,
                trigger=CronTrigger(
                    hour=int(hour), minute=int(minute), timezone=self._timezone_name
                ),
                args=[user_id, hhmm],
                id=self._reminder_job_id(user_id, hhmm),
                replace_existing=True,
                # 一時的な停止やスリープ復帰でも、少し遅れて実行されるようにする
                misfire_grace_time=300,
                max_instances=1,
                coalesce=True,
            )

    # ------------------------------------------------------------------
    # 確認メッセージの送信
    # ------------------------------------------------------------------
    def _fire_scheduled_reminder(self, user_id: str, hhmm: str) -> None:
        """予定時刻になったときの入口(cron ジョブから呼ばれる)。"""
        logger.info("scheduled reminder fired: user=%s time=%s", user_id, hhmm)
        self._send_confirmation(user_id, hhmm, sent_count=1)

    def _send_confirmation(self, user_id: str, hhmm: str, sent_count: int) -> None:
        text = messages.CONFIRM if sent_count == 1 else messages.CONFIRM_AGAIN
        self._storage.set_pending(user_id, hhmm, sent_count)
        try:
            self._line.push_text(user_id, text, quick_reply_labels=["はい", "いいえ"])
        except Exception:
            # 送信に失敗しても追いかけジョブは仕掛けておき、次の機会に再送する
            logger.exception("failed to push confirmation: user=%s", user_id)
        self._schedule_followup(user_id, self._on_timeout)

    def _resend_confirmation(self, user_id: str) -> None:
        """「いいえ」またはタイムアウトを受けての再確認。"""
        pending = self._storage.get_pending(user_id)
        if not pending:
            # 待っている間に「はい」が届いていた場合は何もしない
            return
        self._send_confirmation(user_id, pending["time"], pending["sent_count"] + 1)

    # ------------------------------------------------------------------
    # 追いかけジョブ(ユーザーごとに1件)
    # ------------------------------------------------------------------
    def _schedule_followup(self, user_id: str, func) -> None:
        run_date = datetime.now(self._tz) + timedelta(minutes=self._retry_interval)
        self._scheduler.add_job(
            func,
            trigger="date",
            run_date=run_date,
            args=[user_id],
            id=self._followup_job_id(user_id),
            replace_existing=True,
            misfire_grace_time=300,
        )

    def _cancel_followup(self, user_id: str) -> None:
        job = self._scheduler.get_job(self._followup_job_id(user_id))
        if job is not None:
            job.remove()

    def _on_timeout(self, user_id: str) -> None:
        """規定時間ぶん返信がなかった場合。「いいえ」と同じ処理をする。"""
        pending = self._storage.get_pending(user_id)
        if not pending:
            return
        logger.info("no reply timeout: user=%s time=%s", user_id, pending["time"])

        if self._retry_limit_reached(pending):
            self._finish_by_retry_limit(user_id, notify=True)
            return

        if self._timeout_behavior == TIMEOUT_DELAYED:
            # 無返答の5分ののち、さらに5分待ってから再送する
            self._schedule_followup(user_id, self._resend_confirmation)
        else:
            self._resend_confirmation(user_id)

    # ------------------------------------------------------------------
    # ユーザーの返信
    # ------------------------------------------------------------------
    def handle_yes(self, user_id: str) -> str:
        pending = self._storage.get_pending(user_id)
        self._cancel_followup(user_id)
        self._storage.clear_pending(user_id)
        if not pending:
            return messages.NO_PENDING
        logger.info("user answered YES: user=%s time=%s", user_id, pending["time"])
        return messages.YES_ACCEPTED

    def handle_no(self, user_id: str) -> str:
        pending = self._storage.get_pending(user_id)
        if not pending:
            return messages.NO_PENDING
        logger.info("user answered NO: user=%s time=%s", user_id, pending["time"])

        if self._retry_limit_reached(pending):
            self._finish_by_retry_limit(user_id, notify=False)
            return messages.RETRY_LIMIT_REACHED

        self._schedule_followup(user_id, self._resend_confirmation)
        return messages.NO_ACCEPTED_TEMPLATE.format(minutes=self._retry_interval)

    # ------------------------------------------------------------------
    # 再送回数の上限
    # ------------------------------------------------------------------
    def _retry_limit_reached(self, pending: dict) -> bool:
        if self._max_retry_count <= 0:  # 0 は無制限
            return False
        already_retried = pending["sent_count"] - 1
        return already_retried >= self._max_retry_count

    def _finish_by_retry_limit(self, user_id: str, notify: bool) -> None:
        self._cancel_followup(user_id)
        self._storage.clear_pending(user_id)
        logger.info("retry limit reached: user=%s", user_id)
        if notify:
            try:
                self._line.push_text(user_id, messages.RETRY_LIMIT_REACHED)
            except Exception:
                logger.exception("failed to push retry-limit notice: user=%s", user_id)
