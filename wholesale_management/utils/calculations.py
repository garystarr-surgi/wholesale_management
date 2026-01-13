# wholesale_management/wholesale_management/utils/calculations.py

import frappe

def calculate_par_level(item_code, lookback_date):
    """
    Calculate average monthly sales for an item
    
    Args:
        item_code (str): Item code
        lookback_date (str): Start date for calculation (YYYY-MM-DD)
    
    Returns:
        float: Average quantity sold per month
    """
    
    # Calculate number of months in lookback period
    from datetime import datetime
    today = datetime.now()
    lookback = datetime.strptime(lookback_date, '%Y-%m-%d')
    months = (today.year - lookback.year) * 12 + (today.month - lookback.month)
    
    if months == 0:
        months = 1  # Prevent division by zero
    
    query = """
        SELECT COALESCE(SUM(sii.qty), 0) as total_qty
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON sii.parent = si.name
        WHERE sii.item_code = %s
        AND si.docstatus = 1
        AND si.posting_date >= %s
        AND si.is_return = 0
    """
    
    result = frappe.db.sql(query, (item_code, lookback_date), as_dict=True)
    total_qty = result[0].total_qty if result else 0
    
    return total_qty / months


def calculate_on_hold_qty(item_code):
    """
    Calculate quantity on hold from Sales Orders and Quotations
    
    Args:
        item_code (str): Item code
    
    Returns:
        float: Total quantity on hold
    """
    
    # Sales Orders - outstanding quantity
    so_query = """
        SELECT COALESCE(SUM(soi.qty - soi.delivered_qty), 0) as on_hold_so
        FROM `tabSales Order Item` soi
        JOIN `tabSales Order` so ON soi.parent = so.name
        WHERE soi.item_code = %s
        AND so.docstatus = 1
        AND so.status NOT IN ('Closed', 'Completed', 'Cancelled')
        AND (soi.qty - soi.delivered_qty) > 0
    """
    
    so_result = frappe.db.sql(so_query, (item_code,), as_dict=True)
    on_hold_so = so_result[0].on_hold_so if so_result else 0
    
    # Quotations - open quotations
    quot_query = """
        SELECT COALESCE(SUM(qi.qty), 0) as on_hold_quot
        FROM `tabQuotation Item` qi
        JOIN `tabQuotation` q ON qi.parent = q.name
        WHERE qi.item_code = %s
        AND q.docstatus = 1
        AND q.status NOT IN ('Lost', 'Cancelled', 'Ordered')
    """
    
    quot_result = frappe.db.sql(quot_query, (item_code,), as_dict=True)
    on_hold_quot = quot_result[0].on_hold_quot if quot_result else 0
    
    return on_hold_so + on_hold_quot


def calculate_wholesale_qty(qty_available, on_hold, par_level, months_par=6, buffer_percent=10):
    """
    Calculate available quantity for wholesale offers
    
    Formula: Available - On Hold - (Par Level × Months × (1 + Buffer %))
    
    Args:
        qty_available (float): Current inventory quantity
        on_hold (float): Quantity on hold from SO/Quotations
        par_level (float): Average monthly sales
        months_par (int): Number of months of par to maintain
        buffer_percent (float): Additional buffer percentage
    
    Returns:
        float: Quantity available for wholesale (minimum 0)
    """
    
    par_with_buffer = (par_level * months_par) * (1 + buffer_percent / 100)
    wholesale_qty = qty_available - on_hold - par_with_buffer
    
    return max(0, wholesale_qty)


def get_item_sales_history(item_code, months=12):
    """
    Get monthly sales history for an item
    Useful for future analytics/trending
    
    Args:
        item_code (str): Item code
        months (int): Number of months to look back
    
    Returns:
        list: Monthly sales data
    """
    from datetime import datetime, timedelta
    
    start_date = (datetime.now() - timedelta(days=months * 30)).strftime('%Y-%m-%d')
    
    query = """
        SELECT 
            DATE_FORMAT(si.posting_date, '%%Y-%%m') as month,
            SUM(sii.qty) as qty_sold,
            COUNT(DISTINCT si.name) as invoice_count
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON sii.parent = si.name
        WHERE sii.item_code = %s
        AND si.docstatus = 1
        AND si.posting_date >= %s
        AND si.is_return = 0
        GROUP BY DATE_FORMAT(si.posting_date, '%%Y-%%m')
        ORDER BY month DESC
    """
    
    return frappe.db.sql(query, (item_code, start_date), as_dict=True)

# Add this function to your calculations.py file

def calculate_avg_sale_price(item_code, lookback_date):
    """
    Calculate average sales price for an item over specified period
    
    Args:
        item_code (str): Item code
        lookback_date (str): Start date for calculation (YYYY-MM-DD)
    
    Returns:
        float: Average sale price
    """
    
    query = """
        SELECT 
            COALESCE(AVG(sii.rate), 0) as avg_price,
            COALESCE(SUM(sii.qty), 0) as total_qty
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON sii.parent = si.name
        WHERE sii.item_code = %s
        AND si.docstatus = 1
        AND si.posting_date >= %s
        AND si.is_return = 0
        AND sii.qty > 0
    """
    
    result = frappe.db.sql(query, (item_code, lookback_date), as_dict=True)
    
    if result and result[0].total_qty > 0:
        return result[0].avg_price
    return 0


def get_last_purchase_price(item_code):
    """
    Get the last purchase price from most recent Purchase Receipt
    
    Args:
        item_code (str): Item code
    
    Returns:
        float: Last purchase price
    """
    
    query = """
        SELECT pri.rate
        FROM `tabPurchase Receipt Item` pri
        JOIN `tabPurchase Receipt` pr ON pri.parent = pr.name
        WHERE pri.item_code = %s
        AND pr.docstatus = 1
        ORDER BY pr.posting_date DESC, pr.creation DESC
        LIMIT 1
    """
    
    result = frappe.db.sql(query, (item_code,), as_dict=True)
    
    if result:
        return result[0].rate
    return 0
