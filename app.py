"""LINE お薬リマインダー ボットのエントリーポイント。

Webhook を受け取る Flask サーバーと、確認メッセージをプッシュする
スケジューラ(APScheduler)を同一プロセスで動かす。
"""

import atexit
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, abort, request
from linebot import WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import FollowEvent, MessageEvent, TextMessage

import config
from handlers.message_handler import MessageHandler
from services.line_client import LineClient
from services.reminder_service import ReminderService
from services.storage import Storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    config.validate()

    storage = Storage(config.DATA_FILE)
    line_client = LineClient(config.CHANNEL_ACCESS_TOKEN)

    scheduler = BackgroundScheduler(timezone=config.TIMEZONE)
    reminder = ReminderService(
        scheduler=scheduler,
        storage=storage,
        line_client=line_client,
        timezone=config.TIMEZONE,
        retry_interval_minutes=config.RETRY_INTERVAL_MINUTES,
        max_retry_count=config.MAX_RETRY_COUNT,
        timeout_behavior=config.TIMEOUT_BEHAVIOR,
    )
    message_handler = MessageHandler(storage, reminder)

    scheduler.start()
    reminder.restore_jobs()
    atexit.register(lambda: scheduler.shutdown(wait=False))

    app = Flask(__name__)
    webhook_handler = WebhookHandler(config.CHANNEL_SECRET)

    @app.route("/health", methods=["GET"])
    def health():
        return {"status": "ok"}, 200

    @app.route("/debug/jobs", methods=["GET"])
    def debug_jobs():
        # 原因調査用の一時的な診断ページ。個人情報(ユーザーID等)は含めない。
        jobs = []
        for job in scheduler.get_jobs():
            kind = job.id.split(":", 1)[0]
            jobs.append(
                {
                    "kind": kind,
                    "time": job.id.rsplit(":", 1)[-1] if kind == "remind" else None,
                    "next_run_time": (
                        job.next_run_time.isoformat() if job.next_run_time else None
                    ),
                }
            )
        return {
            "server_time_utc": datetime.now(timezone.utc).isoformat(),
            "server_time_configured_tz": datetime.now(ZoneInfo(config.TIMEZONE)).isoformat(),
            "configured_timezone": config.TIMEZONE,
            "scheduler_running": scheduler.running,
            "job_count": len(jobs),
            "jobs": jobs,
        }, 200

    @app.route("/callback", methods=["POST"])
    def callback():
        # LINE からのリクエストであることを署名で必ず検証する
        signature = request.headers.get("X-Line-Signature", "")
        body = request.get_data(as_text=True)
        try:
            webhook_handler.handle(body, signature)
        except InvalidSignatureError:
            logger.warning("invalid signature on /callback")
            abort(400)
        return "OK", 200

    def _reply(reply_token, reply):
        try:
            line_client.reply_text(
                reply_token, reply.text, quick_reply_labels=reply.quick_reply_labels
            )
        except Exception:
            logger.exception("failed to reply")

    @webhook_handler.add(MessageEvent, message=TextMessage)
    def on_text_message(event):
        user_id = getattr(event.source, "user_id", None)
        if not user_id:
            # グループ・トークルームなど、個人を特定できない送信元は対象外
            return
        reply = message_handler.handle_text(user_id, event.message.text)
        _reply(event.reply_token, reply)

    @webhook_handler.add(FollowEvent)
    def on_follow(event):
        user_id = getattr(event.source, "user_id", None)
        if not user_id:
            return
        reply = message_handler.handle_follow(user_id)
        _reply(event.reply_token, reply)

    return app


# gunicorn など WSGI サーバーから `app:app` として読み込めるよう、モジュール直下にも公開する。
# 本番(Render)では gunicorn がこの `app` を使う。
app = create_app()


if __name__ == "__main__":
    # リローダーを有効にするとスケジューラが二重起動するため無効にしている
    app.run(host="0.0.0.0", port=config.PORT, use_reloader=False)
