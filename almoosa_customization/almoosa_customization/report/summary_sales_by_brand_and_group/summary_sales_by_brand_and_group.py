# Copyright (c) 2026, Printechs and contributors
# For license information, please see license.txt

import frappe
from collections import defaultdict

def execute(filters=None):

	filters = filters or {}
	conditions = "hd.docstatus = 1"
	values = {}

	if filters.get("from_datetime") and filters.get("to_datetime"):
		conditions += """
        AND TIMESTAMP(hd.posting_date, hd.posting_time)
        BETWEEN %(from_datetime)s AND %(to_datetime)s
    	"""
		values["from_datetime"] = filters.get("from_datetime")
		values["to_datetime"] = filters.get("to_datetime")
    
	if filters.get("warehouse"):
		conditions += " AND it.warehouse IN %(warehouse)s"
		values["warehouse"] = tuple(filters.get("warehouse"))

	if filters.get("brand"):
		conditions += " AND it.brand IN %(brand)s"
		values["brand"] = tuple(filters.get("brand"))

	data = frappe.db.sql(f"""
    SELECT
        LEFT(it.warehouse,3) warehouse,
        SUBSTRING_INDEX(it.item_group, '.', -1) AS item_group,
        it.brand,
        SUM(it.qty) AS qty
    FROM `tabPOS Invoice Item` it
    INNER JOIN `tabPOS Invoice` hd
        ON hd.name = it.parent
    WHERE {conditions}
    GROUP BY
        it.warehouse,
        item_group,
        it.brand
    ORDER BY
        it.warehouse, item_group
""", values, as_dict=True)

    # -------------------------
    # Collect Dynamic Brands
    # -------------------------

	#frappe.msgprint(str(values))
	brands = sorted(list({d.brand for d in data if d.brand}))

	columns = [
        {"label": "WH", "fieldname": "warehouse", "fieldtype": "Data", "width": 60},
        {"label": "Group", "fieldname": "item_group", "fieldtype": "Data", "width": 100},
    ]

	for brand in brands:
		columns.append({
            "label": brand,
            "fieldname": frappe.scrub(brand),
            "fieldtype": "Int",
            "width": 70
        })

	columns.append({
        "label": "Total",
        "fieldname": "total",
        "fieldtype": "Int",
        "width": 100
    })

    # -------------------------
    # Organize Data
    # -------------------------
	warehouse_data = defaultdict(lambda: defaultdict(dict))
	warehouse_totals = defaultdict(lambda: defaultdict(float))
	grand_totals = defaultdict(float)

	for row in data:
		warehouse = row.warehouse
		group = row.item_group
		brand = row.brand
		qty = row.qty or 0

		warehouse_data[warehouse][group][brand] = qty
		warehouse_totals[warehouse][brand] += qty
		grand_totals[brand] += qty
		warehouse_totals[warehouse]["total"] += qty
		grand_totals["total"] += qty

    # -------------------------
    # Build Final Rows
    # -------------------------
	result = []

	for warehouse in sorted(warehouse_data.keys()):
		first_row = True

		for group in sorted(warehouse_data[warehouse].keys()):
			row = {
                "warehouse": warehouse if first_row else "",
                "item_group": group
            }

			total = 0
			for brand in brands:
				qty = warehouse_data[warehouse][group].get(brand, 0)
				row[frappe.scrub(brand)] = qty
				total += qty

			row["total"] = total
			result.append(row)
			first_row = False

        # Warehouse Total Row
		total_row = {
            "warehouse": "",
            "item_group": "Warehouse Total"
        }

		for brand in brands:
			total_row[frappe.scrub(brand)] = warehouse_totals[warehouse][brand]

		total_row["total"] = warehouse_totals[warehouse]["total"]
		result.append(total_row)

    # Grand Total Row
	grand_row = {
        "warehouse": "",
        "item_group": "Grand Total"
    }

	for brand in brands:
		grand_row[frappe.scrub(brand)] = grand_totals[brand]

	grand_row["total"] = grand_totals["total"]
	result.append(grand_row)

	return columns, result
