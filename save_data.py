#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
save_data.py - 変更保存CGI
POST: {
  "username": "admin",
  "model": "AAA001",
  "changes": [
    {"lot_number": "ABC001", "new_order_number": "BBB"},
    ...
  ]
}
変更のあったロット行の注文番号のみ更新してCSVを保存する。
"""

import json
import csv
import os
import sys
import shutil
from datetime import datetime

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
SETTING_PATH = os.path.join(SCRIPT_DIR, "setting.json")
LOG_PATH     = os.path.join(SCRIPT_DIR, "log.csv")

ENCODING_MAP = {
    "utf-8": "utf-8", "utf-8-sig": "utf-8-sig", "utf-8-bom": "utf-8-sig",
    "shift-jis": "shift_jis", "shift_jis": "shift_jis", "sjis": "shift_jis",
    "cp932": "cp932", "windows-31j": "cp932",
    "euc-jp": "euc_jp", "euc_jp": "euc_jp",
}

NEWLINE_MAP = {
    "crlf": "\r\n", "lf": "\n", "cr": "\r",
    "\r\n": "\r\n", "\n": "\n", "\r": "\r",
}

def send_json(obj):
    body = json.dumps(obj, ensure_ascii=True)
    output = "Content-Type: application/json; charset=utf-8\r\n"
    output += "Access-Control-Allow-Origin: *\r\n"
    output += "Content-Length: {}\r\n".format(len(body))
    output += "\r\n"
    output += body
    sys.stdout.buffer.write(output.encode("ascii"))
    sys.stdout.buffer.flush()

def normalize_encoding(enc):
    return ENCODING_MAP.get(enc.lower().replace(" ", ""), enc)

def normalize_newline(nl):
    key = nl.lower() if nl.lower() in NEWLINE_MAP else nl
    return NEWLINE_MAP.get(key, "\r\n")

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
        with open(SETTING_PATH, mode="r", encoding="utf-8-sig") as f:
            setting = json.load(f)
    except Exception as e:
        send_json({"success": False, "error": "setting.json 読み込み失敗: " + str(e)})
        return

    data_file = setting.get("data_file", {})
    col_map   = setting.get("column_mapping", {})
    users     = setting.get("users", [])

    try:
        content_length = int(os.environ.get("CONTENT_LENGTH", 0))
        if content_length <= 0:
            send_json({"success": False, "error": "データが空です"})
            return
        raw  = sys.stdin.buffer.read(content_length)
        data = json.loads(raw.decode("utf-8"))
    except Exception as e:
        send_json({"success": False, "error": "リクエスト解析失敗: " + str(e)})
        return

    username = data.get("username", "").strip()
    model    = data.get("model", "")
    changes  = data.get("changes", [])

    if not username:
        send_json({"success": False, "error": "username は必須です"})
        return

    matched_user = None
    for u in users:
        if u.get("username") == username:
            matched_user = u
            break
    if matched_user is None:
        send_json({"success": False, "error": "ユーザーが存在しません"})
        return

    if not model:
        send_json({"success": False, "error": "機種が指定されていません"})
        return

    if not changes:
        send_json({"success": True, "message": "変更はありません", "updated_rows": 0})
        return

    csv_path = data_file.get("csv_file_path", "")
    if not os.path.isabs(csv_path):
        csv_path = os.path.join(SCRIPT_DIR, csv_path)

    read_enc      = normalize_encoding(data_file.get("read_encoding", "utf-8"))
    write_enc     = normalize_encoding(data_file.get("write_encoding", "utf-8"))
    newline       = normalize_newline(data_file.get("newline", "\r\n"))
    create_backup = data_file.get("create_backup", True)

    model_header         = col_map.get("model", "機種")
    order_header         = col_map.get("order_number", "注文番号")
    lot_header           = col_map.get("lot_number", "LOT番号")
    shipped_order_header = col_map.get("shipped_order_number", "")
    shipped_qty_header   = col_map.get("shipped_quantity", "")

    try:
        headers = []
        rows = []
        with open(csv_path, mode="r", encoding=read_enc, newline="") as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if i == 0:
                    headers = row
                else:
                    rows.append(row)
    except Exception as e:
        send_json({"success": False, "error": "CSV読み込みエラー: " + str(e)})
        return

    try:
        model_idx = headers.index(model_header)
        order_idx = headers.index(order_header)
        lot_idx   = headers.index(lot_header)
    except ValueError as e:
        send_json({"success": False, "error": "ヘッダーマッピングエラー: " + str(e)})
        return

    shipped_order_idx = -1
    shipped_qty_idx = -1
    if shipped_order_header:
        try:
            shipped_order_idx = headers.index(shipped_order_header)
        except ValueError:
            pass
    if shipped_qty_header:
        try:
            shipped_qty_idx = headers.index(shipped_qty_header)
        except ValueError:
            pass

    change_map = {}
    for c in changes:
        lot_num   = c.get("lot_number", "")
        new_order = c.get("new_order_number", "")
        is_shipped = c.get("shipped", False)
        if lot_num:
            change_map[lot_num] = {"new_order": new_order, "shipped": is_shipped}

    updated_count = 0
    max_idx = max(model_idx, order_idx, lot_idx)
    for row in rows:
        if len(row) > max_idx:
            if row[model_idx] == model and row[lot_idx] in change_map:
                change_info = change_map[row[lot_idx]]
                if change_info["shipped"] and shipped_order_idx >= 0:
                    # 出荷済みロット: 出荷時注文番号を更新
                    if len(row) > shipped_order_idx:
                        row[shipped_order_idx] = change_info["new_order"]
                else:
                    # 通常ロット: 注文番号を更新
                    row[order_idx] = change_info["new_order"]
                updated_count += 1

    if create_backup and os.path.exists(csv_path):
        timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = csv_path + "." + timestamp + ".bak"
        shutil.copy2(csv_path, backup_path)

    try:
        with open(csv_path, mode="w", encoding=write_enc, newline="") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL, lineterminator=newline)
            writer.writerow(headers)
            for row in rows:
                writer.writerow(row)
    except Exception as e:
        send_json({"success": False, "error": "CSV書き込みエラー: " + str(e)})
        return

    write_log(username, "データ保存",
              "機種={} 更新行数={}".format(model, updated_count))

    send_json({
        "success":      True,
        "message":      "保存しました ({} 行更新)".format(updated_count),
        "updated_rows": updated_count,
    })

if __name__ == "__main__":
    main()
