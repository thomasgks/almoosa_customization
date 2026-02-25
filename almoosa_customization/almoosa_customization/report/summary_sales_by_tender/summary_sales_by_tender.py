import frappe
from collections import defaultdict

def execute(filters=None):
    filters = filters or {}

    columns = []
    data = []

    conditions = []
    values = {}

    # Datetime filter
    if filters.get("from_datetime") and filters.get("to_datetime"):
        conditions.append("""
             (TIMESTAMP(hd.posting_date, hd.posting_time)
            BETWEEN %(from_datetime)s AND %(to_datetime)s)
        """)
        values["from_datetime"] = filters.get("from_datetime")
        values["to_datetime"] = filters.get("to_datetime")


    # Optional warehouse filter
    if filters.get("warehouse"):
        conditions.append(" hd.set_warehouse IN %(warehouse)s")
        values["warehouse"] = tuple(filters.get("warehouse"))

    where_clause = ""
    if conditions:
        where_clause = " AND " + " AND ".join(conditions)
    # Fetch payment data
    records = frappe.db.sql(f"""
        SELECT 
            hd.set_warehouse,
            pay.mode_of_payment,
            SUM(pay.amount) as amount
        FROM `tabSales Invoice Payment` pay
        INNER JOIN `tabPOS Invoice` hd 
            ON hd.name = pay.parent
        WHERE hd.docstatus = 1 {where_clause}
        GROUP BY hd.set_warehouse, pay.mode_of_payment
    """, values, as_dict=True) or []

    #frappe.msgprint(str(values))
    warehouse_data = defaultdict(lambda: defaultdict(float))
    payment_modes = set()

    for row in records:
        warehouse = row.get("set_warehouse")
        mode = row.get("mode_of_payment")
        amount = row.get("amount") or 0

        warehouse_data[warehouse][mode] = amount
        payment_modes.add(mode)

    payment_modes = sorted(payment_modes)

    # --------------------
    # Columns
    # --------------------
    columns.append({
        "label": "Warehouse",
        "fieldname": "warehouse",
        "fieldtype": "Data",
        "width": 180
    })

    for mode in payment_modes:
        columns.append({
            "label": mode,
            "fieldname": mode,
            "fieldtype": "Currency",
            "width": 120
        })

    columns.append({
        "label": "Total",
        "fieldname": "total",
        "fieldtype": "Currency",
        "width": 130
    })

    # --------------------
    # Data Rows
    # --------------------
    grand_totals = defaultdict(float)

    for warehouse in sorted(warehouse_data.keys()):
        row = {"warehouse": warehouse}
        total = 0

        for mode in payment_modes:
            amount = warehouse_data[warehouse].get(mode, 0)
            row[mode] = amount
            total += amount
            grand_totals[mode] += amount

        row["total"] = total
        data.append(row)

    # --------------------
    # Grand Total Row
    # --------------------
    columns.append({
    "fieldname": "is_grand_total",
    "label": "Hidden",
    "fieldtype": "Int",
    "hidden": 1
        })
    if data:
        grand_row = {
            "warehouse": "Grand Total",
        "is_grand_total": 1
        }
        grand_total_sum = 0

        for mode in payment_modes:
            grand_row[mode] = grand_totals[mode]
            grand_total_sum += grand_totals[mode]
            row = {
                "warehouse": warehouse,
             "is_grand_total": 0
                }

        grand_row["total"] = grand_total_sum
        data.append(grand_row)

    return columns, data
