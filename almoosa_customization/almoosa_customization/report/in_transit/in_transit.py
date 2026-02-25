# Copyright (c) 2026, Printechs and contributors
# For license information, please see license.txt

import frappe

# ---------------------------------------------------------
#  PERMISSION CONFIGURATION
# ---------------------------------------------------------
# Define which roles can see cost fields
COST_VIEW_ROLES = ["MAATC - Allocator","Accounts Manager", "Finance Manager", "System Manager", "Stock Manager"]
COST_FIELDS = ["unit_cost", "total_cost"]

def can_view_costs():
    """Check if current user has permission to view cost fields"""
    user_roles = frappe.get_roles(frappe.session.user)
    return any(role in user_roles for role in COST_VIEW_ROLES)


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
#  COLUMNS (UNCHANGED)
# ---------------------------------------------------------
def get_columns():
    return [
        {"label": "Date", "fieldname": "posting_date", "fieldtype": "Date"},
        {"label": "Time", "fieldname": "posting_time", "fieldtype": "Time"},
        {"label": "Doc No", "fieldname": "doc_no", "fieldtype": "Data"},
        {"label": "Created By", "fieldname": "owner", "fieldtype": "Data"},
        {"label": "To Store", "fieldname": "to_warehouse", "fieldtype": "Data"},
        {"label": "From Store", "fieldname": "from_warehouse", "fieldtype": "Data"},
        
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
        {"label": "Total Cost", "fieldname": "total_cost", "fieldtype": "Currency"},
        {"label": "Unit Price Without Tax", "fieldname": "unit_price_wo_tax", "fieldtype": "Currency"},
        {"label": "Unit Tax", "fieldname": "unit_tax", "fieldtype": "Currency"},
        {"label": "Unit Price", "fieldname": "unit_price_with_tax", "fieldtype": "Currency"},
        {"label": "Total Price", "fieldname": "total_price", "fieldtype": "Currency"},
        {"label": "Onhand Source WHS", "fieldname": "oh_source", "fieldtype": "Float"},
        {"label": "Onhand Target WHS", "fieldname": "oh_target", "fieldtype": "Float"},
    ]


# ---------------------------------------------------------
#  MASKING FUNCTION
# ---------------------------------------------------------
def mask_cost_fields(data):
    """Mask cost fields with asterisks for unauthorized users"""
    masked_data = []
    for row in data:
        masked_row = dict(row)  # Create copy to avoid mutating original
        for field in COST_FIELDS:
            if field in masked_row:
                masked_row[field] = "*****"
        masked_data.append(masked_row)
    return masked_data


