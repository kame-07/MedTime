# お薬リマインダー LINE ボット

指定した時間になると「お薬を飲みましたか?」と確認のLINEを送り、
返信に応じて再確認を行うボットです。

## できること

### 1. 指定時間の服薬確認
予定時刻になると、次のメッセージをプッシュ送信します(「はい」「いいえ」のクイックリプライ付き)。

```
お薬を飲みましたか?
「はい」か「いいえ」でお答えください。
```

| 返信 | 動作 |
| --- | --- |
| **はい** | 確認を終了し、次の予定時刻まで何も送りません |
| **いいえ** | 5分後にもう一度確認します |
| **5分間 無返答** | 「いいえ」と同じ扱いで、もう一度確認します |

「はい」が返るまで5分おきに再確認を繰り返します。
(`MAX_RETRY_COUNT` で再送回数の上限を設けることもできます)

### 2. 予定時刻の管理(LINEで送るだけ)

| 送るメッセージ | 動作 |
| --- | --- |
| `時間追加22時00` | 22:00 を追加 |
| `時間変更22時00を19時00` | 22:00 を 19:00 に変更 |
| `時間削除22時00` | 22:00 を削除 |
| `時間一覧` | 登録済みの時刻を表示 |
| `ヘルプ` | 使い方を表示 |

時刻は `22時00` / `22時00分` / `22:00` / `22時` のどれでも受け付けます。
全角数字(`２２時００`)もそのまま使えます。

### まとめて指定する

追加・変更・削除は、いくつでも一度に指定できます。

| 送るメッセージ | 動作 |
| --- | --- |
| `時間追加8時00 12時00 22時00` | 3件まとめて追加 |
| `時間削除8時00 12時00` | 2件まとめて削除 |
| `時間変更8時00を7時00 22時00を21時00` | 2件まとめて変更 |

区切りは空白のほか、改行 / `,` / `、` / `と` も使えます。
結果は「追加しました」「すでに登録されています」のように種類ごとに分けて返信します。

指定の中に1つでも読み取れない時刻があった場合は、**どれも実行せず**にやり直しを促します
(一部だけ中途半端に反映されるのを防ぐため)。

## セットアップ

