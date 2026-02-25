# Copyright (c) 2026, Printechs and contributors
# For license information, please see license.txt

import frappe
from frappe import _

# ---------------------------------------------------------
#  PERMISSION CONFIGURATION
# ---------------------------------------------------------
COST_VIEW_ROLES = ["MAATC - Allocator","Accounts Manager", "Finance Manager", "System Manager", "Stock Manager"]
COST_FIELDS = ["unit_cost"]

def can_view_costs():
    """Check if current user has permission to view cost fields"""
    user_roles = frappe.get_roles(frappe.session.user)
    return any(role in user_roles for role in COST_VIEW_ROLES)


def mask_cost_fields(data):
    """Mask cost fields with asterisks for unauthorized users"""
    masked_data = []
    for row in data:
        masked_row = dict(row)
        for field in COST_FIELDS:
            if field in masked_row:
                masked_row[field] = "*****"
        masked_data.append(masked_row)
    return masked_data


# ---------------------------------------------------------
#  EXECUTE
# ---------------------------------------------------------
def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    
    # Apply field-level masking based on permissions
    if not can_view_costs():
        data = mask_cost_fields(data)
    
    return columns, data


# ---------------------------------------------------------
#  COLUMNS
# ---------------------------------------------------------
def get_columns():
    return [
        {
            "label": _("Material Request No"),
            "fieldname": "material_request_no",
            "fieldtype": "Link",
            "options": "Material Request",
            "width": 140
        },
        {
            "label": _("Source WH"),
            "fieldname": "source_wh",
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 120
        },
        {
            "label": _("Receiving WH"),
            "fieldname": "receiving_wh",
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 120
        },
        {
            "label": _("Creation Date"),
            "fieldname": "creation_date",
            "fieldtype": "Date",
            "width": 100
        },
        {
            "label": _("Created Time"),
            "fieldname": "created_time",
            "fieldtype": "Time",
            "width": 100
        },
        {
            "label": _("Created User"),
            "fieldname": "created_user",
            "fieldtype": "Data",
            "width": 120
        },
        {
            "label": _("ALU"),
            "fieldname": "alu",
            "fieldtype": "Data",
            "width": 100
        },
        {
            "label": _("DESCRIPTION 1"),
            "fieldname": "description_1",
            "fieldtype": "Data",
            "width": 150
        },
        {
            "label": _("DESC2 / SUPPLIER"),
            "fieldname": "desc2_supplier",
            "fieldtype": "Data",
            "width": 120
        },
        {
            "label": _("DESC3/PRODUCT TYPE"),
            "fieldname": "desc3_product_type",
            "fieldtype": "Data",
            "width": 120
        },
        {
            "label": _("DESC4"),
            "fieldname": "desc4",
            "fieldtype": "Data",
            "width": 100
        },
        {
            "label": _("MODEL NO."),
            "fieldname": "model_no",
            "fieldtype": "Data",
            "width": 100
        },
        {
            "label": _("Color Name"),
            "fieldname": "color_name",
            "fieldtype": "Data",
            "width": 100
        },
        {
            "label": _("Year"),
            "fieldname": "year",
            "fieldtype": "Data",
            "width": 80
        },
        {
            "label": _("Season"),
            "fieldname": "season",
            "fieldtype": "Data",
            "width": 80
        },
        {
            "label": _("DCS CODE"),
            "fieldname": "dcs_code",
            "fieldtype": "Data",
            "width": 100
        },
        {
            "label": _("ATTR"),
            "fieldname": "attr",
            "fieldtype": "Data",
            "width": 80
        },
        {
            "label": _("SIZE"),
            "fieldname": "size",
            "fieldtype": "Data",
            "width": 80
        },
        {
            "label": _("UPC"),
            "fieldname": "upc",
            "fieldtype": "Data",
            "width": 120
        },
        {
            "label": _("ITEM NO"),
            "fieldname": "item_no",
            "fieldtype": "Link",
            "options": "Item",
            "width": 120
        },
        {
            "label": _("Order QTY"),
            "fieldname": "order_qty",
            "fieldtype": "Float",
            "width": 100
        },
        {
            "label": _("Transferred QTY"),
            "fieldname": "transferred_qty",
            "fieldtype": "Float",
            "width": 120
        },
        {
            "label": _("Difference"),
            "fieldname": "difference",
            "fieldtype": "Float",
            "width": 100
        },
        {
            "label": _("Per %"),
            "fieldname": "per_percentage",
            "fieldtype": "Percent",
            "width": 80
        },
        {
            "label": _("Unit Cost"),
            "fieldname": "unit_cost",
            "fieldtype": "Currency",
            "width": 100,
            "options": "Company:company:default_currency"
        },
        {
            "label": _("Total Ordered Price"),
            "fieldname": "total_order_price",
            "fieldtype": "Currency",
            "width": 140,
            "options": "Company:company:default_currency"
        },
        {
            "label": _("Total Transferred Price"),
            "fieldname": "total_transferred_price",
            "fieldtype": "Currency",
            "width": 150,
            "options": "Company:company:default_currency"
        },
        {
            "label": _("Status"),
            "fieldname": "status",
            "fieldtype": "Data",
            "width": 120
        },
    ]


