#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
load_data.py - データ読み込みCGI
GET: ?username=admin                         → 顧客一覧を返す
GET: ?username=admin&customer=田中商事        → 該当顧客の機種一覧を返す
GET: ?username=admin&models=1                → 全機種一覧を返す
GET: ?username=admin&model=AAA001            → 指定機種のデータをグループ化して返す
"""

import json
import csv
import os
import sys
from datetime import datetime

if sys.version_info[0] >= 3:
    from urllib.parse import parse_qs
else:
    from urlparse import parse_qs

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
SETTING_PATH = os.path.join(SCRIPT_DIR, "setting.json")
LOG_PATH     = os.path.join(SCRIPT_DIR, "log.csv")

ENCODING_MAP = {
    "utf-8": "utf-8", "utf-8-sig": "utf-8-sig", "utf-8-bom": "utf-8-sig",
    "shift-jis": "shift_jis", "shift_jis": "shift_jis", "sjis": "shift_jis",
    "cp932": "cp932", "windows-31j": "cp932",
    "euc-jp": "euc_jp", "euc_jp": "euc_jp",
}

def send_json(obj):
    body = json.dumps(obj, ensure_ascii=True)
    output = "Content-Type: application/json; charset=utf-8\r\n"
    output += "Access-Control-Allow-Origin: *\r\n"
    output += "Cache-Control: no-store\r\n"
    output += "Content-Length: {}\r\n".format(len(body))
    output += "\r\n"
    output += body
    sys.stdout.buffer.write(output.encode("ascii"))
    sys.stdout.buffer.flush()

def normalize_encoding(enc):
    return ENCODING_MAP.get(enc.lower().replace(" ", ""), enc)

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
    try:
        with open(SETTING_PATH, mode="r", encoding="utf-8-sig") as f:
            setting = json.load(f)
    except Exception as e:
        send_json({"success": False, "error": "setting.json 読み込み失敗: " + str(e)})
        return

    data_file = setting.get("data_file", {})
    col_map   = setting.get("column_mapping", {})
    users     = setting.get("users", [])

    qs     = os.environ.get("QUERY_STRING", "")
    parsed = parse_qs(qs, keep_blank_values=True)
    username = parsed.get("username", [""])[0]
    customer = parsed.get("customer", [""])[0]
    model    = parsed.get("model", [""])[0]
    get_models = parsed.get("models", [""])[0]

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

    csv_path = data_file.get("csv_file_path", "")
    if not os.path.isabs(csv_path):
        csv_path = os.path.join(SCRIPT_DIR, csv_path)
    read_enc = normalize_encoding(data_file.get("read_encoding", "utf-8"))

    if not os.path.exists(csv_path):
        send_json({"success": False, "error": "ファイルが見つかりません: " + csv_path})
        return

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

    customer_header = col_map.get("customer", "")
    model_header    = col_map.get("model", "機種")
    order_header    = col_map.get("order_number", "注文番号")
    lot_header      = col_map.get("lot_number", "LOT番号")
    qty_header      = col_map.get("quantity", "個数")
    process_header  = col_map.get("process", "工程")

    # 顧客列インデックス（設定されている場合のみ）
    customer_idx = -1
    if customer_header:
        try:
            customer_idx = headers.index(customer_header)
        except ValueError:
            pass  # 顧客列が見つからない場合は無視

    try:
        model_idx   = headers.index(model_header)
    except ValueError:
        send_json({"success": False,
                    "error": "ヘッダーに '{}' が見つかりません".format(model_header)})
        return

    try:
        order_idx   = headers.index(order_header)
        lot_idx     = headers.index(lot_header)
        qty_idx     = headers.index(qty_header)
        process_idx = headers.index(process_header)
    except ValueError as e:
        send_json({"success": False, "error": "ヘッダーマッピングエラー: " + str(e)})
        return

    # 顧客一覧取得（model も get_models も指定なし）
    if not model and not get_models:
        if customer_idx >= 0:
            customers = sorted(set(
                row[customer_idx] for row in rows
                if len(row) > customer_idx and row[customer_idx].strip()
            ))
        else:
            customers = []
        write_log(username, "顧客一覧取得", "件数: {}".format(len(customers)))
        send_json({"success": True, "customers": customers})
        return

    # 機種一覧取得（customer フィルターあり or 全機種）
    if not model and get_models:
        if customer and customer_idx >= 0:
            target_rows = [row for row in rows
                           if len(row) > customer_idx and row[customer_idx] == customer]
        else:
            target_rows = rows
        models = sorted(set(
            row[model_idx] for row in target_rows
            if len(row) > model_idx and row[model_idx].strip()
        ))
        write_log(username, "機種一覧取得",
                  "顧客={} 件数: {}".format(customer or "(全て)", len(models)))
        send_json({"success": True, "models": models, "customer": customer})
        return

    filtered = [row for row in rows if len(row) > model_idx and row[model_idx] == model]

    groups = {}
    for row in filtered:
        order   = row[order_idx]   if len(row) > order_idx   else ""
        lot     = row[lot_idx]     if len(row) > lot_idx     else ""
        qty     = row[qty_idx]     if len(row) > qty_idx     else "0"
        process = row[process_idx] if len(row) > process_idx else ""

        if order not in groups:
            groups[order] = []

        groups[order].append({
            "lot_number":   lot,
            "quantity":     qty,
            "process":      process,
            "order_number": order,
        })

    result_groups = []
    for order_num in sorted(groups.keys(), key=lambda x: (x == "", x)):
        lots  = groups[order_num]
        total = 0
        for l in lots:
            try:
                total += int(l["quantity"])
            except (ValueError, TypeError):
                pass
        result_groups.append({
            "order_number":   order_num,
            "total_quantity": total,
            "lots":           lots,
        })

    write_log(username, "データ読み込み",
              "機種={} グループ数={} ロット数={}".format(
                  model, len(result_groups),
                  sum(len(g["lots"]) for g in result_groups)))

    send_json({
        "success": True,
        "model":   model,
        "groups":  result_groups,
        "column_labels": {
            "customer":     customer_header,
            "model":        model_header,
            "order_number": order_header,
            "lot_number":   lot_header,
            "quantity":     qty_header,
            "process":      process_header,
        },
    })

if __name__ == "__main__":
    main()
