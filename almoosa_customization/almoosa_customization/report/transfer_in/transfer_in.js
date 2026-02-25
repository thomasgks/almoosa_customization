// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["Transfer IN"] = {
    filters: [
        {
            fieldname: "from_datetime",
            label: "From Date / Time",
            fieldtype: "Datetime",
            reqd: 1,
            default: (() => {
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
            get_data: txt => frappe.db.get_link_options("Brand", txt)
        },
        {
            fieldname: "supplier",
            label: "Supplier",
            fieldtype: "MultiSelectList",
            get_data: txt => frappe.db.get_link_options("Supplier", txt)
        },

        // 🔒 EXACT SAME Item Group logic – NOT MODIFIED
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

                                    if (aName === search) return -1;
                                    if (bName === search) return 1;

                                    const aStarts = aName.startsWith(search);
                                    const bStarts = bName.startsWith(search);
                                    if (aStarts && !bStarts) return -1;
                                    if (!aStarts && bStarts) return 1;

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
            get_data: txt => frappe.db.get_link_options("Item", txt)
        },

        // ✅ Target warehouse FIRST
        {
            fieldname: "target_warehouse",
            label: "Target Warehouse",
            fieldtype: "Link",
            options: "Warehouse"
        },

        // ✅ Source warehouse SECOND (from outgoing stock entry)
        {
            fieldname: "source_warehouse",
            label: "Source Warehouse",
            fieldtype: "MultiSelectList",
            get_data: txt => frappe.db.get_link_options("Warehouse", txt)
        }
    ]
};