# ---------------------------------------------------------
#  DATA
# ---------------------------------------------------------
def get_data(filters):
    conditions = []
    values = {}

    # Date/Time filters
    if filters.get("from_datetime") and filters.get("to_datetime"):
        conditions.append(
            "CONCAT(mr.transaction_date,' ',TIME(mr.creation)) BETWEEN %(from)s AND %(to)s"
        )
        values["from"] = filters.get("from_datetime")
        values["to"] = filters.get("to_datetime")

    # Material Request No filter
    if filters.get("material_request_no"):
        mr_list = parse_filter_value(filters.get("material_request_no"))
        if mr_list:
            conditions.append(f"mr.name IN %(mr_list)s")
            values["mr_list"] = tuple(mr_list)

    # Source Warehouse filter
    if filters.get("source_warehouse"):
        wh_list = parse_filter_value(filters.get("source_warehouse"))
        if wh_list:
            conditions.append(f"mr.set_from_warehouse IN %(source_wh)s")
            values["source_wh"] = tuple(wh_list)

    # Created User filter
    if filters.get("created_user"):
        user_list = parse_filter_value(filters.get("created_user"))
        if user_list:
            conditions.append(f"mr.owner IN %(created_user)s")
            values["created_user"] = tuple(user_list)

    # Items filter
    if filters.get("items"):
        item_list = parse_filter_value(filters.get("items"))
        if item_list:
            conditions.append(f"mr_item.item_code IN %(items)s")
            values["items"] = tuple(item_list)

    # Status filter
    if filters.get("status"):
        status_list = parse_filter_value(filters.get("status"))
        if status_list:
            conditions.append(f"mr.status IN %(status)s")
            values["status"] = tuple(status_list)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    query = f"""
        SELECT
            mr.name AS material_request_no,
            mr.set_from_warehouse AS source_wh,
            mr.set_warehouse AS receiving_wh,
            mr.transaction_date AS creation_date,
            TIME(mr.creation) AS created_time,
            mr.owner AS created_user,
            
            item.custom_model_no AS alu,
            item.item_name AS description_1,
            (SELECT supplier FROM `tabItem Supplier` WHERE parent = item.name LIMIT 1) AS desc2_supplier,
            item.custom_product_type AS desc3_product_type,
            item.custom_year AS desc4,
            item.custom_model_no AS model_no,
            
            (SELECT attribute_value FROM `tabItem Variant Attribute` 
             WHERE parent = item.name AND attribute = 'Color Name' LIMIT 1) AS color_name,
            (SELECT attribute_value FROM `tabItem Variant Attribute` 
             WHERE parent = item.name AND attribute = 'Year' LIMIT 1) AS year,
            (SELECT attribute_value FROM `tabItem Variant Attribute` 
             WHERE parent = item.name AND attribute = 'Season' LIMIT 1) AS season,
            item.custom_dcs AS dcs_code,
            (SELECT attribute_value FROM `tabItem Variant Attribute` 
             WHERE parent = item.name AND attribute = 'Color' LIMIT 1) AS attr,
            (SELECT attribute_value FROM `tabItem Variant Attribute` 
             WHERE parent = item.name AND attribute = 'Size' LIMIT 1) AS size,
            (SELECT barcode FROM `tabItem Barcode` WHERE parent = item.name LIMIT 1) AS upc,
            
            mr_item.item_code AS item_no,
            mr_item.qty AS order_qty,
            mr_item.ordered_qty AS transferred_qty,
            (mr_item.qty - mr_item.ordered_qty) AS difference,
            
            CASE 
                WHEN mr_item.qty > 0 THEN (mr_item.ordered_qty / mr_item.qty * 100)
                ELSE 0 
            END AS per_percentage,
            
            COALESCE(
				(SELECT AVG(valuation_rate) 
				FROM `tabBin` 
				WHERE item_code = mr_item.item_code 
				-- AND warehouse IN (mr.set_from_warehouse, mr.set_warehouse)
				), 0
			) AS unit_cost,
            (mr_item.qty * COALESCE(ip.price_list_rate, 0)) AS total_order_price,
            (mr_item.ordered_qty * COALESCE(ip.price_list_rate, 0)) AS total_transferred_price,
            
            mr.status AS status

        FROM `tabMaterial Request` mr
        INNER JOIN `tabMaterial Request Item` mr_item ON mr_item.parent = mr.name
        LEFT JOIN `tabItem` item ON item.name = mr_item.item_code
        -- LEFT JOIN `tabBin` bin ON bin.item_code = mr_item.item_code 
            -- AND bin.warehouse = mr.set_from_warehouse
        LEFT JOIN `tabItem Price` ip ON ip.item_code = mr_item.item_code
            AND ip.selling = 1
            AND ip.price_list = 'RSP'
            AND ip.valid_from <= mr.transaction_date
            AND (ip.valid_upto IS NULL OR ip.valid_upto >= mr.transaction_date)

        WHERE mr.docstatus < 2
          AND {where_clause}
          
        ORDER BY mr.transaction_date DESC, mr.creation DESC
    """

    return frappe.db.sql(query, values, as_dict=True)


def parse_filter_value(value):
    """Parse filter value that can be comma-separated string or list"""
    if not value:
        return []
    
    if isinstance(value, list):
        return [v.strip() for v in value if v]
    
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    
    return [value]