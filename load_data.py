#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
load_data.py - データ読み込みCGI
GET: ?username=admin                         → 顧客一覧を返す
GET: ?username=admin&customer=田中商事        → 該当顧客の機種一覧を返す
GET: ?username=admin&models=1                → 全機種一覧を返す
GET: ?username=admin&summary=1               → 全顧客の機種別枚数一覧を返す
GET: ?username=admin&summary=1&customer=田中商事
                                              → 該当顧客の機種別枚数一覧を返す
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

def get_report_column_mapping(setting, customer):
    cfg = setting.get("report_import", {})
    customers = cfg.get("customers", {})
    if customer and customer in customers:
        return customers[customer].get("column_mapping", {})
    default_cfg = cfg.get("default")
    if isinstance(default_cfg, dict) and default_cfg.get("column_mapping"):
        return default_cfg["column_mapping"]
    return cfg.get("column_mapping", {})

def get_effective_values(row, order_idx, qty_idx, shipped_order_idx,
                         shipped_qty_idx, input_qty_idx):
    order = row[order_idx] if len(row) > order_idx else ""
    qty = row[qty_idx] if len(row) > qty_idx else "0"
    shipped_qty = ""
    shipped_order = ""

    if shipped_qty_idx >= 0 and len(row) > shipped_qty_idx:
        shipped_qty = row[shipped_qty_idx].strip()
    if shipped_order_idx >= 0 and len(row) > shipped_order_idx:
        shipped_order = row[shipped_order_idx].strip()

    is_shipped = False
    try:
        is_shipped = bool(shipped_qty and int(shipped_qty) > 0)
    except (ValueError, TypeError):
        pass

    if is_shipped:
        return (
            shipped_order if shipped_order else order,
            shipped_qty,
            True,
            shipped_qty,
            shipped_order,
        )

    effective_qty = qty
    if input_qty_idx >= 0 and len(row) > input_qty_idx:
        input_qty = row[input_qty_idx].strip()
        try:
            if int(input_qty) > 0:
                effective_qty = input_qty
        except (ValueError, TypeError):
            pass

    return order, effective_qty, False, shipped_qty, shipped_order

