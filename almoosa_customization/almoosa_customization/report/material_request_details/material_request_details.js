// Copyright (c) 2026, Printechs and contributors
// For license information, please see license.txt

// Copyright (c) 2026, Printechs and contributors
// For license information, please see license.txt

frappe.query_reports["Material Request Details"] = {
    "filters": [
        {
            "fieldname": "from_datetime",
            "label": __("From Date / Time"),
            "fieldtype": "Datetime",
            "default": frappe.datetime.now_datetime(),
            "reqd": 1
        },
        {
            "fieldname": "to_datetime",
            "label": __("To Date / Time"),
            "fieldtype": "Datetime",
            "default": frappe.datetime.now_datetime(),
            "reqd": 1
        },
        {
            "fieldname": "material_request_no",
            "label": __("Material Request No"),
            "fieldtype": "MultiSelectList",
            "options": "Material Request",
            "get_data": function(txt) {
                return frappe.db.get_link_options("Material Request", txt);
            }
        },
        {
            "fieldname": "source_warehouse",
            "label": __("Source WH"),
            "fieldtype": "MultiSelectList",
            "options": "Warehouse",
            "get_data": function(txt) {
                return frappe.db.get_link_options("Warehouse", txt);
            }
        },
        {
            "fieldname": "created_user",
            "label": __("Created User"),
            "fieldtype": "MultiSelectList",
            "options": "User",
            "get_data": function(txt) {
                return frappe.db.get_link_options("User", txt, {
                    filters: {
                        "user_type": "System User"
                    }
                });
            }
        },
        {
            "fieldname": "items",
            "label": __("Items"),
            "fieldtype": "MultiSelectList",
            "options": "Item",
            "get_data": function(txt) {
                return frappe.db.get_link_options("Item", txt);
            }
        },
        {
            "fieldname": "status",
            "label": __("Status"),
            "fieldtype": "MultiSelectList",
            "options": [
                { "value": "Draft", "description": "Draft" },
                { "value": "Pending", "description": "Pending" },
                { "value": "Intransit", "description": "Intransit" },
                { "value": "Partially Ordered", "description": "Partially Ordered" },
                { "value": "Completed", "description": "Completed" }
            ],
            "get_data": function(txt) {
                let statuses = [
                    { "value": "Draft", "description": "Draft" },
                    { "value": "Pending", "description": "Pending" },
                    { "value": "Intransit", "description": "Intransit" },
                    { "value": "Partially Ordered", "description": "Partially Ordered" },
                    { "value": "Completed", "description": "Completed" }
                ];
                return statuses.filter(s => 
                    s.value.toLowerCase().includes(txt.toLowerCase())
                );
            }
        }
    ],

    "formatter": function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        
        // Color coding for percentage completion
        if (column.fieldname == "per_percentage" && data) {
            let percentage = parseFloat(data.per_percentage) || 0;
            if (percentage >= 100) {
                value = `<span style="color: green; font-weight: bold;">${value}</span>`;
            } else if (percentage >= 50) {
                value = `<span style="color: orange; font-weight: bold;">${value}</span>`;
            } else if (percentage > 0) {
                value = `<span style="color: red; font-weight: bold;">${value}</span>`;
            }
        }
        
        // Highlight negative differences
        if (column.fieldname == "difference" && data && data.difference < 0) {
            value = `<span style="color: red;">${value}</span>`;
        }
        
        // Status color coding
        if (column.fieldname == "status" && data) {
            let status_colors = {
                "Draft": "gray",
                "Pending": "orange",
                "Intransit": "blue",
                "Partially Ordered": "purple",
                "Completed": "green"
            };
            let color = status_colors[data.status] || "black";
            value = `<span style="color: ${color}; font-weight: bold;">${value}</span>`;
        }
        
        return value;
    },

    "tree": false,
    "initial_depth": 0
};