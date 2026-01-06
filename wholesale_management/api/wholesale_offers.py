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
        calculate_wholesale_qty
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
        # Calculate par level (average monthly sales)
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
        
        # Only include items with wholesale quantity available
        if wholesale_qty > 0:
            results.append({
                'brand': item.brand or '',
                'item_code': item.item_code,
                'item_name': item.item_name,
                'item_group': item.item_group or '',
                'wholesale_qty': round(wholesale_qty, 0),
                'last_offer_price': item.last_offer_price or 'MO',
                'qty_available': item.qty_available,
                'on_hold': on_hold,
                'par_level': round(par_level, 2),
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


@frappe.whitelist()
def update_offer_prices(items_data):
    """
    Update custom_wholesale_offer_price for multiple items
    
    Args:
        items_data (str): JSON string of list with [{item_code: '', offer_price: ''}]
    
    Returns:
        dict: Success status and count
    """
    import json
    
    if isinstance(items_data, str):
        items_data = json.loads(items_data)
    
    updated_count = 0
    errors = []
    
    for item in items_data:
        try:
            item_code = item.get('item_code')
            offer_price = item.get('offer_price')
            
            if not item_code:
                continue
                
            frappe.db.set_value('Item', item_code, 'custom_wholesale_offer_price', offer_price)
            updated_count += 1
            
        except Exception as e:
            errors.append({
                'item_code': item_code,
                'error': str(e)
            })
    
    frappe.db.commit()
    
    return {
        'success': True,
        'updated_count': updated_count,
        'errors': errors
    }


@frappe.whitelist()
def get_available_warehouses():
    """
    Get list of all active warehouses
    Useful for dropdown/selection in Google Sheets or UI
    
    Returns:
        list: Active warehouse names
    """
    
    query = """
        SELECT name, warehouse_name
        FROM `tabWarehouse`
        WHERE disabled = 0
        ORDER BY name
    """
    
    warehouses = frappe.db.sql(query, as_dict=True)
    
    return {
        'warehouses': warehouses,
        'count': len(warehouses)
    }


@frappe.whitelist()
def get_item_wholesale_detail(item_code, warehouse="Stores - SURGI"):
    """
    Get detailed wholesale calculation for a single item
    Useful for debugging or detailed view
    
    Args:
        item_code (str): Item code to analyze
        warehouse (str): Warehouse to check
    
    Returns:
        dict: Detailed breakdown of wholesale calculation
    """
    
    from wholesale_management.utils.calculations import (
        calculate_par_level,
        calculate_on_hold_qty,
        get_item_sales_history
    )
    
    # Get item info
    item = frappe.get_doc('Item', item_code)
    
    # Get inventory in specified warehouse
    bin_data = frappe.db.get_value(
        'Bin',
        {'item_code': item_code, 'warehouse': warehouse},
        ['actual_qty', 'reserved_qty', 'ordered_qty', 'planned_qty'],
        as_dict=True
    )
    
    qty_available = bin_data.actual_qty if bin_data else 0
    
    # Calculate metrics
    lookback_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    par_level = calculate_par_level(item_code, lookback_date)
    on_hold = calculate_on_hold_qty(item_code)
    sales_history = get_item_sales_history(item_code, months=12)
    
    # Calculate wholesale qty
    months_par = 6
    buffer_percent = 10
    par_with_buffer = (par_level * months_par) * (1 + buffer_percent / 100)
    wholesale_qty = max(0, qty_available - on_hold - par_with_buffer)
    
    return {
        'item_code': item_code,
        'item_name': item.item_name,
        'brand': item.brand,
        'warehouse': warehouse,
        'inventory': {
            'actual_qty': qty_available,
            'reserved_qty': bin_data.reserved_qty if bin_data else 0,
            'ordered_qty': bin_data.ordered_qty if bin_data else 0,
        },
        'calculations': {
            'par_level_monthly': round(par_level, 2),
            'par_months': months_par,
            'par_total': round(par_level * months_par, 2),
            'buffer_percent': buffer_percent,
            'par_with_buffer': round(par_with_buffer, 2),
            'on_hold': on_hold,
            'wholesale_available': round(wholesale_qty, 0)
        },
        'sales_history': sales_history,
        'last_offer_price': item.custom_wholesale_offer_price
    }
