import frappe
import json
from frappe import _
from frappe.utils import flt
from datetime import datetime, time
from erpnext.accounts.doctype.pos_closing_entry.pos_closing_entry import get_pos_invoices
from erpnext.accounts.doctype.pos_invoice_merge_log.pos_invoice_merge_log import consolidate_pos_invoices

@frappe.whitelist(allow_guest=False)
def update_field(doctype, docname, fieldname, value, update_date: bool = True):
    try:
        # Validate DocType
        if not frappe.db.exists("DocType", doctype):
            return {
                "status": "Failed",
                "message": f"Invalid DocType: {doctype}"
            }

        # Validate document
        if not frappe.db.exists(doctype, docname):
            return {
                "status": "Failed",
                "message": f"{doctype} '{docname}' not found"
            }

        # Validate field exists in DocType
        meta = frappe.get_meta(doctype)
        field = meta.get_field(fieldname)

        if not field:
            return {
                "status": "Failed",
                "message": f"Field '{fieldname}' does not exist in {doctype}"
            }

        # Allow only custom fields
        # Check if field is custom
        is_custom = frappe.db.exists(
            "Custom Field",
            {"dt": doctype, "fieldname": fieldname}
        )
        
        if not is_custom:
            return {
                "status": "Failed",
                "message": f"Field '{fieldname}' is a standard field and cannot be edited"
            }

        # Load document
        doc = frappe.get_doc(doctype, docname)

        # Normal update (updates modified timestamp)
        if update_date:
            doc.set(fieldname, value)
            doc.save(ignore_permissions=True)
            frappe.db.commit()

        else:
            # SQL update (preserves modified timestamp)
            sql = f"""
                UPDATE `tab{doctype}`
                SET `{fieldname}` = %s
                WHERE name = %s
            """
            frappe.db.sql(sql, (value, docname))
            frappe.db.commit()

        return {
            "status": "Success",
            "message": f"{doctype} '{docname}' updated successfully"
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "update_field API Error")
        return {
            "status": "Failed",
            "message": str(e)
        }
            
@frappe.whitelist(allow_guest=False)
def update_fields(doctype, docname, fields: dict, update_date: bool = True):
    try:
        # Validate DocType
        if not frappe.db.exists("DocType", doctype):
            return {
                "status": "Failed",
                "message": f"Invalid DocType: {doctype}"
            }

        # Validate document
        if not frappe.db.exists(doctype, docname):
            return {
                "status": "Failed",
                "message": f"{doctype} '{docname}' not found"
            }

        meta = frappe.get_meta(doctype)

        # Validate fields and ensure they are custom
        for fieldname in fields.keys():
            field = meta.get_field(fieldname)

            if not field:
                return {
                    "status": "Failed",
                    "message": f"Field '{fieldname}' does not exist in {doctype}"
                }

            # Check if field is custom
            is_custom = frappe.db.exists(
                "Custom Field",
                {"dt": doctype, "fieldname": fieldname}
            )
            
            if not is_custom:
                return {
                    "status": "Failed",
                    "message": f"Field '{fieldname}' is a standard field and cannot be edited"
                }

        # Load document
        doc = frappe.get_doc(doctype, docname)

        # Normal update (updates modified timestamp)
        if update_date:
            for fieldname, value in fields.items():
                doc.set(fieldname, value)

            doc.save(ignore_permissions=True)
            frappe.db.commit()

        else:
            # SQL update (preserves modified timestamp)
            set_clauses = []
            values = []

            for fieldname, value in fields.items():
                set_clauses.append(f"`{fieldname}` = %s")
                values.append(value)

            values.append(docname)

            sql = f"""
                UPDATE `tab{doctype}`
                SET {", ".join(set_clauses)}
                WHERE name = %s
            """

            frappe.db.sql(sql, values)
            frappe.db.commit()

        return {
            "status": "Success",
            "message": f"{doctype} '{docname}' updated successfully"
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "update_fields API Error")
        return {
            "status": "Failed",
            "message": str(e)
        }

@frappe.whitelist()
def get_updated_items():
    frappe.local.response["type"] = "json"
    frappe.local.response["nocache"] = 1

    args = frappe.request.args

    is_new = int(args.get("is_new", 0))
    limit  = int(args.get("limit", 50))
    offset = int(args.get("offset", 0))

    field = "creation" if is_new == 1 else "modified"

    # 1️⃣ Total count (WITHOUT limit / offset)
    total_count = frappe.db.sql(
        f"""
        SELECT COUNT(*)
        FROM `tabItem`
        WHERE {field} >= custom_last_synced AND has_variants=0
        """,
        as_list=True
    )[0][0]

    # 2️⃣ Paged data
    query = f"""
        SELECT item_code
        FROM `tabItem`
        WHERE {field} >= custom_last_synced AND has_variants=0
        ORDER BY {field} ASC
        LIMIT %(limit)s OFFSET %(offset)s
    """

    items = frappe.db.sql(
        query,
        {"limit": limit, "offset": offset},
        as_dict=True
    )

    # 3️⃣ Pagination logic
    next_offset = offset + limit
    has_next_page = next_offset < total_count

    return {
        "total_count": total_count,
        "count": len(items),
        "items": [d.item_code for d in items],
        "limit": limit,
        "offset": offset,
        "next_page_token": next_offset if has_next_page else None,
        "has_next_page": has_next_page,
        "is_new": is_new
    }
    