def load_required_quantities(setting):
    required_map = {}
    req_file_cfg = setting.get("required_quantity_file", {})
    req_csv_path = req_file_cfg.get("csv_file_path", "")
    req_col = req_file_cfg.get("column_mapping", {})
    req_model_header = req_col.get("model", "")
    req_order_header = req_col.get("order_number", "")
    req_qty_header = req_col.get("required_quantity", "")

    if not req_csv_path or not req_model_header or not req_order_header or not req_qty_header:
        return required_map

    if not os.path.isabs(req_csv_path):
        req_csv_path = os.path.join(SCRIPT_DIR, req_csv_path)
    if not os.path.exists(req_csv_path):
        return required_map

    req_enc = normalize_encoding(req_file_cfg.get("read_encoding", "utf-8"))
    try:
        with open(req_csv_path, mode="r", encoding=req_enc, newline="") as rf:
            req_reader = csv.reader(rf)
            req_headers = next(req_reader, [])
            model_idx = req_headers.index(req_model_header)
            order_idx = req_headers.index(req_order_header)
            qty_idx = req_headers.index(req_qty_header)

            for row in req_reader:
                if len(row) <= max(model_idx, order_idx, qty_idx):
                    continue
                try:
                    required_map[(row[model_idx], row[order_idx])] = int(row[qty_idx])
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass

    return required_map

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
    get_summary = parsed.get("summary", [""])[0]

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

    customer_header        = col_map.get("customer", "")
    model_header           = col_map.get("model", "機種")
    order_header           = col_map.get("order_number", "注文番号")
    lot_header             = col_map.get("lot_number", "LOT番号")
    qty_header             = col_map.get("quantity", "個数")
    process_header         = col_map.get("process", "工程")
    shipped_order_header   = col_map.get("shipped_order_number", "")
    shipped_qty_header     = col_map.get("shipped_quantity", "")
    input_qty_header       = col_map.get("input_quantity", "")

    # 顧客列インデックス（設定されている場合のみ）
    customer_idx = -1
    if customer_header:
        try:
            customer_idx = headers.index(customer_header)
        except ValueError:
            pass

    # 出荷時列インデックス（設定されている場合のみ）
    shipped_order_idx = -1
    shipped_qty_idx = -1
    input_qty_idx = -1
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
    if input_qty_header:
        try:
            input_qty_idx = headers.index(input_qty_header)
        except ValueError:
            pass

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

    # 顧客一覧取得（model も get_models も summary も指定なし）
    if not model and not get_models and not get_summary:
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

    required_map = load_required_quantities(setting)

    # 機種別枚数一覧取得
    if get_summary:
        if customer and customer_idx < 0:
            send_json({"success": False, "error": "顧客列が設定されていません"})
            return

        target_rows = rows
        if customer:
            target_rows = [
                row for row in rows
                if len(row) > customer_idx and row[customer_idx] == customer
            ]

        summary_map = {}
        model_orders = {}
        for row in target_rows:
            if len(row) <= model_idx or not row[model_idx].strip():
                continue

            row_model = row[model_idx]
            effective_order, effective_qty, _, _, _ = get_effective_values(
                row, order_idx, qty_idx, shipped_order_idx,
                shipped_qty_idx, input_qty_idx
            )
            if row_model not in summary_map:
                summary_map[row_model] = 0
                model_orders[row_model] = set()
            try:
                summary_map[row_model] += int(effective_qty)
            except (ValueError, TypeError):
                pass
            if effective_order:
                model_orders[row_model].add(effective_order)

        if not customer:
            for req_model, _ in required_map.keys():
                if req_model not in summary_map:
                    summary_map[req_model] = 0
                    model_orders[req_model] = set()

        summary_rows = []
        for row_model in sorted(summary_map.keys()):
            if customer:
                required = sum(
                    required_map.get((row_model, order), 0)
                    for order in model_orders.get(row_model, set())
                )
            else:
                required = sum(
                    qty for (req_model, _), qty in required_map.items()
                    if req_model == row_model
                )
            current = summary_map[row_model]
            summary_rows.append({
                "model": row_model,
                "required_quantity": required,
                "current_quantity": current,
                "difference": current - required,
            })

        write_log(username, "機種別枚数一覧取得",
                  "顧客={} 件数: {}".format(customer or "(全て)", len(summary_rows)))
        send_json({
            "success": True,
            "customer": customer,
            "summary": summary_rows,
            "column_labels": {
                "customer": customer_header or "顧客",
                "model": model_header or "機種",
                "required_quantity": (
                    setting.get("required_quantity_file", {})
                    .get("column_mapping", {})
                    .get("required_quantity", "必要枚数")
                ),
                "current_quantity": "現状枚数",
            },
        })
        return

    filtered = [row for row in rows if len(row) > model_idx and row[model_idx] == model]

    groups = {}
    for row in filtered:
        order   = row[order_idx]   if len(row) > order_idx   else ""
        lot     = row[lot_idx]     if len(row) > lot_idx     else ""
        qty     = row[qty_idx]     if len(row) > qty_idx     else "0"
        process = row[process_idx] if len(row) > process_idx else ""

        effective_order, effective_qty, is_shipped, shipped_qty_val, shipped_order_val = (
            get_effective_values(
                row, order_idx, qty_idx, shipped_order_idx,
                shipped_qty_idx, input_qty_idx
            )
        )

        if effective_order not in groups:
            groups[effective_order] = []

        groups[effective_order].append({
            "lot_number":       lot,
            "quantity":         effective_qty,
            "original_quantity": qty,
            "process":          process,
            "order_number":     effective_order,
            "original_order":   order,
            "shipped":          is_shipped,
            "shipped_quantity":  shipped_qty_val,
            "shipped_order":    shipped_order_val,
        })

    req_file_cfg = setting.get("required_quantity_file", {})

    result_groups = []
    for order_num in sorted(groups.keys(), key=lambda x: (x == "", x)):
        lots  = groups[order_num]
        total = 0
        for l in lots:
            try:
                total += int(l["quantity"])
            except (ValueError, TypeError):
                pass
        group_data = {
            "order_number":     order_num,
            "total_quantity":   total,
            "lots":             lots,
        }
        if (model, order_num) in required_map:
            group_data["required_quantity"] = required_map[(model, order_num)]
        result_groups.append(group_data)

    write_log(username, "データ読み込み",
              "機種={} グループ数={} ロット数={}".format(
                  model, len(result_groups),
                  sum(len(g["lots"]) for g in result_groups)))

    req_qty_label = ""
    if req_file_cfg:
        req_qty_label = req_file_cfg.get("column_mapping", {}).get("required_quantity", "")

    # レポート取込設定（顧客別。未設定顧客は default、旧形式はそのまま参照）
    report_import_col = get_report_column_mapping(setting, customer)

    resp = {
        "success": True,
        "model":   model,
        "groups":  result_groups,
        "column_labels": {
            "customer":             customer_header,
            "model":                model_header,
            "order_number":         order_header,
            "lot_number":           lot_header,
            "quantity":             qty_header,
            "process":              process_header,
            "shipped_order_number": shipped_order_header,
            "shipped_quantity":     shipped_qty_header,
            "required_quantity":    req_qty_label,
        },
    }

    # admin ユーザーの場合のみレポート取込設定を返す
    if matched_user.get("username") == "admin" and report_import_col:
        resp["report_import"] = {
            "lot_number_header":   report_import_col.get("lot_number", ""),
            "order_number_header": report_import_col.get("order_number", ""),
        }

    send_json(resp)

if __name__ == "__main__":
    main()
