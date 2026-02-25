# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


from operator import itemgetter
from typing import Any, TypedDict

import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.query_builder.functions import Coalesce
from frappe.utils import add_days, cint, date_diff, flt, getdate
from frappe.utils import get_datetime
from frappe.query_builder.functions import Concat
from frappe.utils.nestedset import get_descendants_of

import erpnext
from erpnext.stock.doctype.inventory_dimension.inventory_dimension import get_inventory_dimensions
from erpnext.stock.doctype.warehouse.warehouse import apply_warehouse_filter
from erpnext.stock.report.stock_ageing.stock_ageing import FIFOSlots, get_average_age
from erpnext.stock.utils import add_additional_uom_columns


class StockBalanceFilter(TypedDict):
	company: str | None
	from_date: str
	to_date: str
	item_group: str | None
	item: list[str] | None
	warehouse: list[str] | None
	warehouse_type: str | None
	include_uom: str | None
	show_stock_ageing_data: bool
	show_variant_attributes: bool


SLEntry = dict[str, Any]


# ---------------------------------------------------------
#  PERMISSION CONFIGURATION
# ---------------------------------------------------------
# Define which roles can see cost/value fields
COST_VIEW_ROLES = ["MAATC - Allocator","Accounts Manager", "Finance Manager", "System Manager", "Stock Manager"]
COST_FIELDS = ["bal_val", "opening_val", "in_val", "out_val", "val_rate"]


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


def execute(filters: StockBalanceFilter | None = None):
	columns, data = StockBalanceReport(filters).run()
	
	# Apply field-level masking based on permissions
	if not can_view_costs():
		data = mask_cost_fields(data)
	
	return columns, data


