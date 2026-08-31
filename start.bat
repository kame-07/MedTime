@echo off
cd /d "%~dp0"

echo ============================================
echo   お薬リマインダー LINE ボット
echo ============================================
echo.
echo 起動しています...
echo.
echo  * 止めるときは Ctrl キーを押しながら C キー
echo  * このウィンドウは閉じずに開いたままにしてください
echo.

".venv\Scripts\python.exe" app.py

echo.
echo ボットが停止しました。
pause
