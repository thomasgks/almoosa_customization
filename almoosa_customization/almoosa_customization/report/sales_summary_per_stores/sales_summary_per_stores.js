// Copyright (c) 2026, Printechs and contributors
// For license information, please see license.txt

frappe.query_reports["Sales Summary Per Stores"] = {
	"filters": [
		{
      "fieldname": "from_datetime",
      "label": "From Date & Time",
      "fieldtype": "Datetime",
      "default": frappe.datetime.month_start() + " 00:00:01",
    },
    {
      "fieldname": "to_datetime",
      "label": "To Date & Time",
      "fieldtype": "Datetime",
      "default": frappe.datetime.month_end() + " 23:59:59"
    },
    {
			"fieldname": "warehouse",
			"label": __("Warehouse"),
			"fieldtype": "MultiSelectList",
			"options": "Warehouse",
			get_data: function (txt) {
				return frappe.db.get_link_options("Warehouse", txt);
			}
	},
	{
			"fieldname": "cost_center",
			"label": __("Cost Center"),
			"fieldtype": "MultiSelectList",
			"options": "Cost Center",
			get_data: function (txt) {
				return frappe.db.get_link_options("Cost Center", txt);
			}
	},

	],
	
	"formatter": function (value, row, column, data, default_formatter) {

	value = default_formatter(value, row, column, data);

	
	if (data && data.warehouse === "Total") {

		value = $(`<span>${value}</span>`);
		var $value = $(value).css({
			"font-weight": "bold"
		});

		return $value.wrap("<p></p>").parent().html();
	}

	return value;
	},
};
