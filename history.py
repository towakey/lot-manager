#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
history.py - 作業履歴取得CGI
GET: ?username=admin&limit=500
"""

import csv
import json
import os
import sys

from session_auth import validate_session

if sys.version_info[0] >= 3:
    from urllib.parse import parse_qs
else:
    from urlparse import parse_qs

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SETTING_PATH = os.path.join(SCRIPT_DIR, "setting.json")
LOG_PATH = os.path.join(SCRIPT_DIR, "log.csv")
CHANGE_ACTIONS = set(["ロット変更", "データ保存", "レポート取込(全体)"])


def send_json(obj):
    body = json.dumps(obj, ensure_ascii=True)
    output = "Content-Type: application/json; charset=utf-8\r\n"
    output += "Access-Control-Allow-Origin: *\r\n"
    output += "Access-Control-Allow-Headers: Content-Type, X-Session-Token\r\n"
    output += "Cache-Control: no-store\r\n"
    output += "Content-Length: {}\r\n".format(len(body))
    output += "\r\n"
    output += body
    sys.stdout.buffer.write(output.encode("ascii"))
    sys.stdout.buffer.flush()


def main():
    method = os.environ.get("REQUEST_METHOD", "GET").upper()
    if method == "OPTIONS":
        send_json({"success": True})
        return
    if method != "GET":
        send_json({"success": False, "error": "GET のみ受け付けます"})
        return

    try:
        with open(SETTING_PATH, mode="r", encoding="utf-8-sig") as f:
            setting = json.load(f)
    except Exception as e:
        send_json({"success": False, "error": "setting.json 読み込み失敗: " + str(e)})
        return

    parsed = parse_qs(
        os.environ.get("QUERY_STRING", ""),
        keep_blank_values=True,
    )
    username = parsed.get("username", [""])[0].strip()
    session_token = os.environ.get("HTTP_X_SESSION_TOKEN", "")
    try:
        limit = int(parsed.get("limit", ["500"])[0])
    except (TypeError, ValueError):
        limit = 500
    limit = max(1, min(limit, 1000))

    users = setting.get("users", [])
    matched_user = None
    display_names = {}
    for user in users:
        user_name = user.get("username", "")
        if user_name:
            display_names[user_name] = user.get("display_name", user_name)
        if user_name == username:
            matched_user = user

    if matched_user is None:
        send_json({"success": False, "error": "ユーザーが存在しません"})
        return
    if not validate_session(username, session_token):
        send_json({"success": False, "error": "ログイン情報が無効です。再ログインしてください"})
        return
    if matched_user.get("can_view_history", False) is not True:
        send_json({"success": False, "error": "作業履歴を閲覧する権限がありません"})
        return

    if not os.path.exists(LOG_PATH):
        send_json({"success": True, "history": []})
        return

    try:
        history = []
        with open(LOG_PATH, mode="r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                action = row.get("操作", "")
                if action not in CHANGE_ACTIONS:
                    continue

                raw_detail = row.get("詳細", "")
                detail = {}
                if action == "ロット変更":
                    try:
                        detail = json.loads(raw_detail)
                    except (TypeError, ValueError):
                        detail = {}

                row_username = row.get("ユーザー名", "")
                history.append({
                    "timestamp": row.get("日時", ""),
                    "username": row_username,
                    "display_name": display_names.get(row_username, row_username),
                    "action": action,
                    "source": detail.get("source", ""),
                    "customer": detail.get("customer", ""),
                    "model": detail.get("model", ""),
                    "lot_number": detail.get("lot_number", ""),
                    "field": detail.get("field", ""),
                    "before": detail.get("before", ""),
                    "after": detail.get("after", ""),
                    "detail": raw_detail if not detail else "",
                })
    except Exception as e:
        send_json({"success": False, "error": "作業履歴読み込み失敗: " + str(e)})
        return

    send_json({"success": True, "history": list(reversed(history[-limit:]))})


if __name__ == "__main__":
    main()
