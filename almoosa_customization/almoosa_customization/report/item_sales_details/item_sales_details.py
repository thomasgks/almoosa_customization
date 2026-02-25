import frappe
from frappe.utils import get_datetime
from decimal import Decimal, ROUND_HALF_UP


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

# ---------------------------------------------------------
#  COLUMNS
# ---------------------------------------------------------
def get_columns():
    return [
        {"label": "Store Code", "fieldname": "store_code", "fieldtype": "Data"},
        {"label": "Doc No", "fieldname": "doc_no", "fieldtype": "Data"},
        {"label": "Sales Date", "fieldname": "posting_date", "fieldtype": "Date"},
        {"label": "Sales Time", "fieldname": "posting_time", "fieldtype": "Time"},
        {"label": "Invoice Type", "fieldname": "invoice_type", "fieldtype": "Data"},
        {"label": "Cashier", "fieldname": "owner", "fieldtype": "Data"},
        {"label": "Associate", "fieldname": "associate", "fieldtype": "Data"},
        {"label": "Associate Name", "fieldname": "associate_name", "fieldtype": "Data"},
        {"label": "Customer ID", "fieldname": "customer_id", "fieldtype": "Data"},
        {"label": "Customer Phone", "fieldname": "customer_phone", "fieldtype": "Data"},
        {"label": "Item Code", "fieldname": "item_code", "fieldtype": "Data"},
        {"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data"},
        {"label": "Main", "fieldname": "group_level_1", "fieldtype": "Data"},
        {"label": "Gender", "fieldname": "group_level_2", "fieldtype": "Data"},
        {"label": "Category", "fieldname": "group_level_3", "fieldtype": "Data"},
        {"label": "Group", "fieldname": "group_level_4", "fieldtype": "Data"},
        {"label": "Subgroup", "fieldname": "group_level_5", "fieldtype": "Data"},
        {"label": "DCS Code", "fieldname": "dcs_code", "fieldtype": "Data"},
        {"label": "Vendor", "fieldname": "vendor", "fieldtype": "Data"},
        {"label": "Vendor Name", "fieldname": "vendor_name", "fieldtype": "Data"},
        {"label": "UPC", "fieldname": "barcode", "fieldtype": "Data"},
        {"label": "Model No", "fieldname": "model_no", "fieldtype": "Data"},
        {"label": "Year", "fieldname": "year", "fieldtype": "Data"},
        {"label": "Season", "fieldname": "season", "fieldtype": "Data"},
        {"label": "Color", "fieldname": "color", "fieldtype": "Data"},
        {"label": "Color Name", "fieldname": "color_name", "fieldtype": "Data"},
        {"label": "Size", "fieldname": "size", "fieldtype": "Data"},
        
        {"label": "List Price (Incl. VAT)", "fieldname": "original_price", "fieldtype": "Currency"},
        {"label": "Quantity", "fieldname": "qty", "fieldtype": "Float"},
        {"label": "Selling Price (Incl. VAT)", "fieldname": "selling_price", "fieldtype": "Currency"},
        
        {"label": "Discount Amount", "fieldname": "discount_amount", "fieldtype": "Currency"},
        {"label": "Total Discount ", "fieldname": "total_discount", "fieldtype": "Currency"},
        {"label": "Discount Reason", "fieldname": "discount_reason", "fieldtype": "Data"},
        
        {"label": "Unit Rate (Incl. VAT)", "fieldname": "unit_rate_w_vat", "fieldtype": "Currency"},
        {"label": "Grand Total (Incl. VAT)", "fieldname": "total", "fieldtype": "Currency"},
        
        {"label": "Net Unit Rate (Excl. VAT)", "fieldname": "net_rate", "fieldtype": "Currency"},
        {"label": "Net Total (Excl. VAT)", "fieldname": "net_total", "fieldtype": "Currency"},
        
        {"label": "Vat Amount", "fieldname": "vat_amount", "fieldtype": "Currency"},
        {"label": "Vat Total", "fieldname": "vat_total", "fieldtype": "Currency"},
        # NEW FIELDS
        {"label": "Unit Cost", "fieldname": "unit_cost", "fieldtype": "Currency"},
        {"label": "Total Cost", "fieldname": "total_cost", "fieldtype": "Currency"},
        {"label": "Current OH Qty", "fieldname": "oh_qty", "fieldtype": "Float"}
    ]
