// Copyright (c) 2026, Printechs and contributors
// For license information, please see license.txt

frappe.query_reports["Summary Sales By Brand And Group"] = {
	"filters": [
		 {
            "fieldname": "from_datetime",
            "label": "From Date & Time",
            "fieldtype": "Datetime",
            "default": frappe.datetime.month_start() + " 00:00:01"
        },

        {
            "fieldname": "to_datetime",
            "label": "To Date & Time",
            "fieldtype": "Datetime",
            "default": frappe.datetime.month_end() + " 23:59:59"
        },
		{
			"fieldname": "warehouse",
			"label": "Warehouse",
			"fieldtype": "MultiSelectList",
			"options": "Warehouse",
			"get_data": function(txt) {
				return frappe.db.get_link_options("Warehouse", txt);
			}
		},
        {
			"fieldname": "brand",
			"label": "Brand",
			"fieldtype": "MultiSelectList",
			"options": "Brand",
			"get_data": function(txt) {
				return frappe.db.get_link_options("Brand", txt);
			}
		}
    ],
	
	"formatter": function (value, row, column, data, default_formatter) {

        value = default_formatter(value, row, column, data);

        if (!data) {
            return value;
        }

        // ✅ Bold TOTAL column (all rows)
        if (column.fieldname === "total") {
            value = `<span style="font-weight:600;">${value}</span>`;
        }

        // ✅ Bold GRAND TOTAL row
        if (data.item_group === "Grand Total") {
            value = `<span style="font-weight:700;">${value}</span>`;
        }

        return value;
}

};