class StockBalanceReport:
	def __init__(self, filters: StockBalanceFilter | None) -> None:
		self.filters = filters
		self.from_datetime = get_datetime(self.filters.get("from_date"))
		self.to_datetime = get_datetime(self.filters.get("to_date"))

		# ✅ REQUIRED: date-only versions for ERPNext core logic
		self.from_date = getdate(self.from_datetime)
		self.to_date = getdate(self.to_datetime)

		self.start_from = None
		self.data = []
		self.columns = []
		self.sle_entries: list[SLEntry] = []
		self.set_company_currency()

	def set_company_currency(self) -> None:
		if self.filters.get("company"):
			self.company_currency = erpnext.get_company_currency(self.filters.get("company"))
		else:
			self.company_currency = frappe.db.get_single_value("Global Defaults", "default_currency")

	def run(self):
		self.float_precision = cint(frappe.db.get_default("float_precision")) or 3

		self.inventory_dimensions = self.get_inventory_dimension_fields()
		self.prepare_opening_data_from_closing_balance()
		self.prepare_stock_ledger_entries()
		self.prepare_new_data()

		if not self.columns:
			self.columns = self.get_columns()

		self.add_additional_uom_columns()

		return self.columns, self.data

	def prepare_opening_data_from_closing_balance(self) -> None:
		self.opening_data = frappe._dict({})

		closing_balance = self.get_closing_balance()
		if not closing_balance:
			return

		self.start_from = get_datetime(
			f"{add_days(closing_balance[0].to_date, 1)} 00:00:00"
		)
		res = frappe.get_doc("Closing Stock Balance", closing_balance[0].name).get_prepared_data()

		for entry in res.data:
			entry = frappe._dict(entry)

			group_by_key = self.get_group_by_key(entry)
			if group_by_key not in self.opening_data:
				self.opening_data.setdefault(group_by_key, entry)

	def prepare_new_data(self):
		self.item_warehouse_map = self.get_item_warehouse_map()

		if self.filters.get("show_stock_ageing_data"):
			self.filters["show_warehouse_wise_stock"] = True
			item_wise_fifo_queue = FIFOSlots(self.filters, self.sle_entries).generate()

		_func = itemgetter(1)

		del self.sle_entries

		sre_details = self.get_sre_reserved_qty_details()

		variant_values = {}
		if self.filters.get("show_variant_attributes"):
			variant_values = self.get_variant_values_for()

		for _key, report_data in self.item_warehouse_map.items():
			if variant_data := variant_values.get(report_data.item_code):
				report_data.update(variant_data)

			if self.filters.get("show_stock_ageing_data"):
				opening_fifo_queue = self.get_opening_fifo_queue(report_data) or []

				fifo_queue = []
				if fifo_queue := item_wise_fifo_queue.get((report_data.item_code, report_data.warehouse)):
					fifo_queue = fifo_queue.get("fifo_queue")

				if fifo_queue:
					opening_fifo_queue.extend(fifo_queue)

				stock_ageing_data = {"average_age": 0, "earliest_age": 0, "latest_age": 0}
				if opening_fifo_queue:
					fifo_queue = sorted(filter(_func, opening_fifo_queue), key=_func)
					if not fifo_queue:
						continue

					to_date = self.to_date
					stock_ageing_data["average_age"] = get_average_age(fifo_queue, to_date)
					stock_ageing_data["earliest_age"] = date_diff(to_date, fifo_queue[0][1])
					stock_ageing_data["latest_age"] = date_diff(to_date, fifo_queue[-1][1])
					stock_ageing_data["fifo_queue"] = fifo_queue

				report_data.update(stock_ageing_data)

			report_data.update(
				{"reserved_stock": sre_details.get((report_data.item_code, report_data.warehouse), 0.0)}
			)

			if (
				not self.filters.get("include_zero_stock_items")
				and report_data
				and report_data.bal_qty == 0
				and report_data.bal_val == 0
			):
				continue

			self.data.append(report_data)

	def get_item_warehouse_map(self):
		item_warehouse_map = {}
		self.opening_vouchers = self.get_opening_vouchers()

		if self.filters.get("show_stock_ageing_data"):
			self.sle_entries = self.sle_query.run(as_dict=True)

		# Convert sle_entries to list for easier processing
		with frappe.db.unbuffered_cursor():
			if not self.filters.get("show_stock_ageing_data"):
				self.sle_entries = list(self.sle_query.run(as_dict=True, as_iterator=True))
		
		# Get POS entries
		pos_entries = self.get_pos_entries()
		
		# Combine all entries
		all_entries = list(self.sle_entries) + list(pos_entries)
		
		# Sort by posting_datetime to ensure correct order
		all_entries.sort(key=lambda x: get_datetime(x.get('posting_datetime')))
		
		# Process all entries together
		for entry in all_entries:
			group_by_key = self.get_group_by_key(entry)
			
			if group_by_key not in item_warehouse_map:
				self.initialize_data(item_warehouse_map, group_by_key, entry)

			self.prepare_item_warehouse_map(item_warehouse_map, entry, group_by_key)

			if self.opening_data.get(group_by_key):
				del self.opening_data[group_by_key]

		for group_by_key, entry in self.opening_data.items():
			if group_by_key not in item_warehouse_map:
				self.initialize_data(item_warehouse_map, group_by_key, entry)

		item_warehouse_map = filter_items_with_no_transactions(
			item_warehouse_map, self.float_precision, self.inventory_dimensions
		)

		return item_warehouse_map

	def get_pos_entries(self):
		"""Get POS invoices that are not consolidated"""
		# Use direct SQL query
		company_filter = f"AND pi.company = '{self.filters.company}'" if self.filters.get("company") else ""
		warehouse_filter = ""
		if self.filters.get("warehouse"):
			warehouses = ', '.join([f"'{wh}'" for wh in self.filters.get("warehouse")])
			warehouse_filter = f"AND pii.warehouse IN ({warehouses})"
		
		# Apply item filters for POS queries
		item_filter = ""
		if self.filters.get("item_code"):
			# If item_code filter is provided, filter by specific items
			items = ', '.join([f"'{item}'" for item in self.filters.get("item_code")])
			item_filter = f"AND pii.item_code IN ({items})"
		elif self.filters.get("item_group"):
			# If item_group filter is provided, get all items in that group
			children = get_descendants_of("Item Group", self.filters.get("item_group"), ignore_permissions=True)
			all_groups = [self.filters.get("item_group")] + children
			
			# Get items in the item group
			items_in_group = frappe.get_all(
				"Item",
				filters={"item_group": ["in", all_groups]},
				pluck="name"
			)
			if items_in_group:
				items_str = ', '.join([f"'{item}'" for item in items_in_group])
				item_filter = f"AND pii.item_code IN ({items_str})"
		
		# Query for POS sales (non-return) - SHOULD BE NEGATIVE (OUT)
		pos_sales_sql = f"""
			SELECT 
				pii.item_code,
				pii.warehouse,
				CONCAT(pi.posting_date, ' ', pi.posting_time) as posting_datetime,
				(pii.stock_qty * -1) as actual_qty,
				COALESCE(
					(SELECT valuation_rate 
					FROM `tabStock Ledger Entry` sle
					WHERE sle.item_code = pii.item_code 
					AND sle.warehouse = pii.warehouse
					AND sle.docstatus = 1
					AND sle.posting_datetime < CONCAT(pi.posting_date, ' ', pi.posting_time)
					ORDER BY sle.posting_datetime DESC 
					LIMIT 1),
					it.valuation_rate, 
					0
				) as valuation_rate,
				pi.company,
				'POS Invoice' as voucher_type,
				(pii.stock_qty * -1 * COALESCE(
					(SELECT valuation_rate 
					FROM `tabStock Ledger Entry` sle
					WHERE sle.item_code = pii.item_code 
					AND sle.warehouse = pii.warehouse
					AND sle.docstatus = 1
					AND sle.posting_datetime < CONCAT(pi.posting_date, ' ', pi.posting_time)
					ORDER BY sle.posting_datetime DESC 
					LIMIT 1),
					it.valuation_rate, 
					0
				)) as stock_value_difference,
				pii.item_code as name,
				pii.parent as voucher_no,
				NULL as stock_value,
				NULL as batch_no,
				NULL as serial_no,
				NULL as serial_and_batch_bundle,
				0 as has_serial_no,
				it.item_group,
				it.stock_uom,
				it.item_name
			FROM `tabPOS Invoice` pi
			INNER JOIN `tabPOS Invoice Item` pii ON pi.name = pii.parent
			LEFT JOIN `tabItem` it ON pii.item_code = it.name
			WHERE pi.docstatus = 1 AND custom_exclude = 0
				AND pi.status != 'Consolidated'
				AND pi.is_return = 0
				AND CONCAT(pi.posting_date, ' ', pi.posting_time) >= '{self.from_datetime}'
				AND CONCAT(pi.posting_date, ' ', pi.posting_time) <= '{self.to_datetime}'
				{company_filter}
				{warehouse_filter}
				{item_filter}
		"""
		
		# Query for POS returns - SHOULD BE POSITIVE (IN)
		# FIX: Use ABS() since pii.stock_qty is negative for return invoices
		pos_returns_sql = f"""
			SELECT 
				pii.item_code,
				pii.warehouse,
				CONCAT(pi.posting_date, ' ', pi.posting_time) as posting_datetime,
				ABS(pii.stock_qty) as actual_qty,
				COALESCE(
					(SELECT valuation_rate 
					FROM `tabStock Ledger Entry` sle
					WHERE sle.item_code = pii.item_code 
					AND sle.warehouse = pii.warehouse
					AND sle.docstatus = 1
					AND sle.posting_datetime < CONCAT(pi.posting_date, ' ', pi.posting_time)
					ORDER BY sle.posting_datetime DESC 
					LIMIT 1),
					it.valuation_rate, 
					0
				) as valuation_rate,
				pi.company,
				'POS Return' as voucher_type,
				(ABS(pii.stock_qty) * COALESCE(
					(SELECT valuation_rate 
					FROM `tabStock Ledger Entry` sle
					WHERE sle.item_code = pii.item_code 
					AND sle.warehouse = pii.warehouse
					AND sle.docstatus = 1
					AND sle.posting_datetime < CONCAT(pi.posting_date, ' ', pi.posting_time)
					ORDER BY sle.posting_datetime DESC 
					LIMIT 1),
					it.valuation_rate, 
					0
				)) as stock_value_difference,
				pii.item_code as name,
				pii.parent as voucher_no,
				NULL as stock_value,
				NULL as batch_no,
				NULL as serial_no,
				NULL as serial_and_batch_bundle,
				0 as has_serial_no,
				it.item_group,
				it.stock_uom,
				it.item_name
			FROM `tabPOS Invoice` pi
			INNER JOIN `tabPOS Invoice Item` pii ON pi.name = pii.parent
			LEFT JOIN `tabItem` it ON pii.item_code = it.name
			WHERE pi.docstatus = 1 AND custom_exclude = 0
				AND pi.status != 'Consolidated'
				AND pi.is_return = 1
				AND CONCAT(pi.posting_date, ' ', pi.posting_time) >= '{self.from_datetime}'
				AND CONCAT(pi.posting_date, ' ', pi.posting_time) <= '{self.to_datetime}'
				{company_filter}
				{warehouse_filter}
				{item_filter}
		"""
		
		# Execute queries
		sales_entries = frappe.db.sql(pos_sales_sql, as_dict=True)
		return_entries = frappe.db.sql(pos_returns_sql, as_dict=True)
		
		return sales_entries + return_entries

	def get_sre_reserved_qty_details(self) -> dict:
		from erpnext.stock.doctype.stock_reservation_entry.stock_reservation_entry import (
			get_sre_reserved_qty_for_items_and_warehouses as get_reserved_qty_details,
		)

		item_code_list, warehouse_list = [], []
		for d in self.item_warehouse_map:
			item_code_list.append(d[1])
			warehouse_list.append(d[2])

		return get_reserved_qty_details(item_code_list, warehouse_list)

	def prepare_item_warehouse_map(self, item_warehouse_map, entry, group_by_key):
		qty_dict = item_warehouse_map[group_by_key]
		for field in self.inventory_dimensions:
			qty_dict[field] = entry.get(field)

		# Get values using dictionary access for both dict and object entries
		voucher_type = entry.get('voucher_type') if isinstance(entry, dict) else entry.voucher_type
		batch_no = entry.get('batch_no') if isinstance(entry, dict) else entry.batch_no
		serial_no = entry.get('serial_no') if isinstance(entry, dict) else entry.serial_no
		qty_after_transaction = entry.get('qty_after_transaction') if isinstance(entry, dict) else entry.qty_after_transaction
		actual_qty = entry.get('actual_qty') if isinstance(entry, dict) else entry.actual_qty
		stock_value_difference = entry.get('stock_value_difference') if isinstance(entry, dict) else entry.stock_value_difference
		valuation_rate = entry.get('valuation_rate') if isinstance(entry, dict) else entry.valuation_rate
		posting_datetime = entry.get('posting_datetime') if isinstance(entry, dict) else entry.posting_datetime
		voucher_no = entry.get('voucher_no') if isinstance(entry, dict) else entry.voucher_no

		# Convert posting_datetime string to datetime if needed
		if isinstance(posting_datetime, str):
			posting_datetime = get_datetime(posting_datetime)

		if voucher_type == "Stock Reconciliation" and (not batch_no or serial_no):
			qty_diff = flt(qty_after_transaction) - flt(qty_dict.bal_qty)
		else:
			qty_diff = flt(actual_qty)

		value_diff = flt(stock_value_difference)

		if posting_datetime < self.from_datetime or voucher_no in self.opening_vouchers.get(
			voucher_type, []
		):
			qty_dict.opening_qty += qty_diff
			qty_dict.opening_val += value_diff

		elif posting_datetime >= self.from_datetime and posting_datetime <= self.to_datetime:
			if flt(qty_diff, self.float_precision) >= 0:
				qty_dict.in_qty += qty_diff
			else:
				qty_dict.out_qty += abs(qty_diff)

			if flt(value_diff, self.float_precision) >= 0:
				qty_dict.in_val += value_diff
			else:
				qty_dict.out_val += abs(value_diff)

		qty_dict.val_rate = valuation_rate
		qty_dict.bal_qty += qty_diff
		qty_dict.bal_val += value_diff

	def initialize_data(self, item_warehouse_map, group_by_key, entry):
		opening_data = self.opening_data.get(group_by_key, {})

		# Get values using dictionary access for both dict and object entries
		item_code = entry.get('item_code') if isinstance(entry, dict) else entry.item_code
		warehouse = entry.get('warehouse') if isinstance(entry, dict) else entry.warehouse
		item_group = entry.get('item_group') if isinstance(entry, dict) else entry.item_group
		company = entry.get('company') if isinstance(entry, dict) else entry.company
		stock_uom = entry.get('stock_uom') if isinstance(entry, dict) else entry.stock_uom
		item_name = entry.get('item_name') if isinstance(entry, dict) else entry.item_name

		item_warehouse_map[group_by_key] = frappe._dict(
			{
				"item_code": item_code,
				"warehouse": warehouse,
				"item_group": item_group,
				"company": company,
				"currency": self.company_currency,
				"stock_uom": stock_uom,
				"item_name": item_name,
				"opening_qty": opening_data.get("bal_qty") or 0.0,
				"opening_val": opening_data.get("bal_val") or 0.0,
				"opening_fifo_queue": opening_data.get("fifo_queue") or [],
				"in_qty": 0.0,
				"in_val": 0.0,
				"out_qty": 0.0,
				"out_val": 0.0,
				"bal_qty": opening_data.get("bal_qty") or 0.0,
				"bal_val": opening_data.get("bal_val") or 0.0,
				"val_rate": 0.0,
			}
		)

	def get_group_by_key(self, row) -> tuple:
		# Handle both dictionary and object access
		company = row.get('company') if isinstance(row, dict) else row.company
		item_code = row.get('item_code') if isinstance(row, dict) else row.item_code
		warehouse = row.get('warehouse') if isinstance(row, dict) else row.warehouse
		
		group_by_key = [company, item_code, warehouse]

		for fieldname in self.inventory_dimensions:
			field_value = row.get(fieldname) if isinstance(row, dict) else getattr(row, fieldname, None)
			if not field_value:
				continue

			if self.filters.get(fieldname) or self.filters.get("show_dimension_wise_stock"):
				group_by_key.append(field_value)

		return tuple(group_by_key)

	def get_closing_balance(self) -> list[dict[str, Any]]:
		if self.filters.get("ignore_closing_balance"):
			return []

		table = frappe.qb.DocType("Closing Stock Balance")

		query = (
			frappe.qb.from_(table)
			.select(table.name, table.to_date)
			.where(
				(table.docstatus == 1)
				& (table.company == self.filters.company)
				& (table.to_date <= self.from_date)
				& (table.status == "Completed")
			)
			.orderby(table.to_date, order=Order.desc)
			.limit(1)
		)

		for fieldname in ["warehouse", "item_code", "item_group", "warehouse_type"]:
			if value := self.filters.get(fieldname):
				if isinstance(value, list | tuple):
					query = query.where(table[fieldname].isin(value))
				else:
					query = query.where(table[fieldname] == value)

		return query.run(as_dict=True)

	def prepare_stock_ledger_entries(self):
		sle = frappe.qb.DocType("Stock Ledger Entry")
		item_table = frappe.qb.DocType("Item")

		# Regular SLE entries
		query = (
			frappe.qb.from_(sle)
			.inner_join(item_table)
			.on(sle.item_code == item_table.name)
			.select(
				sle.item_code,
				sle.warehouse,
				sle.posting_datetime,
				sle.actual_qty,
				sle.valuation_rate,
				sle.company,
				sle.voucher_type,
				sle.qty_after_transaction,
				sle.stock_value_difference,
				sle.item_code.as_("name"),
				sle.voucher_no,
				sle.stock_value,
				sle.batch_no,
				sle.serial_no,
				sle.serial_and_batch_bundle,
				sle.has_serial_no,
				item_table.item_group,
				item_table.stock_uom,
				item_table.item_name,
			)
			.where((sle.docstatus < 2) & (sle.is_cancelled == 0))
			.orderby(sle.posting_datetime)
			.orderby(sle.creation)
		)

		query = self.apply_inventory_dimensions_filters(query, sle)
		query = self.apply_warehouse_filters(query, sle)
		query = self.apply_items_filters(query, item_table)
		query = self.apply_date_filters(query, sle)

		if self.filters.get("company"):
			query = query.where(sle.company == self.filters.get("company"))

		self.sle_query = query

	def apply_inventory_dimensions_filters(self, query, sle) -> str:
		inventory_dimension_fields = self.get_inventory_dimension_fields()
		if inventory_dimension_fields:
			for fieldname in inventory_dimension_fields:
				query = query.select(fieldname)
				if self.filters.get(fieldname):
					query = query.where(sle[fieldname].isin(self.filters.get(fieldname)))

		return query

	def apply_warehouse_filters(self, query, sle) -> str:
		warehouse_table = frappe.qb.DocType("Warehouse")

		if self.filters.get("warehouse"):
			query = apply_warehouse_filter(query, sle, self.filters)

		elif warehouse_type := self.filters.get("warehouse_type"):
			query = (
				query.join(warehouse_table)
				.on(warehouse_table.name == sle.warehouse)
				.where(warehouse_table.warehouse_type == warehouse_type)
			)

		return query

	def apply_items_filters(self, query, item_table) -> str:
		if item_group := self.filters.get("item_group"):
			children = get_descendants_of("Item Group", item_group, ignore_permissions=True)
			query = query.where(item_table.item_group.isin([*children, item_group]))

		if item_codes := self.filters.get("item_code"):
			query = query.where(item_table.name.isin(item_codes))

		if brand := self.filters.get("brand"):
			query = query.where(item_table.brand == brand)

		return query

	def apply_date_filters(self, query, sle):
		if not self.filters.get("ignore_closing_balance") and self.start_from:
			query = query.where(sle.posting_datetime >= self.start_from)

		if self.to_datetime:
			query = query.where(sle.posting_datetime <= self.to_datetime)

		return query

	def get_columns(self):
		columns = [
			{
				"label": _("Item"),
				"fieldname": "item_code",
				"fieldtype": "Link",
				"options": "Item",
				"width": 100,
			},
			{"label": _("Item Name"), "fieldname": "item_name", "width": 150},
			{
				"label": _("Item Group"),
				"fieldname": "item_group",
				"fieldtype": "Link",
				"options": "Item Group",
				"width": 100,
			},
			{
				"label": _("Warehouse"),
				"fieldname": "warehouse",
				"fieldtype": "Link",
				"options": "Warehouse",
				"width": 100,
			},
		]

		if self.filters.get("show_dimension_wise_stock"):
			for dimension in get_inventory_dimensions():
				columns.append(
					{
						"label": _(dimension.doctype),
						"fieldname": dimension.fieldname,
						"fieldtype": "Link",
						"options": dimension.doctype,
						"width": 110,
					}
				)

		columns.extend(
			[
				{
					"label": _("Stock UOM"),
					"fieldname": "stock_uom",
					"fieldtype": "Link",
					"options": "UOM",
					"width": 90,
				},
				{
					"label": _("Balance Qty"),
					"fieldname": "bal_qty",
					"fieldtype": "Float",
					"width": 100,
					"convertible": "qty",
				},
				{
					"label": _("Balance Value"),
					"fieldname": "bal_val",
					"fieldtype": "Currency",
					"width": 100,
					"options": "Company:company:default_currency",
				},
				{
					"label": _("Opening Qty"),
					"fieldname": "opening_qty",
					"fieldtype": "Float",
					"width": 100,
					"convertible": "qty",
				},
				{
					"label": _("Opening Value"),
					"fieldname": "opening_val",
					"fieldtype": "Currency",
					"width": 110,
					"options": "Company:company:default_currency",
				},
				{
					"label": _("In Qty"),
					"fieldname": "in_qty",
					"fieldtype": "Float",
					"width": 80,
					"convertible": "qty",
				},
				{"label": _("In Value"), "fieldname": "in_val", "fieldtype": "Float", "width": 80},
				{
					"label": _("Out Qty"),
					"fieldname": "out_qty",
					"fieldtype": "Float",
					"width": 80,
					"convertible": "qty",
				},
				{"label": _("Out Value"), "fieldname": "out_val", "fieldtype": "Float", "width": 80},
				{
					"label": _("Valuation Rate"),
					"fieldname": "val_rate",
					"fieldtype": self.filters.valuation_field_type or "Currency",
					"width": 90,
					"convertible": "rate",
					"options": "Company:company:default_currency"
					if self.filters.valuation_field_type == "Currency"
					else None,
				},
				{
					"label": _("Reserved Stock"),
					"fieldname": "reserved_stock",
					"fieldtype": "Float",
					"width": 80,
					"convertible": "qty",
				},
				{
					"label": _("Company"),
					"fieldname": "company",
					"fieldtype": "Link",
					"options": "Company",
					"width": 100,
				},
			]
		)

		if self.filters.get("show_stock_ageing_data"):
			columns += [
				{"label": _("Average Age"), "fieldname": "average_age", "width": 100},
				{"label": _("Earliest Age"), "fieldname": "earliest_age", "width": 100},
				{"label": _("Latest Age"), "fieldname": "latest_age", "width": 100},
			]

		if self.filters.get("show_variant_attributes"):
			columns += [
				{"label": att_name, "fieldname": att_name, "width": 100}
				for att_name in get_variants_attributes()
			]

		return columns

	def add_additional_uom_columns(self):
		if not self.filters.get("include_uom"):
			return

		conversion_factors = self.get_itemwise_conversion_factor()
		add_additional_uom_columns(self.columns, self.data, self.filters.include_uom, conversion_factors)

	def get_itemwise_conversion_factor(self):
		items = []
		if self.filters.item_code or self.filters.item_group:
			items = [d.item_code for d in self.data]

		table = frappe.qb.DocType("UOM Conversion Detail")
		query = (
			frappe.qb.from_(table)
			.select(
				table.conversion_factor,
				table.parent,
			)
			.where((table.parenttype == "Item") & (table.uom == self.filters.include_uom))
		)

		if items:
			query = query.where(table.parent.isin(items))

		result = query.run(as_dict=1)
		if not result:
			return {}

		return {d.parent: d.conversion_factor for d in result}

	def get_variant_values_for(self):
		"""Returns variant values for items."""
		attribute_map = {}
		items = []
		if self.filters.item_code or self.filters.item_group:
			items = [d.item_code for d in self.data]

		filters = {}
		if items:
			filters = {"parent": ("in", items)}

		attribute_info = frappe.get_all(
			"Item Variant Attribute",
			fields=["parent", "attribute", "attribute_value"],
			filters=filters,
		)

		for attr in attribute_info:
			attribute_map.setdefault(attr["parent"], {})
			attribute_map[attr["parent"]].update({attr["attribute"]: attr["attribute_value"]})

		return attribute_map

	def get_opening_vouchers(self):
		opening_vouchers = {"Stock Entry": [], "Stock Reconciliation": []}

		se = frappe.qb.DocType("Stock Entry")
		sr = frappe.qb.DocType("Stock Reconciliation")

		se_datetime = Concat(se.posting_date, " ", se.posting_time)
		sr_datetime = Concat(sr.posting_date, " ", sr.posting_time)

		# Stock Entry
		se_data = (
			frappe.qb.from_(se)
			.select(se.name)
			.where(
				(se.docstatus == 1)
				& (se.is_opening == "Yes")
				& (se_datetime <= self.to_datetime)
			)
		).run(as_dict=True)

		for d in se_data or []:
			opening_vouchers["Stock Entry"].append(d.name)

		# Stock Reconciliation
		sr_data = (
			frappe.qb.from_(sr)
			.select(sr.name)
			.where(
				(sr.docstatus == 1)
				& (sr.purpose == "Opening Stock")
				& (sr_datetime <= self.to_datetime)
			)
		).run(as_dict=True)

		for d in sr_data or []:
			opening_vouchers["Stock Reconciliation"].append(d.name)

		return opening_vouchers

	@staticmethod
	def get_inventory_dimension_fields():
		return [dimension.fieldname for dimension in get_inventory_dimensions()]

	@staticmethod
	def get_opening_fifo_queue(report_data):
		opening_fifo_queue = report_data.get("opening_fifo_queue") or []
		for row in opening_fifo_queue:
			row[1] = getdate(row[1])

		return opening_fifo_queue


def filter_items_with_no_transactions(
	iwb_map, float_precision: float, inventory_dimensions: list | None = None
):
	pop_keys = []
	for group_by_key in iwb_map:
		qty_dict = iwb_map[group_by_key]

		no_transactions = True
		for key, val in qty_dict.items():
			if inventory_dimensions and key in inventory_dimensions:
				continue

			if key in [
				"item_code",
				"warehouse",
				"item_name",
				"item_group",
				"project",
				"stock_uom",
				"company",
				"opening_fifo_queue",
			]:
				continue

			val = flt(val, float_precision)
			qty_dict[key] = val
			if key != "val_rate" and val:
				no_transactions = False

		if no_transactions:
			pop_keys.append(group_by_key)

	for key in pop_keys:
		iwb_map.pop(key)

	return iwb_map


def get_variants_attributes() -> list[str]:
	"""Return all item variant attributes."""
	return frappe.get_all("Item Attribute", pluck="name")