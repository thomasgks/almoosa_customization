import frappe
from collections import defaultdict

def execute(filters=None):
    columns = []
    data = []

    conditions = ""
    values = {}

    # -----------------------
    # Date & Time Filter
    # -----------------------
    if filters.get("from_datetime") and filters.get("to_datetime"):
        conditions += """
            AND TIMESTAMP(hd.posting_date, hd.posting_time)
            BETWEEN %(from_datetime)s AND %(to_datetime)s
        """
        values["from_datetime"] = filters.get("from_datetime")
        values["to_datetime"] = filters.get("to_datetime")

    # -----------------------
    # Item Group Filter
    # -----------------------
    if filters.get("item_group"):
        conditions += """
            AND SUBSTRING_INDEX(it.item_group, '.', -1) IN %(item_group)s
        """
        values["item_group"] = tuple(filters.get("item_group"))

    # -----------------------
    # Warehouse Filter
    # -----------------------
    if filters.get("warehouse"):
        conditions += " AND it.warehouse IN %(warehouse)s"
        values["warehouse"] = tuple(filters.get("warehouse"))

    # -----------------------
    # Fetch Data
    # -----------------------
    records = frappe.db.sql(f"""
        SELECT 
            SUBSTRING_INDEX(it.item_group, '.', -1) AS item_group,
            LEFT(it.warehouse,3) warehouse,
            SUM(it.qty) AS qty
        FROM `tabPOS Invoice Item` it
        INNER JOIN `tabPOS Invoice` hd 
            ON hd.name = it.parent
        WHERE hd.docstatus = 1 {conditions}
        GROUP BY it.item_group, it.warehouse
        ORDER BY item_group
    """, values, as_dict=True)

    # -----------------------
    # Prepare Pivot Structure
    # -----------------------
    item_group_data = defaultdict(lambda: defaultdict(float))
    warehouses = set()

    for row in records:
        item_group = row["item_group"]
        warehouse = row["warehouse"]
        qty = row["qty"] or 0

        item_group_data[item_group][warehouse] += qty
        warehouses.add(warehouse)

    warehouses = sorted(warehouses)

    # -----------------------
    # Columns
    # -----------------------
    columns.append({
        "label": "Item Group",
        "fieldname": "item_group",
        "fieldtype": "Data",
        "width": 130
    })

    for wh in warehouses:
        columns.append({
            "label": wh,
            "fieldname": wh,
            "fieldtype": "Int",
            "width": 60
        })

    columns.append({
        "label": "Total",
        "fieldname": "total",
        "fieldtype": "Int",
        "width": 100
    })

    # -----------------------
    # Data Rows
    # -----------------------
    grand_totals = defaultdict(float)

    for item_group in sorted(item_group_data.keys()):
        row = {"item_group": item_group}
        total = 0

        for wh in warehouses:
            qty = item_group_data[item_group].get(wh, 0)
            row[wh] = qty
            total += qty
            grand_totals[wh] += qty

        row["total"] = total
        data.append(row)

    # -----------------------
    # Grand Total Row
    # -----------------------
    if data:
        grand_row = {"item_group": "Grand Total"}
        grand_total_sum = 0

        for wh in warehouses:
            grand_row[wh] = grand_totals[wh]
            grand_total_sum += grand_totals[wh]

        grand_row["total"] = grand_total_sum
        data.append(grand_row)

    return columns, data
