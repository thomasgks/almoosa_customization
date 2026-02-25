# Copyright (c) 2026
# For license information, please see license.txt

import frappe


def execute(filters=None):
    filters = filters or {}

    # enforce date range (needed for all calculations)
    if not filters.get("from_datetime") or not filters.get("to_datetime"):
        frappe.throw("Please set From Date / time and To Date / time")

    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": "Vendor Code", "fieldname": "vendor_code", "fieldtype": "Data"},
        {"label": "Vendor Name", "fieldname": "vendor_name", "fieldtype": "Data"},

        {"label": "Main", "fieldname": "group_l1", "fieldtype": "Data"},
        {"label": "Gender", "fieldname": "group_l2", "fieldtype": "Data"},
        {"label": "Category", "fieldname": "group_l3", "fieldtype": "Data"},
        {"label": "Group", "fieldname": "group_l4", "fieldtype": "Data"},
        {"label": "Sub Group", "fieldname": "group_l5", "fieldtype": "Data"},

        {"label": "Item No", "fieldname": "item_code", "fieldtype": "Data"},
        {"label": "ALU", "fieldname": "alu", "fieldtype": "Data"},
        {"label": "Description 1", "fieldname": "item_name", "fieldtype": "Data"},
        {"label": "Supplier", "fieldname": "supplier", "fieldtype": "Data"},
        {"label": "Product Type", "fieldname": "product_type", "fieldtype": "Data"},
        {"label": "Model No", "fieldname": "model_no", "fieldtype": "Data"},

        {"label": "Color Name", "fieldname": "color_name", "fieldtype": "Data"},
        {"label": "Year", "fieldname": "year", "fieldtype": "Data"},
        {"label": "Season", "fieldname": "season", "fieldtype": "Data"},
        {"label": "DCS Code", "fieldname": "dcs_code", "fieldtype": "Data"},
        {"label": "Size", "fieldname": "size", "fieldtype": "Data"},
        {"label": "UPC", "fieldname": "barcode", "fieldtype": "Data"},

        {"label": "Opening Qty", "fieldname": "opening_qty", "fieldtype": "Float"},
        {"label": "Purchase Qty", "fieldname": "purchase_qty", "fieldtype": "Float"},
        {"label": "Sold Qty", "fieldname": "sold_qty", "fieldtype": "Float"},
        {"label": "Adjustment Qty", "fieldname": "adjustment_qty", "fieldtype": "Float"},
        {"label": "In Transit Qty", "fieldname": "in_transit_qty", "fieldtype": "Float"},
        {"label": "Remaining Qty", "fieldname": "remaining_qty", "fieldtype": "Float"},
        {"label": "Current Balance", "fieldname": "current_balance", "fieldtype": "Float"},

        {"label": "Status", "fieldname": "status", "fieldtype": "Data"},

        {"label": "Purchase Cost", "fieldname": "purchase_cost", "fieldtype": "Currency"},
        {"label": "Sale Cost", "fieldname": "sale_cost", "fieldtype": "Currency"},
        {"label": "Adjustment Cost", "fieldname": "adjustment_cost", "fieldtype": "Currency"},
        {"label": "On Hand Cost", "fieldname": "onhand_cost", "fieldtype": "Currency"},

        {"label": "Sold Price (With Tax)", "fieldname": "sold_price_w_tax", "fieldtype": "Currency"},
        {"label": "Sold Price (Without Tax)", "fieldname": "sold_price_wo_tax", "fieldtype": "Currency"},
        {"label": "Onhand Price", "fieldname": "onhand_price", "fieldtype": "Currency"},
    ]


