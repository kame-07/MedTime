"""服薬確認の一連の流れ(確認 → 返信 → 再確認)を検証する。"""

from types import SimpleNamespace

import pytest

import messages
from handlers.message_handler import MessageHandler
from services.reminder_service import ReminderService
from services.storage import Storage
from tests.fakes import FakeLineClient, FakeScheduler

USER = "U_test"
REMIND_JOB = f"remind:{USER}:22:00"
FOLLOWUP_JOB = f"followup:{USER}"


def build_env(tmp_path, max_retry_count=0, timeout_behavior="immediate"):
    storage = Storage(str(tmp_path / "data" / "schedules.json"))
    scheduler = FakeScheduler()
    line = FakeLineClient()
    reminder = ReminderService(
        scheduler=scheduler,
        storage=storage,
        line_client=line,
        timezone="Asia/Tokyo",
        retry_interval_minutes=5,
        max_retry_count=max_retry_count,
        timeout_behavior=timeout_behavior,
    )
    handler = MessageHandler(storage, reminder)
    return SimpleNamespace(
        storage=storage, scheduler=scheduler, line=line, reminder=reminder, handler=handler
    )


@pytest.fixture
def env(tmp_path):
    return build_env(tmp_path)


def register_and_fire(env):
    """22時00分を登録し、その予定時刻が来た状態にする。"""
    env.handler.handle_text(USER, "時間追加22時00")
    env.scheduler.fire(REMIND_JOB)


# ----------------------------------------------------------------------
# 予定時刻の管理
# ----------------------------------------------------------------------
def test_add_registers_cron_job(env):
    reply = env.handler.handle_text(USER, "時間追加22時00")
    assert "22時00分" in reply.text
    assert env.scheduler.get_job(REMIND_JOB) is not None


def test_change_replaces_cron_job(env):
    env.handler.handle_text(USER, "時間追加22時00")
    reply = env.handler.handle_text(USER, "時間変更22時00を19時00")
    assert "19時00分" in reply.text
    assert env.scheduler.get_job(REMIND_JOB) is None
    assert env.scheduler.get_job(f"remind:{USER}:19:00") is not None


def test_delete_removes_cron_job(env):
    env.handler.handle_text(USER, "時間追加22時00")
    env.handler.handle_text(USER, "時間削除22時00")
    assert env.scheduler.get_job(REMIND_JOB) is None
    assert env.storage.get_times(USER) == []


def test_delete_unregistered_time(env):
    reply = env.handler.handle_text(USER, "時間削除22時00")
    assert "登録されていません" in reply.text


# ----------------------------------------------------------------------
# 予定時刻になったとき
# ----------------------------------------------------------------------
def test_reminder_sends_confirmation_and_arms_timeout(env):
    register_and_fire(env)
    assert env.line.pushed == [(USER, messages.CONFIRM)]
    assert env.storage.get_pending(USER) == {"time": "22:00", "sent_count": 1}
    assert env.scheduler.get_job(FOLLOWUP_JOB) is not None


# ----------------------------------------------------------------------
# 「はい」
# ----------------------------------------------------------------------
def test_yes_clears_pending_and_cancels_followup(env):
    register_and_fire(env)
    reply = env.handler.handle_text(USER, "はい")

    assert reply.text == messages.YES_ACCEPTED
    assert env.storage.get_pending(USER) is None
    assert env.scheduler.get_job(FOLLOWUP_JOB) is None
    # 次の予定時刻までは何も送らない
    assert len(env.line.pushed) == 1


def test_yes_without_pending(env):
    assert env.handler.handle_text(USER, "はい").text == messages.NO_PENDING


# ----------------------------------------------------------------------
# 「いいえ」
# ----------------------------------------------------------------------
def test_no_resends_after_interval(env):
    register_and_fire(env)
    reply = env.handler.handle_text(USER, "いいえ")
    assert "5分後" in reply.text

    # 「いいえ」の時点ではまだ再送していない
    assert len(env.line.pushed) == 1

    env.scheduler.fire_once(FOLLOWUP_JOB)
    assert env.line.pushed[1] == (USER, messages.CONFIRM_AGAIN)
    assert env.storage.get_pending(USER)["sent_count"] == 2
    # 再送後はふたたび無返答タイムアウトを見張る
    assert env.scheduler.get_job(FOLLOWUP_JOB) is not None


