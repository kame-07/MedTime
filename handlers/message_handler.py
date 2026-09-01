"""受信テキストをコマンドに変換し、対応する処理と返信文を決める。

LINE SDK には依存しないので、単体テストでは文字列を渡すだけで検証できる。
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional

import messages
from handlers import command_parser
from handlers.command_parser import Command

logger = logging.getLogger(__name__)

YES_NO_LABELS = ["はい", "いいえ"]


@dataclass
class Reply:
    text: str
    quick_reply_labels: Optional[List[str]] = field(default=None)


class MessageHandler:
    def __init__(self, storage, reminder_service):
        self._storage = storage
        self._reminder = reminder_service

    def handle_text(self, user_id: str, text: str) -> Reply:
        self._storage.ensure_user(user_id)
        command = command_parser.parse(text)

        if command.kind == command_parser.YES:
            return Reply(self._reminder.handle_yes(user_id))

        if command.kind == command_parser.NO:
            return Reply(self._reminder.handle_no(user_id))

        if command.kind == command_parser.ADD:
            return Reply(self._add(user_id, command))

        if command.kind == command_parser.CHANGE:
            return Reply(self._change(user_id, command))

        if command.kind == command_parser.DELETE:
            return Reply(self._delete(user_id, command))

        if command.kind == command_parser.DELETE_ALL:
            return Reply(self._delete_all(user_id))

        if command.kind == command_parser.LIST:
            return Reply(messages.time_list(self._storage.get_times(user_id)))

        if command.kind == command_parser.HELP:
            return Reply(messages.HELP)

        if command.kind == command_parser.INVALID_TIME:
            example = messages.INVALID_TIME_EXAMPLES.get(
                command.keyword or "", "時間追加22時00"
            )
            return Reply(messages.INVALID_TIME_TEMPLATE.format(example=example))

        # 確認待ちの最中に関係のない文言が届いたら、返信の仕方を案内し直す
        if self._storage.get_pending(user_id):
            return Reply(messages.PENDING_NUDGE, quick_reply_labels=YES_NO_LABELS)

        return Reply(messages.UNKNOWN)

    def handle_follow(self, user_id: str) -> Reply:
        """友だち追加(またはブロック解除)されたとき。"""
        self._storage.ensure_user(user_id)
        return Reply(messages.WELCOME)

    # ------------------------------------------------------------------
    # 予定時刻の追加・変更・削除
    # ------------------------------------------------------------------
    def _add(self, user_id: str, command: Command) -> str:
        added, skipped = [], []
        for hhmm in command.times:
            if self._storage.add_time(user_id, hhmm):
                added.append(hhmm)
            else:
                skipped.append(hhmm)

        # 予定が1件でも変わったときだけ、cronジョブを組み直す
        if added:
            self._reminder.sync_user_jobs(user_id)
            logger.info("times added: user=%s times=%s", user_id, added)
        return messages.added(added, skipped, self._storage.get_times(user_id))

    def _change(self, user_id: str, command: Command) -> str:
        changed, missing, duplicated = [], [], []
        for old, new in command.changes:
            result = self._storage.change_time(user_id, old, new)
            if result == "ok":
                changed.append((old, new))
            elif result == "not_found":
                missing.append(old)
            else:
                duplicated.append(new)

        if changed:
            self._reminder.sync_user_jobs(user_id)
            logger.info("times changed: user=%s changes=%s", user_id, changed)
        return messages.changed(
            changed, missing, duplicated, self._storage.get_times(user_id)
        )

    def _delete(self, user_id: str, command: Command) -> str:
        deleted, missing = [], []
        for hhmm in command.times:
            if self._storage.remove_time(user_id, hhmm):
                deleted.append(hhmm)
            else:
                missing.append(hhmm)

        if deleted:
            self._reminder.sync_user_jobs(user_id)
            logger.info("times deleted: user=%s times=%s", user_id, deleted)
        return messages.deleted(deleted, missing, self._storage.get_times(user_id))

    def _delete_all(self, user_id: str) -> str:
        removed = self._storage.clear_times(user_id)
        if not removed:
            return messages.deleted_all([], pending_cancelled=False)

        # 予定を全部消したのに追いかけ確認だけが残らないよう、確認待ちも解除する
        pending_cancelled = self._reminder.cancel_pending(user_id)
        self._reminder.sync_user_jobs(user_id)
        logger.info("all times deleted: user=%s times=%s", user_id, removed)
        return messages.deleted_all(removed, pending_cancelled)
