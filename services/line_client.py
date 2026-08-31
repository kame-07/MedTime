"""LINE Messaging API への送信をまとめたラッパー。

主用途はプッシュ通知(push_text)。Webhook への応答には reply_text を使う。
テスト時はこのクラスを差し替えるだけで API 呼び出しを止められる。

【SDK の API バージョンについて】
line-bot-sdk の v3 API(linebot.v3.*)は pydantic に依存しており、
pydantic のネイティブ拡張(_pydantic_core)を読み込めない環境では import に失敗する。
ここでは純 Python 実装である v2 API(linebot.*)を使い、環境を選ばずに動くようにしている。
v3 へ移すときは、このファイルと app.py の import まわりだけを差し替えればよい。
"""

import logging
from typing import List, Optional

from linebot import LineBotApi
from linebot.models import (
    MessageAction,
    QuickReply,
    QuickReplyButton,
    TextSendMessage,
)

logger = logging.getLogger(__name__)

# 服薬確認メッセージに添えるクイックリプライ(「はい」「いいえ」をタップで返せる)
YES_NO_QUICK_REPLY_LABELS = ["はい", "いいえ"]


def build_message(
    text: str, quick_reply_labels: Optional[List[str]] = None
) -> TextSendMessage:
    if not quick_reply_labels:
        return TextSendMessage(text=text)
    items = [
        QuickReplyButton(action=MessageAction(label=label, text=label))
        for label in quick_reply_labels
    ]
    return TextSendMessage(text=text, quick_reply=QuickReply(items=items))


class LineClient:
    def __init__(self, channel_access_token: str):
        self._api = LineBotApi(channel_access_token)

    def push_text(
        self, user_id: str, text: str, quick_reply_labels: Optional[List[str]] = None
    ) -> None:
        self._api.push_message(user_id, build_message(text, quick_reply_labels))
        logger.info("push message sent: user=%s", user_id)

    def reply_text(
        self, reply_token: str, text: str, quick_reply_labels: Optional[List[str]] = None
    ) -> None:
        self._api.reply_message(reply_token, build_message(text, quick_reply_labels))