# ---------------------------------------------------------
#  DATA QUERY
# ---------------------------------------------------------
def get_data(filters):
    conditions = []
    values = {}

    # Date filter
    if filters.get("from_datetime") and filters.get("to_datetime"):
        conditions.append(" AND CONCAT(pi.posting_date, ' ', pi.posting_time) BETWEEN %(from)s AND %(to)s")
        values["from"] = filters.get("from_datetime")
        values["to"] = filters.get("to_datetime")

    # Multi-select filters
    multi_fields = {
        "vendor_code": "b.custom_brand_code",
        "supplier": "si.supplier",
        "item_code": "pii.item_code",
        "warehouse": "pi.set_warehouse"
    }

    for f, sql_field in multi_fields.items():
        val = filters.get(f)
        if val:
            if isinstance(val, list):
                conditions.append(f"{sql_field} IN %(f_{f})s")
                values[f"f_{f}"] = val
            elif isinstance(val, str):
                items = [d.strip() for d in val.split(",") if d.strip()]
                conditions.append(f"{sql_field} IN %(f_{f})s")
                values[f"f_{f}"] = items

    # Item Group filter (ANY LEVEL)
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

    where_clause = "  AND ".join(conditions) if conditions else "1=1"

    query = f"""
        SELECT
            pi.set_warehouse AS store_code,
            ia_season.attribute_value AS season,
            pi.owner,
            it.custom_dcs AS dcs_code,
            emp.employee_number AS associate,
            st.sales_person AS associate_name,
            SUBSTRING_INDEX(ig.name, '.', 1) AS group_level_1,
            SUBSTRING_INDEX(SUBSTRING_INDEX(ig.name, '.', 2), '.', -1) AS group_level_2,
            SUBSTRING_INDEX(SUBSTRING_INDEX(ig.name, '.', 3), '.', -1) AS group_level_3,
            SUBSTRING_INDEX(SUBSTRING_INDEX(ig.name, '.', 4), '.', -1) AS group_level_4,
            SUBSTRING_INDEX(ig.name, '.', -1) AS group_level_5,
            ia_size.attribute_value AS size,
            pi.customer AS customer_id,
            ib.barcode,
            c.mobile_no AS customer_phone,
            pii.price_list_rate AS original_price,
            pii.qty,
            (pii.price_list_rate * pii.qty ) as selling_price,
            pi.posting_date,
            pii.rate AS current_price,
            pi.posting_time,
            NULLIF(bin.valuation_rate, 0) AS unit_cost,
            pi.custom_reference_doc_no AS doc_no,
            COALESCE(bin.actual_qty,0) AS oh_qty,
            CASE WHEN pi.is_return = 1 THEN 'RETURN' ELSE 'SALE' END AS invoice_type,
            
            --si.supplier AS vendor,
            b.custom_brand_code as vendor, 
            sup.supplier_name AS vendor_name,
            (pii.discount_amount + (pii.distributed_discount_amount * 1.15)/pii.qty) AS discount_amount,
            (ABS((pii.discount_amount * pii.qty) + (pii.distributed_discount_amount * 1.15))) AS total_discount,
            (pii.distributed_discount_amount * 1.15) as distributed_discount_amount,
            pii.custom_discount_reason AS discount_reason,
            pii.item_code,
            pii.item_name,
            ia_color.attribute_value AS color,
            ia_colorname.attribute_value AS color_name,
            ia_year.attribute_value AS year,
            it.custom_model_no AS model_no,
            pii.net_rate AS net_rate,
			pii.net_amount AS net_amount,
			pii.amount AS gross_amount,            
            COALESCE((bin.valuation_rate * pii.qty),0) AS total_cost
        FROM `tabPOS Invoice` pi
        JOIN `tabPOS Invoice Item` pii ON pii.parent = pi.name
        LEFT JOIN `tabItem` it ON it.name = pii.item_code
        LEFT JOIN `tabBin` bin ON bin.item_code = pii.item_code AND bin.warehouse = pi.set_warehouse
        LEFT JOIN `tabCustomer` c ON c.name = pi.customer
        LEFT JOIN `tabItem Barcode` ib ON ib.parent = it.name
        LEFT JOIN `tabBrand` b ON b.name = it.brand
        LEFT JOIN `tabItem Supplier` si ON si.parent = it.name
        LEFT JOIN `tabSupplier` sup ON sup.name = si.supplier
        LEFT JOIN `tabSales Team` st ON st.parent = pi.name
        LEFT JOIN `tabSales Person` sp ON sp.name = st.sales_person
        LEFT JOIN `tabEmployee` emp ON emp.name = sp.employee
        LEFT JOIN `tabItem Variant Attribute` ia_season ON ia_season.parent = it.name AND ia_season.attribute = 'Season'
        LEFT JOIN `tabItem Variant Attribute` ia_color ON ia_color.parent = it.name AND ia_color.attribute = 'Color'
        LEFT JOIN `tabItem Variant Attribute` ia_colorname ON ia_colorname.parent = it.name AND ia_colorname.attribute = 'Color Name'
        LEFT JOIN `tabItem Variant Attribute` ia_size ON ia_size.parent = it.name AND ia_size.attribute = 'Size'
        LEFT JOIN `tabItem Variant Attribute` ia_year ON ia_year.parent = it.name AND ia_year.attribute = 'Year'
        LEFT JOIN `tabItem Group` ig ON ig.name = it.item_group
        WHERE pi.custom_exclude=0 AND pi.docstatus=1 {where_clause}
    """

    rows = frappe.db.sql(query, values, as_dict=True)

    for row in rows:
        
        unit_rate_w_vat = row["original_price"] - abs(row["discount_amount"]) or 0
        gross = row.get("qty") * unit_rate_w_vat or 0  # with VAT
                
        net = row.get("net_amount") or 0      # without VAT
        
        vat_amount= (row["net_rate"] * 0.15) or 0
        vat_total = vat_amount * row.get("qty") or 0          # VAT per line
        
        row["unit_rate_w_vat"] = unit_rate_w_vat
        row["total"] = gross                  # Total (with VAT)
        
        row["net_total"] = net         #  Net Total W/O Vat
        
        row["vat_amount"] = vat_amount 
        row["vat_total"] = vat_total               # Vat Total
        
        

    return rows