# wholesale_management/wholesale_management/api/wholesale_offers.py

import frappe
from frappe import _
from datetime import datetime, timedelta

@frappe.whitelist()
def get_wholesale_availability(months_lookback=3, months_par=6, buffer_percent=10, warehouse="Stores - SURGI"):
    """
    Calculate wholesale availability for all items based on:
    - Current inventory in specified warehouse only
    - On hold quantities (SO + Quotations)
    - Par level (average monthly sales * months_par + buffer)
    
    Args:
        months_lookback (int): Number of months to calculate average sales (default: 3)
        months_par (int): Number of months of par to maintain (default: 6)
        buffer_percent (int): Additional buffer percentage (default: 10)
        warehouse (str): Warehouse to check inventory (default: 'Stores - SURGI')
    
    Returns:
        list: Wholesale offer data for all eligible items
    """
    
    from wholesale_management.utils.calculations import (
        calculate_par_level,
        calculate_on_hold_qty,
        calculate_wholesale_qty,
        calculate_avg_sale_price,
        get_last_purchase_price
    )
    
    # Validate parameters
    months_lookback = int(months_lookback)
    months_par = int(months_par)
    buffer_percent = float(buffer_percent)
    
    # Get date range for average calculation
    lookback_date = (datetime.now() - timedelta(days=months_lookback * 30)).strftime('%Y-%m-%d')
    
    # Main query - FILTER BY SPECIFIED WAREHOUSE ONLY
    query = """
        SELECT 
            i.name as item_code,
            i.item_name,
            i.brand,
            i.item_group,
            i.custom_wholesale_offer_price as last_offer_price,
            COALESCE(SUM(bin.actual_qty), 0) as qty_available
        FROM `tabItem` i
        INNER JOIN `tabBin` bin ON bin.item_code = i.name
        WHERE i.disabled = 0
        AND i.is_stock_item = 1
        AND bin.warehouse = %s
        GROUP BY i.name
        HAVING qty_available > 0
        ORDER BY i.brand, i.item_name
    """
    
    items = frappe.db.sql(query, (warehouse,), as_dict=True)
    
    results = []
    
    for item in items:
        # Calculate par level (average monthly sales over 3 months)
        par_level = calculate_par_level(
            item_code=item.item_code,
            lookback_date=lookback_date
        )
        
        # Calculate on hold quantity
        on_hold = calculate_on_hold_qty(item_code=item.item_code)
        
        # Calculate wholesale available quantity
        wholesale_qty = calculate_wholesale_qty(
            qty_available=item.qty_available,
            on_hold=on_hold,
            par_level=par_level,
            months_par=months_par,
            buffer_percent=buffer_percent
        )
        
        # Calculate average sale price over last 3 months
        avg_sale_price = calculate_avg_sale_price(
            item_code=item.item_code,
            lookback_date=lookback_date
        )
        
        # Get last purchase price
        cost = get_last_purchase_price(item_code=item.item_code)
        
        # Include ALL items with inventory, even if wholesale_qty is 0 or negative
        results.append({
            'brand': item.brand or '',
            'item_code': item.item_code,
            'item_name': item.item_name,
            'item_group': item.item_group or '',
            'wholesale_qty': round(wholesale_qty, 0),  # Can be 0 or negative
            'last_offer_price': item.last_offer_price or 'MO',
            'qty_available': item.qty_available,
            'on_hold': on_hold,
            'par_level': round(par_level, 2),  # 3 month average
            'avg_sale_price': round(avg_sale_price, 2),
            'lowest_offer': None,  # Placeholder for future calculation
            'cost': round(cost, 2),
            'par_months': months_par,
            'buffer_percent': buffer_percent
        })
    
    frappe.response['message'] = {
        'data': results,
        'summary': {
            'total_items': len(results),
            'warehouse': warehouse,
            'generated_at': datetime.now().isoformat(),
            'parameters': {
                'months_lookback': months_lookback,
                'months_par': months_par,
                'buffer_percent': buffer_percent
            }
        }
    }
    
    return frappe.response['message']
