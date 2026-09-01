"""服薬予定時刻と確認待ち状態を JSON ファイルに保存する。

プロセス再起動後もスケジュールを復元できるよう、変更のたびに永続化する。
将来 DB に差し替えられるよう、呼び出し側はこのクラスの API のみに依存する。
"""

import json
import os
import tempfile
import threading
from typing import Dict, List, Optional


class Storage:
    def __init__(self, path: str):
        self._path = path
        self._lock = threading.RLock()
        self._data: Dict = {"users": {}}
        self._load()

    # ------------------------------------------------------------------
    # 永続化
    # ------------------------------------------------------------------
    def _load(self) -> None:
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
        except (json.JSONDecodeError, OSError):
            # 壊れたファイルで起動不能になるより、空の状態から始める
            return
        if isinstance(loaded, dict) and isinstance(loaded.get("users"), dict):
            self._data = loaded

    def _save(self) -> None:
        directory = os.path.dirname(os.path.abspath(self._path))
        os.makedirs(directory, exist_ok=True)
        # 書き込み途中のクラッシュでファイルが壊れないよう、一時ファイル経由で置換する
        fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    def _user(self, user_id: str) -> Dict:
        users = self._data.setdefault("users", {})
        return users.setdefault(user_id, {"times": [], "pending": None})

    # ------------------------------------------------------------------
    # ユーザー
    # ------------------------------------------------------------------
    def ensure_user(self, user_id: str) -> None:
        with self._lock:
            users = self._data.setdefault("users", {})
            if user_id not in users:
                self._user(user_id)
                self._save()

    def user_ids(self) -> List[str]:
        with self._lock:
            return list(self._data.get("users", {}).keys())

    # ------------------------------------------------------------------
    # 予定時刻(すべて "HH:MM" 形式で保持する)
    # ------------------------------------------------------------------
    def get_times(self, user_id: str) -> List[str]:
        with self._lock:
            return list(self._user(user_id)["times"])

    def add_time(self, user_id: str, hhmm: str) -> bool:
        """追加できたら True、すでに登録済みなら False。"""
        with self._lock:
            times = self._user(user_id)["times"]
            if hhmm in times:
                return False
            times.append(hhmm)
            times.sort()
            self._save()
            return True

    def remove_time(self, user_id: str, hhmm: str) -> bool:
        """削除できたら True、未登録なら False。"""
        with self._lock:
            times = self._user(user_id)["times"]
            if hhmm not in times:
                return False
            times.remove(hhmm)
            self._save()
            return True

    def clear_times(self, user_id: str) -> List[str]:
        """登録済みの時刻をすべて削除し、削除した時刻を返す。"""
        with self._lock:
            user = self._user(user_id)
            removed = list(user["times"])
            if removed:
                user["times"] = []
                self._save()
            return removed

    def change_time(self, user_id: str, old: str, new: str) -> str:
        """変更結果を "ok" / "not_found" / "duplicate" で返す。"""
        with self._lock:
            times = self._user(user_id)["times"]
            if old not in times:
                return "not_found"
            if new != old and new in times:
                return "duplicate"
            times[times.index(old)] = new
            times.sort()
            self._save()
            return "ok"

    # ------------------------------------------------------------------
    # 確認待ち状態(ユーザーごとに1件)
    # ------------------------------------------------------------------
    def set_pending(self, user_id: str, hhmm: str, sent_count: int) -> None:
        with self._lock:
            self._user(user_id)["pending"] = {"time": hhmm, "sent_count": sent_count}
            self._save()

    def get_pending(self, user_id: str) -> Optional[Dict]:
        with self._lock:
            pending = self._user(user_id).get("pending")
            return dict(pending) if pending else None

    def clear_pending(self, user_id: str) -> None:
        with self._lock:
            user = self._user(user_id)
            if user.get("pending") is not None:
                user["pending"] = None
                self._save()

    def clear_all_pending(self) -> None:
        """再起動時に、宙に浮いた確認待ち状態を片付ける。"""
        with self._lock:
            changed = False
            for user in self._data.get("users", {}).values():
                if user.get("pending") is not None:
                    user["pending"] = None
                    changed = True
            if changed:
                self._save()