def auto_close_pos_opening_entries():
    logger = frappe.logger("pos_auto_closing")
    logger.info("Starting auto POS closing job")

    openings = frappe.get_all(
        "POS Opening Entry",
        filters={"status": "Open", "docstatus": 1, "custom_ready_for_closing":1},
        fields=["name", "period_start_date", "posting_date", "pos_profile", "user", "company"],
    )

    for row in openings:
        try:
            opening = frappe.get_doc("POS Opening Entry", row.name)
            start_dt = opening.period_start_date  # date
            end_dt = datetime.combine(start_dt, time(23, 59, 59))  # datetime

            # 1️⃣ Fetch only same-day invoices
            invoices = get_pos_invoices(
                start=start_dt,
                end=end_dt,
                pos_profile=opening.pos_profile,
                user=opening.user,
            )

            if not invoices:
                logger.info(f"No invoices for {opening.name}, skipping")
                continue

            # 2️⃣ Build closing entry manually
            closing = frappe.new_doc("POS Closing Entry")
            closing.pos_opening_entry = opening.name
            closing.pos_profile = opening.pos_profile
            closing.user = opening.user
            closing.company = opening.company

            closing.posting_date = opening.posting_date
            closing.posting_time = "23:59:59"
            closing.period_start_date = start_dt
            closing.period_end_date = end_dt

            grand_total = 0
            net_total = 0
            total_qty = 0
            pos_transactions = []
            taxes = []
            payments = []

            # 3️⃣ Populate invoices and totals
            for inv in invoices:
                pos_transactions.append(
                    frappe._dict({
                        "pos_invoice": inv.name,
                        "posting_date": inv.posting_date,
                        "grand_total": inv.grand_total,
                        "customer": inv.customer,
                    })
                )
                grand_total += flt(inv.grand_total)
                net_total += flt(inv.net_total)
                total_qty += flt(inv.total_qty)

                # Taxes
                for t in inv.taxes:
                    existing_tax = [tx for tx in taxes if tx.account_head == t.account_head and tx.rate == t.rate]
                    if existing_tax:
                        existing_tax[0].amount += flt(t.tax_amount)
                    else:
                        taxes.append(frappe._dict({"account_head": t.account_head, "rate": t.rate, "amount": t.tax_amount}))

                # Payments
                for p in inv.payments:
                    existing_pay = [pay for pay in payments if pay.mode_of_payment == p.mode_of_payment]
                    if existing_pay:
                        existing_pay[0].expected_amount += flt(p.amount)
                    else:
                        payments.append(frappe._dict({"mode_of_payment": p.mode_of_payment, "opening_amount": 0, "expected_amount": p.amount}))

            closing.set("pos_transactions", pos_transactions)
            closing.set("taxes", taxes)
            closing.set("payment_reconciliation", payments)
            closing.grand_total = grand_total
            closing.net_total = net_total
            closing.total_quantity = total_qty

            closing.insert(ignore_permissions=True)
            closing.submit()

            logger.info(f"POS Closing Entry {closing.name} created for {opening.name}")

        except Exception:
            frappe.log_error(title=f"POS Auto Closing Failed: {row.name}", message=frappe.get_traceback())
            print(frappe.get_traceback())

    logger.info("Auto POS Closing job completed")
       
@frappe.whitelist()
def scan_barcode(search_value, **kwargs):
    """
    ERPNext v15 compatible barcode scan:
    1. Try Item Barcode
    2. Fallback to Item Code
    """

    # 1️⃣ Try standard barcode (Item Barcode table)
    item_code = frappe.db.get_value(
        "Item Barcode",
        {"barcode": search_value},
        "parent"
    )

    # 2️⃣ Fallback to Item Code
    if not item_code and frappe.db.exists("Item", search_value):
        item_code = search_value

    # ❌ STOP if item not found
    if not item_code:
        frappe.throw(
            _("Item not found for scanned barcode / code: {0}").format(search_value),
            frappe.DoesNotExistError
        )

    # ✅ Only return when valid item exists
    return {
        "item_code": item_code
    }

@frappe.whitelist()
def get_item_attributes(item_code):
    """Return Color and Size of an Item Variant, safe for store users"""
    if not item_code:
        return {}

    attrs = frappe.get_all(
        "Item Variant Attribute",
        filters={"parent": item_code},
        fields=["attribute", "attribute_value"]
    )

    result = {}
    for a in attrs:
        result[a.attribute.lower()] = a.attribute_value

    return result

