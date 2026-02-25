# Copyright (c) 2026, Printechs and contributors
# For license information, please see license.txt

import frappe

# ---------------------------------------------------------
#  EXECUTE
# ---------------------------------------------------------
def execute(filters=None):
    return get_columns(), get_data(filters)


# ---------------------------------------------------------
#  COLUMNS
# ---------------------------------------------------------
def get_columns():
    return [
        {"label": "Date", "fieldname": "posting_date", "fieldtype": "Date"},
        {"label": "Time", "fieldname": "posting_time", "fieldtype": "Time"},
        {"label": "Doc No", "fieldname": "doc_no", "fieldtype": "Data"},
        {"label": "PO No", "fieldname": "po_no", "fieldtype": "Data"},
        {"label": "Created By", "fieldname": "owner", "fieldtype": "Data"},
        {"label": "Received Warehouse", "fieldname": "to_warehouse", "fieldtype": "Data"},

        {"label": "Vendor Code", "fieldname": "vendor_code", "fieldtype": "Data"},
        {"label": "Vendor Name", "fieldname": "vendor_name", "fieldtype": "Data"},

        {"label": "Main", "fieldname": "group_level_1", "fieldtype": "Data"},
        {"label": "Gender", "fieldname": "group_level_2", "fieldtype": "Data"},
        {"label": "Category", "fieldname": "group_level_3", "fieldtype": "Data"},
        {"label": "Group", "fieldname": "group_level_4", "fieldtype": "Data"},
        {"label": "Sub Group", "fieldname": "group_level_5", "fieldtype": "Data"},

        {"label": "Item No", "fieldname": "item_code", "fieldtype": "Data"},
        {"label": "Alu", "fieldname": "model_no", "fieldtype": "Data"},
        {"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data"},
        {"label": "Supplier", "fieldname": "vendor", "fieldtype": "Data"},
        {"label": "Product Type", "fieldname": "product_type", "fieldtype": "Data"},
        {"label": "Model No", "fieldname": "model_no", "fieldtype": "Data"},
        {"label": "Color Name", "fieldname": "color_name", "fieldtype": "Data"},
        {"label": "Year", "fieldname": "year", "fieldtype": "Data"},
        {"label": "Season", "fieldname": "season", "fieldtype": "Data"},
        {"label": "Dcs Code", "fieldname": "dcs_code", "fieldtype": "Data"},
        {"label": "Size", "fieldname": "size", "fieldtype": "Data"},
        {"label": "Upc", "fieldname": "barcode", "fieldtype": "Data"},

        {"label": "Qty", "fieldname": "qty", "fieldtype": "Float"},
        {"label": "Unit Cost", "fieldname": "unit_cost", "fieldtype": "Currency"},
        {"label": "Discount", "fieldname": "disc", "fieldtype": "Currency"},
        {"label": "Total Cost", "fieldname": "total_cost", "fieldtype": "Currency"},
        {"label": "Unit Price Without Tax", "fieldname": "unit_price_wo_tax", "fieldtype": "Currency"},
        {"label": "Unit Tax", "fieldname": "unit_tax", "fieldtype": "Currency"},
        {"label": "Unit Price", "fieldname": "unit_price_with_tax", "fieldtype": "Currency"},
        {"label": "Total Price", "fieldname": "total_price", "fieldtype": "Currency"},
        {"label": "Onhand Qty", "fieldname": "oh_whs", "fieldtype": "Float"},
    ]


