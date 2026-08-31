"""ユーザーに送るテキストを一箇所にまとめる。"""

from typing import List

from handlers.command_parser import format_time_jp

CONFIRM = "お薬を飲みましたか?\n「はい」か「いいえ」でお答えください。"

CONFIRM_AGAIN = "【再確認】お薬を飲みましたか?\n「はい」か「いいえ」でお答えください。"

YES_ACCEPTED = "確認しました。次の予定時刻までお知らせしません。おだいじに。"

NO_ACCEPTED_TEMPLATE = "わかりました。{minutes}分後にもう一度確認します。"

RETRY_LIMIT_REACHED = (
    "再確認の上限に達したため、今回の確認を終了します。\n"
    "お薬を飲んだら「はい」と送ってください。"
)

NO_PENDING = "現在、確認中のお薬はありません。\n次の予定時刻になったらお知らせします。"

HELP = (
    "【お薬リマインダーの使い方】\n"
    "\n"
    "▼ 予定時刻の管理\n"
    "・追加: 時間追加22時00\n"
    "・変更: 時間変更22時00を19時00\n"
    "・削除: 時間削除22時00\n"
    "・一覧: 時間一覧\n"
    "\n"
    "▼ 服薬確認への返信\n"
    "予定時刻になったら確認メッセージを送ります。\n"
    "「はい」…次の予定時刻までお知らせしません。\n"
    "「いいえ」…5分後にもう一度確認します。\n"
    "5分間お返事がない場合も、もう一度確認します。\n"
    "\n"
    "使い方がわからなくなったら「ヘルプ」と送ってください。"
)

WELCOME = "友だち追加ありがとうございます!\nお薬の時間をお知らせします。\n\n" + HELP

INVALID_TIME_TEMPLATE = (
    "時刻を読み取れませんでした。\n"
    "次のように送ってください。\n"
    "例) {example}"
)

INVALID_TIME_EXAMPLES = {
    "時間追加": "時間追加22時00",
    "時間変更": "時間変更22時00を19時00",
    "時間削除": "時間削除22時00",
}

UNKNOWN = "コマンドを認識できませんでした。\n「ヘルプ」と送ると使い方を表示します。"

# 確認待ちのときに「はい」「いいえ」以外が届いた場合
PENDING_NUDGE = "お薬を飲みましたか?\n「はい」か「いいえ」でお答えください。"


def added(hhmm: str, times: List[str]) -> str:
    return f"{format_time_jp(hhmm)} を追加しました。\n\n" + time_list(times)


def already_exists(hhmm: str, times: List[str]) -> str:
    return f"{format_time_jp(hhmm)} はすでに登録されています。\n\n" + time_list(times)


def changed(old: str, new: str, times: List[str]) -> str:
    return (
        f"{format_time_jp(old)} を {format_time_jp(new)} に変更しました。\n\n"
        + time_list(times)
    )


def not_found(hhmm: str, times: List[str]) -> str:
    return f"{format_time_jp(hhmm)} は登録されていません。\n\n" + time_list(times)


def duplicate(hhmm: str, times: List[str]) -> str:
    return f"{format_time_jp(hhmm)} はすでに登録されています。\n\n" + time_list(times)


def deleted(hhmm: str, times: List[str]) -> str:
    return f"{format_time_jp(hhmm)} を削除しました。\n\n" + time_list(times)


def time_list(times: List[str]) -> str:
    if not times:
        return "現在、登録されている時刻はありません。\n「時間追加22時00」のように送ると追加できます。"
    lines = "\n".join(f"・{format_time_jp(t)}" for t in times)
    return f"【現在の予定時刻】\n{lines}"
