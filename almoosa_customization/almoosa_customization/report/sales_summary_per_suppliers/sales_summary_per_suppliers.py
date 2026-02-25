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
            AND SUBSTRING_INDEX(SUBSTRING_INDEX(it.item_group, '.', 3), '.', -1) IN %(item_group)s
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
    MAX(sup.supplier) AS supplier,
    LEFT(it.warehouse,3) warehouse ,        
    SUM(it.qty) AS qty
FROM `tabPOS Invoice Item` AS it
INNER JOIN `tabPOS Invoice` hd 
    ON hd.name = it.parent
INNER JOIN `ViewSupplierItem` AS sup 
    ON sup.item_code = it.item_code
WHERE hd.docstatus = 1 {conditions}
GROUP BY sup.supplier,it.warehouse
ORDER BY sup.supplier;
    """, values, as_dict=True)

    # -----------------------
    # Prepare Pivot Structure
    # -----------------------
    supplier_data = defaultdict(lambda: defaultdict(float))
    warehouses = set()

    for row in records:
        supplier = row["supplier"]
        warehouse = row["warehouse"]
        qty = row["qty"] or 0

        supplier_data[supplier][warehouse] += qty
        warehouses.add(warehouse)

    warehouses = sorted(warehouses)

    # -----------------------
    # Columns
    # -----------------------
    columns.append({
        "label": "Supplier",
        "fieldname": "supplier",
        "fieldtype": "Data",
        "width": 90
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

    for supplier in sorted(supplier_data.keys()):
        row = {"supplier": supplier}
        total = 0

        for wh in warehouses:
            qty = supplier_data[supplier].get(wh, 0)
            row[wh] = qty
            total += qty
            grand_totals[wh] += qty

        row["total"] = total
        data.append(row)

    # -----------------------
    # Grand Total Row
    # -----------------------
    if data:
        grand_row = {"supplier": "Grand Total"}
        grand_total_sum = 0

        for wh in warehouses:
            grand_row[wh] = grand_totals[wh]
            grand_total_sum += grand_totals[wh]

        grand_row["total"] = grand_total_sum
        data.append(grand_row)

    return columns, data