def get_data(filters):
    conditions = []
    values = {
        "from": filters["from_datetime"],
        "to": filters["to_datetime"],
    }

    def multi(field, sql_field):
        val = filters.get(field)
        if val:
            if isinstance(val, str):
                val = [d.strip() for d in val.split(",")]
            conditions.append(f"{sql_field} IN %({field})s")
            values[field] = tuple(val)

    multi("vendor_code", "b.custom_brand_code")
    multi("supplier", "sup.name")
    multi("item_group", "ig.name")
    multi("year", "it.custom_year")

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # Add zero stock filter
    include_zero_stock = filters.get("include_zero_stock", 0)
    
    query = f"""
        WITH 
        -- Pre-calculate opening recon qty per item
        opening_recon AS (
            SELECT sle.item_code, COALESCE(SUM(sle.qty_after_transaction), 0) as qty
            FROM `tabStock Ledger Entry` sle
            JOIN `tabStock Reconciliation` sr ON sr.name = sle.voucher_no
            WHERE sle.posting_datetime < %(to)s
            AND sle.voucher_type = 'Stock Reconciliation'
            AND sr.purpose IN ('Opening Stock', 'Opening')
            GROUP BY sle.item_code
        ),
        -- Pre-calculate SLE before from date
        sle_before_from AS (
            SELECT item_code, COALESCE(SUM(actual_qty), 0) as qty
            FROM `tabStock Ledger Entry`
            WHERE posting_datetime < %(from)s
            GROUP BY item_code
        ),
        -- Pre-calculate SLE up to to date
        sle_up_to_to AS (
            SELECT item_code, COALESCE(SUM(actual_qty), 0) as qty
            FROM `tabStock Ledger Entry`
            WHERE posting_datetime <= %(to)s
            GROUP BY item_code
        ),
        -- Pre-calculate purchase qty and cost
        purchase_data AS (
            SELECT pri.item_code,
                   COALESCE(SUM(pri.qty), 0) as qty,
                   COALESCE(SUM(pri.qty * pri.rate), 0) as cost
            FROM `tabPurchase Receipt Item` pri
            JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
            WHERE pr.docstatus = 1
            AND pr.posting_date BETWEEN DATE(%(from)s) AND DATE(%(to)s)
            GROUP BY pri.item_code
        ),
        -- Pre-calculate sold qty and prices
        sold_data AS (
            SELECT posi.item_code,
                   COALESCE(SUM(posi.qty), 0) as qty,
                   COALESCE(SUM(posi.net_amount), 0) as net_amount,
                   COALESCE(SUM(posi.net_amount * 1.15), 0) as net_amount_with_tax
            FROM `tabPOS Invoice Item` posi
            JOIN `tabPOS Invoice` pos ON pos.name = posi.parent
            WHERE pos.docstatus = 1 
            AND pos.custom_exclude = 0
            AND pos.posting_date BETWEEN DATE(%(from)s) AND DATE(%(to)s)
            GROUP BY posi.item_code
        ),
        -- Pre-calculate adjustment qty and cost
        adjustment_data AS (
            SELECT sri.item_code,
                   COALESCE(SUM(sri.quantity_difference), 0) as qty_diff,
                   COALESCE(SUM(sri.amount_difference), 0) as amount_diff
            FROM `tabStock Reconciliation Item` sri
            JOIN `tabStock Reconciliation` sr ON sr.name = sri.parent
            WHERE sr.docstatus = 1
            AND sr.purpose = 'Stock Reconciliation'
            AND sr.posting_date BETWEEN DATE(%(from)s) AND DATE(%(to)s)
            GROUP BY sri.item_code
        ),
        -- Pre-calculate in transit qty
        in_transit_data AS (
            SELECT sed.item_code,
                   COALESCE(SUM(sed.qty - sed.transferred_qty), 0) as qty
            FROM `tabStock Entry Detail` sed
            JOIN `tabStock Entry` se ON se.name = sed.parent
            WHERE se.docstatus = 1
            AND se.stock_entry_type = 'Material Transfer'
            AND se.add_to_transit = 1
            AND sed.transferred_qty < sed.qty
            AND se.posting_date BETWEEN DATE(%(from)s) AND DATE(%(to)s)
            GROUP BY sed.item_code
        ),
        -- Pre-calculate average valuation rate per item
        item_valuation AS (
            SELECT item_code, COALESCE(AVG(valuation_rate), 0) as avg_rate
            FROM `tabBin`
            GROUP BY item_code
        ),
        -- Pre-calculate RSP price
        item_price_rsp AS (
            SELECT item_code, price_list_rate
            FROM `tabItem Price`
            WHERE price_list = 'RSP'
            GROUP BY item_code
        ),
        -- Main calculations
        calculated_data AS (
            SELECT 
                it.name as item_code,
                COALESCE(orcon.qty, 0) as opening_recon_qty,
                COALESCE(sbf.qty, 0) as sle_before_from_qty,
                COALESCE(sto.qty, 0) as sle_up_to_to_qty,
                COALESCE(pd.qty, 0) as purchase_qty,
                COALESCE(pd.cost, 0) as purchase_cost,
                COALESCE(sd.qty, 0) as sold_qty,
                COALESCE(sd.net_amount, 0) as sold_net_amount,
                COALESCE(sd.net_amount_with_tax, 0) as sold_price_w_tax,
                COALESCE(ad.qty_diff, 0) as adjustment_qty,
                COALESCE(ad.amount_diff, 0) as adjustment_cost,
                COALESCE(itd.qty, 0) as in_transit_qty,
                COALESCE(iv.avg_rate, 0) as avg_valuation_rate,
                COALESCE(ipr.price_list_rate, 0) as rsp_price
            FROM `tabItem` it
            LEFT JOIN opening_recon orcon ON orcon.item_code = it.name
            LEFT JOIN sle_before_from sbf ON sbf.item_code = it.name
            LEFT JOIN sle_up_to_to sto ON sto.item_code = it.name
            LEFT JOIN purchase_data pd ON pd.item_code = it.name
            LEFT JOIN sold_data sd ON sd.item_code = it.name
            LEFT JOIN adjustment_data ad ON ad.item_code = it.name
            LEFT JOIN in_transit_data itd ON itd.item_code = it.name
            LEFT JOIN item_valuation iv ON iv.item_code = it.name
            LEFT JOIN item_price_rsp ipr ON ipr.item_code = it.name
        )
        SELECT
            b.custom_brand_code AS vendor_code,
            sup.supplier_name AS vendor_name,

            SUBSTRING_INDEX(ig.name,'.',1) AS group_l1,
            SUBSTRING_INDEX(SUBSTRING_INDEX(ig.name,'.',2),'.',-1) AS group_l2,
            SUBSTRING_INDEX(SUBSTRING_INDEX(ig.name,'.',3),'.',-1) AS group_l3,
            SUBSTRING_INDEX(SUBSTRING_INDEX(ig.name,'.',4),'.',-1) AS group_l4,
            SUBSTRING_INDEX(ig.name,'.',-1) AS group_l5,

            it.name AS item_code,
            it.custom_model_no AS alu,
            it.item_name,
            si.supplier,
            it.custom_product_type AS product_type,
            it.custom_model_no AS model_no,
            it.custom_dcs AS dcs_code,

            ia_color.attribute_value AS color_name,
            ia_year.attribute_value AS year,
            ia_season.attribute_value AS season,
            ia_size.attribute_value AS size,

            ib.barcode,

            -- Opening Qty
            (cd.opening_recon_qty + cd.sle_before_from_qty) AS opening_qty,

            -- Purchase Qty
            cd.purchase_qty AS purchase_qty,

            -- Sold Qty
            cd.sold_qty AS sold_qty,

            -- Adjustment Qty
            cd.adjustment_qty AS adjustment_qty,

            -- In Transit Qty
            cd.in_transit_qty AS in_transit_qty,

            -- Remaining Qty
            (cd.opening_recon_qty + cd.sle_before_from_qty + cd.purchase_qty - cd.sold_qty + cd.adjustment_qty - cd.in_transit_qty) AS remaining_qty,

            -- Current Balance
            (cd.opening_recon_qty + cd.sle_up_to_to_qty - cd.sold_qty - cd.in_transit_qty) AS current_balance,

            -- Status
            CASE
                WHEN (cd.opening_recon_qty + cd.sle_before_from_qty + cd.purchase_qty - cd.sold_qty + cd.adjustment_qty - cd.in_transit_qty)
                     = (cd.opening_recon_qty + cd.sle_up_to_to_qty - cd.sold_qty - cd.in_transit_qty)
                THEN 'Typical'
                ELSE 'Need to check'
            END AS status,

            -- Purchase Cost
            cd.purchase_cost AS purchase_cost,

            -- Sale Cost
            (cd.sold_qty * cd.avg_valuation_rate) AS sale_cost,

            -- Adjustment Cost
            cd.adjustment_cost AS adjustment_cost,

            -- On Hand Cost
            ((cd.opening_recon_qty + cd.sle_up_to_to_qty - cd.sold_qty - cd.in_transit_qty) * cd.avg_valuation_rate) AS onhand_cost,

            -- Sold Price With Tax
            cd.sold_price_w_tax AS sold_price_w_tax,

            -- Sold Price Without Tax
            cd.sold_net_amount AS sold_price_wo_tax,

            -- Onhand Price
            ((cd.opening_recon_qty + cd.sle_up_to_to_qty - cd.sold_qty - cd.in_transit_qty) * cd.rsp_price) AS onhand_price

        FROM `tabItem` it
        INNER JOIN calculated_data cd ON cd.item_code = it.name
        LEFT JOIN `tabItem Group` ig ON ig.name = it.item_group
        LEFT JOIN `tabBrand` b ON b.name = it.brand
        LEFT JOIN `tabItem Supplier` si ON si.parent = it.name
        LEFT JOIN `tabSupplier` sup ON sup.name = si.supplier
        LEFT JOIN `tabItem Barcode` ib ON ib.parent = it.name

        LEFT JOIN `tabItem Variant Attribute` ia_color
            ON ia_color.parent = it.name AND ia_color.attribute = 'Color Name'
        LEFT JOIN `tabItem Variant Attribute` ia_year
            ON ia_year.parent = it.name AND ia_year.attribute = 'Year'
        LEFT JOIN `tabItem Variant Attribute` ia_season
            ON ia_season.parent = it.name AND ia_season.attribute = 'Season'
        LEFT JOIN `tabItem Variant Attribute` ia_size
            ON ia_size.parent = it.name AND ia_size.attribute = 'Size'

        WHERE {where_clause}
        {"AND (cd.purchase_qty != 0 OR cd.sold_qty != 0 OR cd.adjustment_qty != 0 OR cd.in_transit_qty != 0 OR (cd.opening_recon_qty + cd.sle_up_to_to_qty - cd.sold_qty - cd.in_transit_qty) != 0)" if not include_zero_stock else ""}
        GROUP BY it.name
    """

    return frappe.db.sql(query, values, as_dict=True)