# ---------------------------------------------------------
#  DATA
# ---------------------------------------------------------
def get_data(filters):
    conditions = []
    values = {}

    # Handle datetime filtering with optional from/to dates
    from_datetime = filters.get("from_datetime")
    to_datetime = filters.get("to_datetime")

    # Default to_date to current datetime if not provided
    if not to_datetime:
        to_datetime = frappe.utils.now()
    
    # Build the datetime condition based on what we have
    if from_datetime and to_datetime:
        conditions.append(
            "CONCAT(se.posting_date,' ',se.posting_time) BETWEEN %(from)s AND %(to)s"
        )
        values["from"] = from_datetime
        values["to"] = to_datetime
    elif to_datetime:
        conditions.append(
            "CONCAT(se.posting_date,' ',se.posting_time) <= %(to)s"
        )
        values["to"] = to_datetime
    elif from_datetime:
        conditions.append(
            "CONCAT(se.posting_date,' ',se.posting_time) >= %(from)s"
        )
        values["from"] = from_datetime

    def multi_filter(field, sql_field):
        val = filters.get(field)
        if val:
            if isinstance(val, str):
                val = [d.strip() for d in val.split(",")]
            conditions.append(f"{sql_field} IN %({field})s")
            values[field] = tuple(val)

    multi_filter("vendor_code", "b.custom_brand_code")
    multi_filter("supplier", "si.supplier")
    multi_filter("item_code", "sed.item_code")
    multi_filter("source_warehouse", "se.from_warehouse")

    # Item Group filter
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

    if filters.get("receiving_warehouse"):
        conditions.append("se.custom_receiving_warehouse = %(rw)s")
        values["rw"] = filters.get("receiving_warehouse")

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # Main query - NO HAVING clause, filter in Python instead
    query = f"""
        SELECT
            se.posting_date,
            se.posting_time,
            se.name AS doc_no,
            se.owner,
            se.from_warehouse AS from_warehouse,
            se.custom_receiving_warehouse AS to_warehouse,
            b.custom_brand_code AS vendor_code,
            sup.supplier_name AS vendor_name,
            si.supplier AS vendor,
            SUBSTRING_INDEX(ig.name,'.',1) AS group_level_1,
            SUBSTRING_INDEX(SUBSTRING_INDEX(ig.name,'.',2),'.',-1) AS group_level_2,
            SUBSTRING_INDEX(SUBSTRING_INDEX(ig.name,'.',3),'.',-1) AS group_level_3,
            SUBSTRING_INDEX(SUBSTRING_INDEX(ig.name,'.',4),'.',-1) AS group_level_4,
            SUBSTRING_INDEX(ig.name,'.',-1) AS group_level_5,
            sed.item_code,
            it.item_name,
            it.custom_model_no AS model_no,
            it.custom_product_type AS product_type,
            it.custom_dcs AS dcs_code,
            ia_color.attribute_value AS color_name,
            ia_year.attribute_value AS year,
            ia_season.attribute_value AS season,
            ia_size.attribute_value AS size,
            ib.barcode,
            
            /* Calculate remaining qty by subtracting received qty from end transit entries */
            (sed.qty - COALESCE(received_qty.total_received, 0)) AS qty,
            
            bin_src.valuation_rate AS unit_cost,
            ((sed.qty - COALESCE(received_qty.total_received, 0)) * bin_src.valuation_rate) AS total_cost,
            ip.price_list_rate AS unit_price_with_tax,
            (ip.price_list_rate / 1.15) AS unit_price_wo_tax,
            (ip.price_list_rate - (ip.price_list_rate / 1.15)) AS unit_tax,
            (ip.price_list_rate * (sed.qty - COALESCE(received_qty.total_received, 0))) AS total_price,
            bin_src.actual_qty AS oh_source,
            bin_tgt.actual_qty AS oh_target,
            
            /* Show original qty for reference */
            sed.qty AS original_transit_qty,
            COALESCE(received_qty.total_received, 0) AS received_qty,
            COALESCE(received_qty.end_transit_count, 0) AS end_transit_entries

        FROM `tabStock Entry` se
        JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
        
        /* Subquery to calculate total received qty from end transit entries */
        /* End Transit entries: outgoing_stock_entry IS NOT NULL (references original entry) */
        LEFT JOIN (
            SELECT 
                se2.outgoing_stock_entry AS original_entry,
                sed2.item_code,
                SUM(sed2.qty) AS total_received,
                COUNT(DISTINCT se2.name) AS end_transit_count
            FROM `tabStock Entry Detail` sed2
            JOIN `tabStock Entry` se2 ON se2.name = sed2.parent
            WHERE se2.docstatus = 1
              AND se2.stock_entry_type = 'Material Transfer'
              AND se2.outgoing_stock_entry IS NOT NULL
            GROUP BY se2.outgoing_stock_entry, sed2.item_code
        ) received_qty 
            ON received_qty.original_entry = se.name 
            AND received_qty.item_code = sed.item_code

        LEFT JOIN `tabItem` it ON it.name = sed.item_code
        LEFT JOIN `tabItem Group` ig ON ig.name = it.item_group
        LEFT JOIN `tabBrand` b ON b.name = it.brand
        LEFT JOIN `tabItem Supplier` si ON si.parent = it.name
        LEFT JOIN `tabSupplier` sup ON sup.name = si.supplier
        LEFT JOIN `tabItem Barcode` ib ON ib.parent = it.name

        LEFT JOIN `tabItem Price` ip
            ON ip.item_code = sed.item_code
           AND ip.selling = 1
           AND ip.price_list = 'RSP'
           AND ip.valid_from <= se.posting_date
           AND (ip.valid_upto IS NULL OR ip.valid_upto >= se.posting_date)

        LEFT JOIN `tabItem Variant Attribute` ia_color
            ON ia_color.parent = it.name AND ia_color.attribute='Color Name'
        LEFT JOIN `tabItem Variant Attribute` ia_year
            ON ia_year.parent = it.name AND ia_year.attribute='Year'
        LEFT JOIN `tabItem Variant Attribute` ia_season
            ON ia_season.parent = it.name AND ia_season.attribute='Season'
        LEFT JOIN `tabItem Variant Attribute` ia_size
            ON ia_size.parent = it.name AND ia_size.attribute='Size'

        LEFT JOIN `tabBin` bin_src
            ON bin_src.item_code = sed.item_code AND bin_src.warehouse = se.from_warehouse
        LEFT JOIN `tabBin` bin_tgt
            ON bin_tgt.item_code = sed.item_code AND bin_tgt.warehouse = se.custom_receiving_warehouse

        WHERE se.docstatus = 1
          AND se.stock_entry_type = 'Material Transfer'
          AND se.add_to_transit = 1
          AND {where_clause}
    """

    result = frappe.db.sql(query, values, as_dict=True)
    
    # Filter in Python: only keep rows with remaining qty > 0
    # This avoids the SQL HAVING clause issue with subquery columns
    filtered_result = []
    for row in result:
        remaining_qty = row.get('qty') or 0
        if remaining_qty > 0:
            filtered_result.append(row)
    
    return filtered_result