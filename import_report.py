#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
import_report.py - レポート取込CGI（データソース全体反映）
POST: {
  "username": "admin",
  "report_csv": "LOT番号,注文番号\nABC001,CCC\n..."
}
レポートCSVのロット番号→注文番号マッピングをデータソース全体に反映する。
出荷済みロット（出荷時個数 > 0）は除外。
"""

import json
import csv
import os
import sys
import shutil
from datetime import datetime

if sys.version_info[0] >= 3:
    import io

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
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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

    users = setting.get("users", [])

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

    username   = data.get("username", "").strip()
    report_csv = data.get("report_csv", "")

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

    if matched_user.get("username") != "admin":
        send_json({"success": False, "error": "この操作は管理者のみ実行できます"})
        return

    if not report_csv:
        send_json({"success": False, "error": "レポートデータが空です"})
        return

    # レポート取込設定
    report_import_cfg = setting.get("report_import", {})
    report_import_col = report_import_cfg.get("column_mapping", {})
    report_lot_header   = report_import_col.get("lot_number", "")
    report_order_header = report_import_col.get("order_number", "")

    if not report_lot_header or not report_order_header:
        send_json({"success": False, "error": "レポート取込のカラムマッピングが設定されていません"})
        return

    # レポートCSVをパース
    report_lines = report_csv.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if len(report_lines) < 2:
        send_json({"success": False, "error": "レポートにデータがありません"})
        return

    report_reader = csv.reader(report_lines)
    report_headers = None
    report_lot_idx = -1
    report_order_idx = -1
    import_map = {}

    for ri, rrow in enumerate(report_reader):
        if ri == 0:
            report_headers = rrow
            for h in range(len(report_headers)):
                if report_headers[h].strip() == report_lot_header:
                    report_lot_idx = h
                if report_headers[h].strip() == report_order_header:
                    report_order_idx = h
            if report_lot_idx < 0 or report_order_idx < 0:
                send_json({"success": False,
                           "error": "レポートに必要なヘッダーが見つかりません ({}, {})".format(
                               report_lot_header, report_order_header)})
                return
        else:
            if len(rrow) > max(report_lot_idx, report_order_idx):
                lot_num = rrow[report_lot_idx].strip()
                order_num = rrow[report_order_idx].strip()
                if lot_num:
                    import_map[lot_num] = order_num

    if not import_map:
        send_json({"success": False, "error": "レポートに有効なデータがありません"})
        return

    # データソースCSV読み込み
    data_file = setting.get("data_file", {})
    col_map   = setting.get("column_mapping", {})

    csv_path = data_file.get("csv_file_path", "")
    if not os.path.isabs(csv_path):
        csv_path = os.path.join(SCRIPT_DIR, csv_path)

    read_enc      = normalize_encoding(data_file.get("read_encoding", "utf-8"))
    write_enc     = normalize_encoding(data_file.get("write_encoding", "utf-8"))
    newline       = normalize_newline(data_file.get("newline", "\r\n"))
    create_backup = data_file.get("create_backup", True)

    lot_header           = col_map.get("lot_number", "LOT番号")
    order_header         = col_map.get("order_number", "注文番号")
    shipped_qty_header   = col_map.get("shipped_quantity", "")

    try:
        csv_headers = []
        rows = []
        with open(csv_path, mode="r", encoding=read_enc, newline="") as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if i == 0:
                    csv_headers = row
                else:
                    rows.append(row)
    except Exception as e:
        send_json({"success": False, "error": "CSV読み込みエラー: " + str(e)})
        return

    try:
        lot_idx   = csv_headers.index(lot_header)
        order_idx = csv_headers.index(order_header)
    except ValueError as e:
        send_json({"success": False, "error": "ヘッダーマッピングエラー: " + str(e)})
        return

    shipped_qty_idx = -1
    if shipped_qty_header:
        try:
            shipped_qty_idx = csv_headers.index(shipped_qty_header)
        except ValueError:
            pass

    # マッピング適用（出荷済みロットは除外）
    updated_count = 0
    for row in rows:
        if len(row) <= max(lot_idx, order_idx):
            continue

        # 出荷済み判定
        is_shipped = False
        if shipped_qty_idx >= 0 and len(row) > shipped_qty_idx:
            try:
                if row[shipped_qty_idx].strip() and int(row[shipped_qty_idx].strip()) > 0:
                    is_shipped = True
            except (ValueError, TypeError):
                pass

        if is_shipped:
            continue

        lot_num = row[lot_idx].strip()
        if lot_num in import_map:
            new_order = import_map[lot_num]
            if row[order_idx] != new_order:
                row[order_idx] = new_order
                updated_count += 1

    # バックアップ
    if create_backup and os.path.exists(csv_path):
        timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = csv_path + "." + timestamp + ".bak"
        shutil.copy2(csv_path, backup_path)

    # CSV書き込み
    try:
        with open(csv_path, mode="w", encoding=write_enc, newline="") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL, lineterminator=newline)
            writer.writerow(csv_headers)
            for row in rows:
                writer.writerow(row)
    except Exception as e:
        send_json({"success": False, "error": "CSV書き込みエラー: " + str(e)})
        return

    write_log(username, "レポート取込(全体)",
              "レポート件数={} 更新行数={}".format(len(import_map), updated_count))

    send_json({
        "success":      True,
        "message":      "データソース全体に反映しました ({} 行更新)".format(updated_count),
        "updated_rows": updated_count,
    })

if __name__ == "__main__":
    main()