# ---------------------------------------------------------
#  DATA
# ---------------------------------------------------------
def get_data(filters):
    conditions = []
    values = {}

    if filters.get("from_datetime") and filters.get("to_datetime"):
        conditions.append(
            "CONCAT(pr.posting_date,' ',pr.posting_time) BETWEEN %(from)s AND %(to)s"
        )
        values["from"] = filters.get("from_datetime")
        values["to"] = filters.get("to_datetime")

    def multi_filter(field, sql_field):
        val = filters.get(field)
        if val:
            if isinstance(val, str):
                val = [d.strip() for d in val.split(",")]
            conditions.append(f"{sql_field} IN %({field})s")
            values[field] = tuple(val)

    multi_filter("vendor_code", "b.custom_brand_code")
    multi_filter("supplier", "pr.supplier")
    multi_filter("item_code", "pri.item_code")
    multi_filter("warehouse", "pri.warehouse")

    # Item Group filter — SAME LOGIC
    if filters.get("item_group_filter"):
        ig_val = filters.get("item_group_filter")

        if isinstance(ig_val, list):
            or_parts = []
            for i, g in enumerate(ig_val):
                key = f"grp_{i}"
                or_parts.append(f"ig.name LIKE %({key})s")
                values[key] = g + "%"
            conditions.append("(" + " OR ".join(or_parts) + ")")

        elif isinstance(ig_val, str):
            conditions.append("ig.name LIKE %(item_group_filter)s")
            values["item_group_filter"] = ig_val + "%"

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    query = f"""
        SELECT
            pr.posting_date,
            pr.posting_time,
            pr.name AS doc_no,
            pri.purchase_order AS po_no,
            pr.owner,

            pri.warehouse AS to_warehouse,

            b.custom_brand_code AS vendor_code,
            sup.supplier_name AS vendor_name,
            pr.supplier AS vendor,

            SUBSTRING_INDEX(ig.name,'.',1) AS group_level_1,
            SUBSTRING_INDEX(SUBSTRING_INDEX(ig.name,'.',2),'.',-1) AS group_level_2,
            SUBSTRING_INDEX(SUBSTRING_INDEX(ig.name,'.',3),'.',-1) AS group_level_3,
            SUBSTRING_INDEX(SUBSTRING_INDEX(ig.name,'.',4),'.',-1) AS group_level_4,
            SUBSTRING_INDEX(ig.name,'.',-1) AS group_level_5,

            pri.item_code,
            it.item_name,
            it.custom_model_no AS model_no,
            it.custom_product_type AS product_type,
            it.custom_dcs AS dcs_code,

            ia_color.attribute_value AS color_name,
            ia_year.attribute_value AS year,
            ia_season.attribute_value AS season,
            ia_size.attribute_value AS size,

            ib.barcode,
            pri.qty,

            pri.rate AS unit_cost,
            (pri.discount_amount + pri.distributed_discount_amount) AS disc,
            (pri.qty * pri.rate) - (pri.discount_amount + pri.distributed_discount_amount) AS total_cost,

            pri.rate AS unit_price_with_tax,
            (pri.rate / 1.15) AS unit_price_wo_tax,
            (pri.rate - (pri.rate / 1.15)) AS unit_tax,
            (pri.rate * pri.qty) AS total_price,

            bin.actual_qty AS oh_whs

        FROM `tabPurchase Receipt` pr
        JOIN `tabPurchase Receipt Item` pri ON pri.parent = pr.name

        LEFT JOIN `tabItem` it ON it.name = pri.item_code
        LEFT JOIN `tabItem Group` ig ON ig.name = it.item_group
        LEFT JOIN `tabBrand` b ON b.name = it.brand
        LEFT JOIN `tabSupplier` sup ON sup.name = pr.supplier
        LEFT JOIN `tabItem Barcode` ib ON ib.parent = it.name

        LEFT JOIN `tabItem Variant Attribute` ia_color
            ON ia_color.parent = it.name AND ia_color.attribute='Color Name'
        LEFT JOIN `tabItem Variant Attribute` ia_year
            ON ia_year.parent = it.name AND ia_year.attribute='Year'
        LEFT JOIN `tabItem Variant Attribute` ia_season
            ON ia_season.parent = it.name AND ia_season.attribute='Season'
        LEFT JOIN `tabItem Variant Attribute` ia_size
            ON ia_size.parent = it.name AND ia_size.attribute='Size'

        LEFT JOIN `tabBin` bin
            ON bin.item_code = pri.item_code AND bin.warehouse = pri.warehouse

        WHERE pr.docstatus = 1
          AND {where_clause}
    """

    return frappe.db.sql(query, values, as_dict=True)