def test_yes_after_no_cancels_scheduled_resend(env):
    register_and_fire(env)
    env.handler.handle_text(USER, "いいえ")
    env.handler.handle_text(USER, "はい")

    assert env.scheduler.get_job(FOLLOWUP_JOB) is None
    assert env.storage.get_pending(USER) is None
    assert len(env.line.pushed) == 1


def test_no_without_pending(env):
    assert env.handler.handle_text(USER, "いいえ").text == messages.NO_PENDING


# ----------------------------------------------------------------------
# 無返答タイムアウト(「いいえ」と同じ扱い)
# ----------------------------------------------------------------------
def test_timeout_resends_immediately(env):
    register_and_fire(env)
    env.scheduler.fire_once(FOLLOWUP_JOB)  # 5分間無返答

    assert env.line.pushed[1] == (USER, messages.CONFIRM_AGAIN)
    assert env.storage.get_pending(USER)["sent_count"] == 2
    assert env.scheduler.get_job(FOLLOWUP_JOB) is not None


def test_timeout_repeats_until_yes(env):
    register_and_fire(env)
    for _ in range(3):
        env.scheduler.fire_once(FOLLOWUP_JOB)
    assert len(env.line.pushed) == 4

    env.handler.handle_text(USER, "はい")
    assert env.scheduler.get_job(FOLLOWUP_JOB) is None


def test_timeout_delayed_behavior(tmp_path):
    env = build_env(tmp_path, timeout_behavior="delayed")
    register_and_fire(env)

    env.scheduler.fire_once(FOLLOWUP_JOB)  # タイムアウト。さらに5分待つ
    assert len(env.line.pushed) == 1
    assert env.scheduler.get_job(FOLLOWUP_JOB) is not None

    env.scheduler.fire_once(FOLLOWUP_JOB)  # 待機後の再送
    assert env.line.pushed[1] == (USER, messages.CONFIRM_AGAIN)


def test_timeout_after_yes_does_nothing(env):
    """「はい」直後にタイムアウトジョブが走っても再送しない。"""
    register_and_fire(env)
    job = env.scheduler.get_job(FOLLOWUP_JOB)
    env.handler.handle_text(USER, "はい")

    job.func(*job.args)  # 取り消し漏れを模して直接実行する
    assert len(env.line.pushed) == 1


# ----------------------------------------------------------------------
# 再送回数の上限
# ----------------------------------------------------------------------
def test_max_retry_count_stops_resending(tmp_path):
    env = build_env(tmp_path, max_retry_count=1)
    register_and_fire(env)

    env.scheduler.fire_once(FOLLOWUP_JOB)  # 1回目の再送
    assert len(env.line.pushed) == 2

    env.scheduler.fire_once(FOLLOWUP_JOB)  # 上限に達したので打ち切る
    assert env.line.pushed[2] == (USER, messages.RETRY_LIMIT_REACHED)
    assert env.storage.get_pending(USER) is None
    assert env.scheduler.get_job(FOLLOWUP_JOB) is None


# ----------------------------------------------------------------------
# その他
# ----------------------------------------------------------------------
def test_unknown_text_during_pending_nudges(env):
    register_and_fire(env)
    reply = env.handler.handle_text(USER, "こんにちは")
    assert reply.text == messages.PENDING_NUDGE
    assert reply.quick_reply_labels == ["はい", "いいえ"]


def test_unknown_text_without_pending(env):
    assert env.handler.handle_text(USER, "こんにちは").text == messages.UNKNOWN


def test_restore_jobs_rebuilds_cron_and_drops_pending(tmp_path):
    env = build_env(tmp_path)
    register_and_fire(env)
    assert env.storage.get_pending(USER) is not None

    # 再起動を模して、同じ保存ファイルから作り直す
    restarted = build_env(tmp_path)
    restarted.reminder.restore_jobs()

    assert restarted.scheduler.get_job(REMIND_JOB) is not None
    assert restarted.storage.get_pending(USER) is None
