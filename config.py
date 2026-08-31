"""環境変数の読み込み。

シークレットは .env で管理し、コードには直書きしない。
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


CHANNEL_ACCESS_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN", "").strip()
CHANNEL_SECRET = os.environ.get("CHANNEL_SECRET", "").strip()

TIMEZONE = os.environ.get("TIMEZONE", "Asia/Tokyo").strip() or "Asia/Tokyo"

RETRY_INTERVAL_MINUTES = _int_env("RETRY_INTERVAL_MINUTES", 5)

# immediate: 無返答タイムアウト時点で即再送 / delayed: さらに RETRY_INTERVAL_MINUTES 待ってから再送
TIMEOUT_BEHAVIOR = os.environ.get("TIMEOUT_BEHAVIOR", "immediate").strip().lower()

# 0 は無制限(「はい」が返るまで再送し続ける)
MAX_RETRY_COUNT = _int_env("MAX_RETRY_COUNT", 0)

DATA_FILE = os.environ.get("DATA_FILE", "data/schedules.json").strip()

PORT = _int_env("PORT", 5000)


def validate() -> None:
    """起動時に必須の環境変数が揃っているか確認する。"""
    missing = [
        name
        for name, value in (
            ("CHANNEL_ACCESS_TOKEN", CHANNEL_ACCESS_TOKEN),
            ("CHANNEL_SECRET", CHANNEL_SECRET),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "環境変数が設定されていません: "
            + ", ".join(missing)
            + " (.env.example をコピーして .env を作成してください)"
        )
