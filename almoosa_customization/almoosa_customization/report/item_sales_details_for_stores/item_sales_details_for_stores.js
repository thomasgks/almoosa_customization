// Copyright (c) 2026, Printechs and contributors
// For license information, please see license.txt

frappe.query_reports["Item Sales Details for Stores"] = {
	"filters": [
        {
            fieldname: "from_datetime",
            label: "From Date / Time",
            fieldtype: "Datetime",
            reqd: 1,
            default: (() => {
                // Get datetime 7 days ago
                let d = frappe.datetime.add_days(frappe.datetime.now_date(), -7);
                return d + " 00:00:00";
            })()
        },
        {
            fieldname: "to_datetime",
            label: "To Date / Time",
            fieldtype: "Datetime",
            reqd: 1,
            default: (() => {
                let d = frappe.datetime.now_date();
                return d + " 23:59:59";
            })()
        },
        {
            fieldname: "vendor_code",
            label: "Vendor Code",
            fieldtype: "MultiSelectList",
            get_data: function(txt) {
                return frappe.db.get_link_options("Brand", txt);
            }
        },
        {
            fieldname: "supplier",
            label: "Supplier",
            fieldtype: "MultiSelectList",
            get_data: function(txt) {
                return frappe.db.get_link_options("Supplier", txt);
            }
        },
        {
    fieldname: "item_group_filter",
    label: "Item Group",
    fieldtype: "MultiSelectList",
    get_data: function (txt) {
        return new Promise(resolve => {
            frappe.call({
                method: "frappe.client.get_list",
                args: {
                    doctype: "Item Group",
                    fields: ["name"],
                    limit_page_length: 5000
                },
                callback: function(r) {
                    let rows = r.message || [];
                    let search = txt.toLowerCase();

                    // Filter + sort logic
                    let filtered = rows
                        .filter(d => d.name.toLowerCase().includes(search))
                        .map(d => ({
                            value: d.name,
                            label: d.name,
                            description: d.name
                        }))
                        .sort((a, b) => {
                            const aName = a.value.toLowerCase();
                            const bName = b.value.toLowerCase();

                            // 1. Exact match first
                            if (aName === search) return -1;
                            if (bName === search) return 1;

                            // 2. Starts-with matches next
                            const aStarts = aName.startsWith(search);
                            const bStarts = bName.startsWith(search);
                            if (aStarts && !bStarts) return -1;
                            if (!aStarts && bStarts) return 1;

                            // 3. Alphabetical fallback
                            return aName.localeCompare(bName);
                        });

                    resolve(filtered);
                }
            });
        });
    }
},

        {
            fieldname: "item_code",
            label: "Items",
            fieldtype: "MultiSelectList",
            get_data: function(txt) {
                return frappe.db.get_link_options("Item", txt);
            }
        },
        {
    fieldname: "warehouse",
    label: "Location",
    fieldtype: "MultiSelectList",
    get_data: function(txt) {
        // Use custom method to get only allowed warehouses for current user
        return frappe.call({
            method: "almoosa_customization.almoosa_customization.report.item_sales_details_for_stores.item_sales_details_for_stores.get_allowed_warehouses",
            args: { txt: txt }
        }).then(r => r.message || []);
    }
} 
    ]
};