### 1. LINE Developers Console での準備
1. [LINE Developers](https://developers.line.biz/) で Messaging API チャネルを作成
2. **チャネルシークレット**(`CHANNEL_SECRET`)を控える
3. **チャネルアクセストークン(長期)**(`CHANNEL_ACCESS_TOKEN`)を発行して控える
4. LINE Official Account Manager で**応答メッセージをオフ**、**Webhookをオン**にする

### 2. 環境構築

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3. 環境変数の設定

`.env.example` をコピーして `.env` を作り、値を埋めます。

```powershell
Copy-Item .env.example .env
```

```
CHANNEL_ACCESS_TOKEN=（発行したトークン）
CHANNEL_SECRET=（チャネルシークレット）
```

`.env` は `.gitignore` 済みです。コミットしないでください。

### 4. 起動

```powershell
.\.venv\Scripts\python.exe app.py
```

### 5. Webhook URL の登録

別のターミナルで ngrok を起動します。

```powershell
ngrok http 5000
```

表示された HTTPS の URL に `/callback` を付けたものを、
LINE Developers Console の **Webhook URL** に設定して「検証」を押します。

```
https://xxxx-xx-xx-xx-xx.ngrok-free.app/callback
```

### 6. 使いはじめ
ボットを友だち追加すると使い方が送られてきます。
`時間追加8時00` のように送って予定時刻を登録してください。

## 設定項目(`.env`)

| 変数 | 既定値 | 説明 |
| --- | --- | --- |
| `CHANNEL_ACCESS_TOKEN` | (必須) | チャネルアクセストークン |
| `CHANNEL_SECRET` | (必須) | チャネルシークレット(署名検証に使用) |
| `TIMEZONE` | `Asia/Tokyo` | スケジュールの基準タイムゾーン |
| `RETRY_INTERVAL_MINUTES` | `5` | 再確認までの待ち時間(分) |
| `TIMEOUT_BEHAVIOR` | `immediate` | 無返答時の挙動。`immediate`=即再送 / `delayed`=さらに待ってから再送 |
| `MAX_RETRY_COUNT` | `0` | 1回の確認あたりの最大再送回数(`0`=無制限) |
| `DATA_FILE` | `data/schedules.json` | 予定・状態の保存先 |
| `PORT` | `5000` | 待ち受けポート |

## テスト

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## 構成

```
app.py                          Flask Webhookサーバー + スケジューラ起動
config.py                       環境変数の読み込み
messages.py                     ユーザーに送る文面
handlers/command_parser.py      受信テキスト → コマンドの解析
handlers/message_handler.py     コマンドの振り分けと返信文の決定
services/reminder_service.py    確認・再確認のスケジューリング
services/storage.py             予定時刻と確認待ち状態のJSON永続化
services/line_client.py         LINE Messaging API 送信ラッパー
tests/                          テストコード
```

LINE SDK に依存するのは `services/line_client.py` と `app.py` のみで、
コアロジックは SDK 非依存です。そのためテストでは実APIを呼ばずに検証できます。

## 補足

- 予定時刻はユーザーごとに保存されるため、複数人が同じボットを使えます。
- プロセスを再起動すると、保存済みの予定時刻から cron ジョブを組み直します。
  ただし再起動時点で「確認待ち」だったものは破棄され、次の予定時刻から再開します。
- LINE SDK は純Python実装の **v2 API**(`linebot.*`)を使っています。理由は
  `services/line_client.py` の冒頭コメントを参照してください。

## 本番デプロイ(Render)

PCを起動していなくても24時間動かし続けたい場合は、[Render](https://render.com/) にデプロイします。
月額 **$7(Web Service) + $0.25/GB(永続ディスク)** ≒ 月1,000円強かかります。

### 1. GitHub にリポジトリを作る
```powershell
git init
git add .
git commit -m "Initial commit"
```
GitHub上に新規リポジトリを作成し、案内される `git remote add` / `git push` を実行してプッシュする。
**`.env` は `.gitignore` 済みなのでプッシュされません。** 誤って直書きしていないか、push前に
`git status` で差分を確認してください。

### 2. Render で Web Service を作成
1. [Render](https://render.com/) にサインアップし、GitHubリポジトリを連携
2. 「New +」→「Web Service」で、このリポジトリを選択
3. 設定項目
   | 項目 | 値 |
   | --- | --- |
   | Runtime | Python 3(`.python-version` から自動検出される) |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `gunicorn --workers 1 --bind 0.0.0.0:$PORT app:app`(`Procfile` 済みなら省略可) |
   | Instance Type | **Starter**(Freeは常時起動できないため不可) |
4. **「Workers は必ず1のままにする。** 複数にすると確認メッセージのスケジューラが複数動き、
   同じ確認を二重に送ってしまう。

### 3. 環境変数を設定
Render の「Environment」タブで、`.env` の中身と同じものを1つずつ登録する
(`CHANNEL_ACCESS_TOKEN` / `CHANNEL_SECRET` / `TIMEZONE` など)。
加えて `DATA_FILE` は、次の手順で追加するディスクのマウント先に合わせて
`/var/data/schedules.json` のように設定する。

### 4. 永続ディスクを追加(必須)
これを追加しないと、再デプロイのたびに登録した予定時刻が消えてしまう。
1. Web Serviceの「Disks」タブで「Add Disk」
2. Mount Path に `/var/data` を指定、Size は 1GB で十分
3. 上記 `DATA_FILE=/var/data/schedules.json` と一致させる

### 5. デプロイ後、Webhook URL を更新
デプロイが終わると `https://<サービス名>.onrender.com` のような固定URLが発行される。
LINE Developers Console の Webhook URL を
`https://<サービス名>.onrender.com/callback` に更新し、「検証」で成功を確認する。

### 6. ローカルの後片付け
Render上で動くようになったら、ローカルPCの `start.bat` と `cloudflared` は不要になるので終了してよい。