@frappe.whitelist()
def get_mr_item_for_scan(material_request, item_code, used_items=None, used_qty_map=None):
    """Get MR item line for scanned item code with qty validation"""
    
    used_items = json.loads(used_items) if used_items else []
    used_qty_map = json.loads(used_qty_map) if used_qty_map else {}
    
    # Get all MR items for this item_code
    mr_items = frappe.get_all(
        "Material Request Item",
        filters={
            "parent": material_request,
            "item_code": item_code,
            "docstatus": 1
        },
        fields=["name", "item_code", "qty", "description", "stock_uom"],
        order_by="idx asc"
    )
    
    if not mr_items:
        return {"found": False, "error": "Item not in Material Request"}
    
    # Find first MR line with remaining qty
    for mr_item in mr_items:
        # Calculate already used qty for this MR line
        used_qty = used_qty_map.get(mr_item.name, 0)
        
        # Get qty from other stock entries (submitted or draft)
        other_used = frappe.db.sql("""
            SELECT SUM(qty) FROM `tabStock Entry Detail`
            WHERE material_request_item = %s
            AND docstatus < 2
            AND parent != %s
        """, (mr_item.name, frappe.form_dict.get('current_stock_entry', '')))[0][0] or 0
        
        total_used = used_qty + other_used
        remaining_qty = mr_item.qty - total_used
        
        if remaining_qty > 0 and mr_item.name not in used_items:
            mr_item["found"] = True
            mr_item["remaining_qty"] = remaining_qty
            mr_item["total_mr_qty"] = mr_item.qty
            return mr_item
    
    # All lines used or no remaining qty
    return {"found": False, "error": "All MR lines for this item are fully used"}

@frappe.whitelist()
def get_mr_item_remaining_qty(material_request_item, current_row_name=None, current_qty=0):
    """Get remaining qty for a specific MR item line"""
    
    mr_item = frappe.get_doc("Material Request Item", material_request_item)
    
    # Get used qty from other stock entry details
    used_in_other_rows = frappe.db.sql("""
        SELECT SUM(qty) FROM `tabStock Entry Detail`
        WHERE material_request_item = %s
        AND docstatus < 2
        AND name != %s
    """, (material_request_item, current_row_name or ''))[0][0] or 0
    
    remaining = mr_item.qty - used_in_other_rows
    return remaining if remaining > 0 else 0

@frappe.whitelist()
def validate_stock_entry_items(stock_entry_name):
    """Validate all items in Stock Entry against MR before submit"""
    stock_entry = frappe.get_doc("Stock Entry", stock_entry_name)
    
    if not stock_entry.custom_material_request:
        return {"valid": True}
    
    errors = []
    
    # Build map of MR items
    mr_items = frappe.get_all(
        "Material Request Item",
        filters={"parent": stock_entry.custom_material_request, "docstatus": 1},
        fields=["name", "item_code", "qty"]
    )
    mr_map = {item.name: item for item in mr_items}
    
    # Validate each row
    for item in stock_entry.items:
        if not item.material_request_item:
            errors.append(f"Row {item.idx}: {item.item_code} is not linked to Material Request")
            continue
            
        if item.material_request_item not in mr_map:
            errors.append(f"Row {item.idx}: Invalid Material Request link")
            continue
        
        mr_line = mr_map[item.material_request_item]
        
        # Check total used qty across all entries
        total_used_elsewhere = frappe.db.sql("""
            SELECT SUM(qty) FROM `tabStock Entry Detail`
            WHERE material_request_item = %s
            AND docstatus < 2
            AND parent != %s
        """, (item.material_request_item, stock_entry_name))[0][0] or 0
        
        total_with_current = total_used_elsewhere + item.qty
        
        if total_with_current > mr_line.qty:
            available = mr_line.qty - total_used_elsewhere
            errors.append(
                f"Row {item.idx}: Qty {item.qty} exceeds available {available} "
                f"(MR total: {mr_line.qty})"
            )
    
    return {
        "valid": len(errors) == 0,
        "errors": errors
    }
    
@frappe.whitelist(allow_guest=True)
def get_purchase_receipts_query(shipment_no):
    return frappe.db.sql(f"""SELECT `name` AS `receipt_document`, 'Purchase Receipt' AS `receipt_document_type`, `supplier`,`grand_total`, `posting_date`
FROM `tabPurchase Receipt` 
WHERE docstatus=1 AND custom_shipment_no= '{shipment_no}'""",as_dict=True )

@frappe.whitelist(allow_guest=True)
def get_purchase_invoice_items_query(shipment_no):
    return frappe.db.sql(f"""SELECT pi.`name` AS `purchase_invoice_no`,pitem.`item_code`,pitem.`item_name` ,pitem.`expense_account`, pi.`currency`,pi.conversion_rate AS `exchange_rate`,pitem.`base_amount`,pitem.`amount` 
FROM `tabPurchase Invoice Item` AS pitem
LEFT JOIN `tabPurchase Invoice` AS `pi` ON pitem.parent=pi.`name`
LEFT JOIN `tabItem` item ON pitem.item_code=item.name
WHERE  pi.docstatus=1 AND pitem.stock_uom='SERVICE' AND item.custom_include_item_in_lcv=1 AND pitem.custom_shipment_no= '{shipment_no}'""",as_dict=True )                  
