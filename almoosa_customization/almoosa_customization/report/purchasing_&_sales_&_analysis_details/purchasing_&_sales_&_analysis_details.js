// Copyright (c) 2026, Printechs and contributors
// For license information, please see license.txt

frappe.query_reports["Purchasing & Sales & Analysis Details"] = {
	filters: [
        {
            fieldname: "from_datetime",
            label: "From Date / Time",
            fieldtype: "Datetime",
            reqd: 1
        },
        {
            fieldname: "to_datetime",
            label: "To Date / Time",
            fieldtype: "Datetime",
            reqd: 1
        },
        {
            fieldname: "vendor_code",
            label: "Vendor Code",
            fieldtype: "MultiSelectList",
            get_data: txt => frappe.db.get_link_options("Brand", txt)
        },
        {
            fieldname: "supplier",
            label: "Supplier",
            fieldtype: "MultiSelectList",
            get_data: txt => frappe.db.get_link_options("Supplier", txt)
        },
        {
            fieldname: "item_group",
            label: "Item Group",
            fieldtype: "MultiSelectList",
            get_data: txt => frappe.db.get_link_options("Item Group", txt)
        },        
        {
    fieldname: "year",
    label: "Year",
    fieldtype: "MultiSelectList",
    get_data: function(txt) {
        return frappe.db.get_list("Item", {
            fields: ["distinct custom_year"],
            filters: {
                "custom_year": ["is", "set"]
            },
            limit: 0
        }).then(r => {
            return r.map(d => ({
                value: d.custom_year,
                label: d.custom_year,
                description: ""
            }));
        });
    }
},
        {
            "fieldname": "include_zero_stock",
            "label": "Include Zero Stock Items",
            "fieldtype": "Check",
            "default": 0
        }
        
    ]
};
