#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
auth.py - ログイン認証 CGI
POST: { "username": "...", "password": "..." }
"""

import json
import os
import sys
import csv
from datetime import datetime

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
SETTING_PATH = os.path.join(SCRIPT_DIR, "setting.json")
LOG_PATH     = os.path.join(SCRIPT_DIR, "log.csv")

def send_json(obj):
    body = json.dumps(obj, ensure_ascii=False)
    sys.stdout.write("Content-Type: application/json; charset=utf-8\r\n")
    sys.stdout.write("Access-Control-Allow-Origin: *\r\n")
    sys.stdout.write("\r\n")
    sys.stdout.write(body)
    sys.stdout.flush()

def write_log(username, action, detail=""):
    timestamp   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_exists = os.path.exists(LOG_PATH)
    try:
        with open(LOG_PATH, mode="a", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f, lineterminator="\r\n")
            if not file_exists:
                writer.writerow(["日時", "ユーザー名", "操作", "詳細"])
            writer.writerow([timestamp, username, action, detail])
    except Exception:
        pass

def main():
    method = os.environ.get("REQUEST_METHOD", "GET").upper()
    if method == "OPTIONS":
        send_json({"success": True})
        return
    if method != "POST":
        send_json({"success": False, "error": "POST のみ受け付けます"})
        return

    try:
        content_length = int(os.environ.get("CONTENT_LENGTH", 0))
        raw = sys.stdin.buffer.read(content_length)
        data = json.loads(raw.decode("utf-8"))
    except Exception as e:
        send_json({"success": False, "error": "リクエスト解析失敗: " + str(e)})
        return

    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        send_json({"success": False, "error": "ユーザー名とパスワードを入力してください"})
        return

    try:
        with open(SETTING_PATH, mode="r", encoding="utf-8") as f:
            setting = json.load(f)
    except json.JSONDecodeError as e:
        send_json({"success": False, "error": "setting.json の形式エラー: " + str(e)})
        return
    except Exception as e:
        send_json({"success": False, "error": "setting.json 読み込み失敗: " + str(e)})
        return

    users = setting.get("users", [])

    matched_user = None
    for u in users:
        if u.get("username") == username:
            matched_user = u
            break

    if matched_user is None:
        write_log(username, "ログイン失敗", "ユーザーが存在しない")
        send_json({"success": False, "error": "ユーザー名またはパスワードが違います"})
        return

    stored_password = matched_user.get("password", "")
    if not stored_password:
        write_log(username, "ログイン失敗", "パスワード未設定")
        send_json({"success": False, "error": "このユーザーはパスワードが設定されていません"})
        return

    if password != stored_password:
        write_log(username, "ログイン失敗", "パスワード不一致")
        send_json({"success": False, "error": "ユーザー名またはパスワードが違います"})
        return

    write_log(username, "ログイン")

    send_json({
        "success":      True,
        "username":     username,
        "display_name": matched_user.get("display_name", username),
    })

if __name__ == "__main__":
    main()
