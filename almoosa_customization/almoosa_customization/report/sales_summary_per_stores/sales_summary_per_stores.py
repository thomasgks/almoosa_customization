# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.utils import flt
from frappe import msgprint, _
from frappe.utils import cstr

def execute(filters=None):
	columns, data = [], []
	columns=get_columns()
	data=get_report_data(filters, columns)
	return columns, data

def get_columns():
    return [

        {
            "label": _("WH"),
            "fieldname": "warehouse",
            "fieldtype": "Data",            
            "width": 60
        },
        {
            "label": _("#Inv"),
            "fieldname": "invoice_count",
            "fieldtype": "Int",            
            "width": 60
        },

        {
            "label": _("Qty"),
            "fieldname": "qty",
            "fieldtype": "Int",
            "width": 70
        },
        {
            "label": _("SaleB4Disc"),
            "fieldname": "sale_before_discount",
            "fieldtype": "Float",
            "width": 120
        },
        {
            "label": _("Disc"),
            "fieldname": "discount",
            "fieldtype": "Float",
            "width": 100
        },
        {
            "label": _("SaleWoTax"),
            "fieldname": "sale_without_tax",
            "fieldtype": "Float",
            "width": 120
        },
        {
            "label": _("Tax"),
            "fieldname": "tax",
            "fieldtype": "Float",
            "width": 100
        },
        {
            "label": _("SaleWithTax"),
            "fieldname": "sale_with_tax",
            "fieldtype": "Float",
            "width": 120
        },
        {
            "label": _("TotalCost"),
            "fieldname": "total_cost",
            "fieldtype": "Float",
            "width": 120
        },
        {
            "label": _("Margin"),
            "fieldname": "margin",
            "fieldtype": "Float",
            "width": 120
        },
        {
            "label": _("GpWoTax"),
            "fieldname": "profit",
            "fieldtype": "Float",
            "width": 100
        },

    ]

 
def get_conditions(filters):
    conditions = ""
    # Datetime filter
    if filters.get("from_datetime") and filters.get("to_datetime"):
        conditions=" AND (TIMESTAMP(hd.posting_date, hd.posting_time) BETWEEN %(from_datetime)s AND %(to_datetime)s)"
    if filters.get("warehouse"): conditions += " and item.warehouse in %(warehouse)s"  
    if filters.get("cost_center"): conditions += " and hd.cost_center in %(cost_center)s"  
    
    return conditions 

def get_data(filters):
    condition = get_conditions(filters) 
    #frappe.msgprint(str(condition))
    return frappe.db.sql("""
                       SELECT 
    LEFT(item.warehouse,3) AS warehouse,
    COUNT(DISTINCT item.parent) AS invoice_count,
    COALESCE(SUM(item.qty),0) AS qty,
    COALESCE(SUM(item.sales_b4_disc),0) AS sales_b4_disc,
    COALESCE(SUM(item.sales_b4_disc - tax.total),0) AS discount,
    COALESCE(SUM(item.sales_wo_tax),0) sales_wo_tax,
    COALESCE(SUM(tax.tax_amount_after_discount_amount),0) AS tax,
    COALESCE(SUM(tax.total),0) AS  sales_w_tax,
    COALESCE(SUM(im.cost),0) AS cost,
    COALESCE(SUM(item.sales_wo_tax-im.cost),0) AS margin,
    CASE WHEN SUM(tax.total)>0 THEN SUM(tax.total)/COALESCE(SUM(item.sales_wo_tax-im.cost),0)*100 ELSE 0 END AS profit
FROM
(
    SELECT 
        it.parent,
        it.item_code,
        it.warehouse,
        SUM(it.qty) qty,
        SUM(it.amount) sales_b4_disc,
        SUM(it.net_amount) sales_wo_tax
    FROM `tabPOS Invoice Item` it
    GROUP BY it.parent, it.warehouse
) AS item
INNER JOIN `tabSales Taxes and Charges` AS tax 
    ON tax.parent = item.parent 
    AND tax.parenttype = 'POS Invoice' 
    AND tax.rate>0 
INNER JOIN `tabPOS Invoice` hd 
    ON hd.name = item.parent
LEFT JOIN (SELECT item_code,valuation_rate AS cost ,warehouse FROM tabBin )AS im 
    ON im.item_code=item.item_code  AND im.warehouse= item.warehouse  
WHERE hd.docstatus=1 {condition}

GROUP BY item.warehouse;
    """.format(condition=condition), filters, as_dict=1)
   
          
def get_report_data(filters, columns):
	data = []
	row = []    
	line=get_data(filters)
	total_inv_nos=0
	total_inv_qty=0
	total_before_disc=0
	total_disc=0
	total_without_tax=0
	total_tax=0
	total_with_tax=0
	total_cost=0
	total_margin=0
	total_profit=0
	for a in line:
		total_inv_nos+=a.invoice_count or 0
		total_inv_qty+=a.qty or 0
		total_before_disc+=a.sales_b4_disc or 0
		total_disc+=a.discount or 0
		total_without_tax+=a.sales_wo_tax or 0
		total_tax+=a.tax or 0
		total_with_tax+=a.sales_w_tax or 0        
		total_cost+=a.cost or 0
		total_margin+=a.margin or 0
		total_profit+=a.profit or 0
        
		row=[a.warehouse,a.invoice_count,a.qty,a.sales_b4_disc,a.discount,a.sales_wo_tax,a.tax,a.sales_w_tax,a.cost,a.margin,a.profit]        
		if row:
			data.append(row)  
	row=["Total",total_inv_nos,total_inv_qty,total_before_disc,total_disc,total_without_tax,total_tax,total_with_tax,total_cost,total_margin,total_profit]       
	data.append(row)               
	return data 