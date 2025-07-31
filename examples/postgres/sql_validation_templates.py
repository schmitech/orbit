#!/usr/bin/env python3
"""
SQL Validation Templates
========================

This module provides SQL templates that mirror the RAG system's query templates
for accurate validation of results.
"""

from typing import Dict, List, Tuple, Any

class SQLValidationTemplates:
    """
    Contains SQL templates that correspond to RAG system query templates
    """
    
    @staticmethod
    def get_customer_orders_sql(parameters: Dict[str, Any]) -> Tuple[str, List]:
        """SQL for customer-specific order queries"""
        sql = """
            SELECT 
                c.id as customer_id,
                c.name as customer_name,
                c.email as customer_email,
                c.city as customer_city,
                c.country as customer_country,
                o.id as order_id,
                o.order_date,
                o.total,
                o.status,
                o.payment_method,
                o.shipping_address,
                o.created_at
            FROM customers c
            INNER JOIN orders o ON c.id = o.customer_id
            WHERE 1=1
        """
        
        params = []
        
        # Customer ID filter
        if 'customer_id' in parameters:
            sql += " AND c.id = %s"
            params.append(parameters['customer_id'])
        
        # Customer name filter (with ILIKE for partial matching)
        if 'customer_name' in parameters:
            sql += " AND c.name ILIKE %s"
            params.append(f"%{parameters['customer_name']}%")
        
        # Days back filter
        if 'days_back' in parameters:
            sql += " AND o.order_date >= CURRENT_DATE - INTERVAL %s"
            params.append(f"{parameters['days_back']} days")
        
        sql += " ORDER BY o.order_date DESC LIMIT 100"
        return sql, params
    
    @staticmethod
    def get_order_value_filter_sql(parameters: Dict[str, Any]) -> Tuple[str, List]:
        """SQL for order value filtering queries"""
        sql = """
            SELECT 
                c.id as customer_id,
                c.name as customer_name,
                c.email as customer_email,
                c.city as customer_city,
                c.country as customer_country,
                o.id as order_id,
                o.order_date,
                o.total,
                o.status,
                o.payment_method,
                o.shipping_address
            FROM customers c
            INNER JOIN orders o ON c.id = o.customer_id
            WHERE 1=1
        """
        
        params = []
        
        # Min amount filter
        if 'min_total' in parameters:
            sql += " AND o.total >= %s"
            params.append(parameters['min_total'])
        
        # Max amount filter  
        if 'max_total' in parameters:
            sql += " AND o.total <= %s"
            params.append(parameters['max_total'])
        
        # Days back filter
        if 'days_back' in parameters:
            sql += " AND o.order_date >= CURRENT_DATE - INTERVAL %s"
            params.append(f"{parameters['days_back']} days")
        
        sql += " ORDER BY o.order_date DESC LIMIT 100"
        return sql, params
    
    @staticmethod
    def get_order_status_filter_sql(parameters: Dict[str, Any]) -> Tuple[str, List]:
        """SQL for order status filtering queries"""
        sql = """
            SELECT 
                c.id as customer_id,
                c.name as customer_name,
                c.email as customer_email,
                c.city as customer_city,
                c.country as customer_country,
                o.id as order_id,
                o.order_date,
                o.total,
                o.status,
                o.payment_method,
                o.shipping_address
            FROM customers c
            INNER JOIN orders o ON c.id = o.customer_id
            WHERE 1=1
        """
        
        params = []
        
        # Status filter
        if 'status' in parameters:
            sql += " AND o.status = %s"
            params.append(parameters['status'])
        
        # Days back filter
        if 'days_back' in parameters:
            sql += " AND o.order_date >= CURRENT_DATE - INTERVAL %s"
            params.append(f"{parameters['days_back']} days")
        
        sql += " ORDER BY o.order_date DESC LIMIT 100"
        return sql, params
    
    @staticmethod
    def get_location_filter_sql(parameters: Dict[str, Any]) -> Tuple[str, List]:
        """SQL for location-based filtering queries"""
        sql = """
            SELECT 
                c.id as customer_id,
                c.name as customer_name,
                c.email as customer_email,
                c.city as customer_city,
                c.country as customer_country,
                o.id as order_id,
                o.order_date,
                o.total,
                o.status,
                o.payment_method,
                o.shipping_address
            FROM customers c
            INNER JOIN orders o ON c.id = o.customer_id
            WHERE 1=1
        """
        
        params = []
        
        # City filter
        if 'city' in parameters:
            sql += " AND c.city ILIKE %s"
            params.append(f"%{parameters['city']}%")
        
        # Country filter
        if 'country' in parameters:
            sql += " AND c.country ILIKE %s"
            params.append(f"%{parameters['country']}%")
        
        # Days back filter
        if 'days_back' in parameters:
            sql += " AND o.order_date >= CURRENT_DATE - INTERVAL %s"
            params.append(f"{parameters['days_back']} days")
        
        sql += " ORDER BY o.order_date DESC LIMIT 100"
        return sql, params
    
    @staticmethod
    def get_payment_filter_sql(parameters: Dict[str, Any]) -> Tuple[str, List]:
        """SQL for payment method filtering queries"""
        sql = """
            SELECT 
                c.id as customer_id,
                c.name as customer_name,
                c.email as customer_email,
                c.city as customer_city,
                c.country as customer_country,
                o.id as order_id,
                o.order_date,
                o.total,
                o.status,
                o.payment_method,
                o.shipping_address
            FROM customers c
            INNER JOIN orders o ON c.id = o.customer_id
            WHERE 1=1
        """
        
        params = []
        
        # Payment method filter
        if 'payment_method' in parameters:
            sql += " AND o.payment_method = %s"
            params.append(parameters['payment_method'])
        
        # Days back filter
        if 'days_back' in parameters:
            sql += " AND o.order_date >= CURRENT_DATE - INTERVAL %s"
            params.append(f"{parameters['days_back']} days")
        
        sql += " ORDER BY o.order_date DESC LIMIT 100"
        return sql, params
    
    @staticmethod
    def get_customer_summary_sql(parameters: Dict[str, Any]) -> Tuple[str, List]:
        """SQL for customer summary/analytics queries"""
        sql = """
            SELECT 
                c.id as customer_id,
                c.name as customer_name,
                c.email as customer_email,
                c.city as customer_city,
                c.country as customer_country,
                COUNT(o.id) as order_count,
                SUM(o.total) as total_spent,
                AVG(o.total) as avg_order_value,
                MAX(o.total) as max_order_value,
                MIN(o.total) as min_order_value,
                MAX(o.order_date) as last_order_date,
                MIN(o.order_date) as first_order_date
            FROM customers c
            INNER JOIN orders o ON c.id = o.customer_id
            WHERE 1=1
        """
        
        params = []
        
        # Customer ID filter for specific customer summary
        if 'customer_id' in parameters:
            sql += " AND c.id = %s"
            params.append(parameters['customer_id'])
        
        # Days back filter
        if 'days_back' in parameters:
            sql += " AND o.order_date >= CURRENT_DATE - INTERVAL %s"
            params.append(f"{parameters['days_back']} days")
        
        sql += """
            GROUP BY c.id, c.name, c.email, c.city, c.country
            ORDER BY total_spent DESC
            LIMIT 50
        """
        
        return sql, params
    
    @staticmethod
    def get_top_customers_sql(parameters: Dict[str, Any]) -> Tuple[str, List]:
        """SQL for top customers queries"""
        sql = """
            SELECT 
                c.id as customer_id,
                c.name as customer_name,
                c.email as customer_email,
                c.city as customer_city,
                c.country as customer_country,
                COUNT(o.id) as order_count,
                SUM(o.total) as total_spent,
                AVG(o.total) as avg_order_value
            FROM customers c
            INNER JOIN orders o ON c.id = o.customer_id
            WHERE 1=1
        """
        
        params = []
        
        # Days back filter
        if 'days_back' in parameters:
            sql += " AND o.order_date >= CURRENT_DATE - INTERVAL %s"
            params.append(f"{parameters['days_back']} days")
        
        # Get the limit from parameters or default to 10
        limit = parameters.get('limit', 10)
        
        sql += """
            GROUP BY c.id, c.name, c.email, c.city, c.country
            ORDER BY total_spent DESC
            LIMIT %s
        """
        params.append(limit)
        
        return sql, params
    
    @staticmethod
    def get_customers_by_time_period_sql(parameters: Dict[str, Any]) -> Tuple[str, List]:
        """SQL for listing customers who ordered in a time period"""
        sql = """
            SELECT DISTINCT c.id as customer_id, c.name as customer_name, c.email as customer_email,
                   c.city as customer_city, c.country as customer_country,
                   COUNT(o.id) as order_count,
                   SUM(o.total) as total_spent,
                   MAX(o.order_date) as last_order_date,
                   MIN(o.order_date) as first_order_date
            FROM customers c
            JOIN orders o ON c.id = o.customer_id
            WHERE 1=1
        """
        
        params = []
        
        # Days back filter
        if 'days_back' in parameters:
            sql += " AND o.order_date >= CURRENT_DATE - INTERVAL %s"
            params.append(f"{parameters['days_back']} days")
        
        sql += """
            GROUP BY c.id, c.name, c.email, c.city, c.country
            ORDER BY last_order_date DESC, total_spent DESC
            LIMIT 100
        """
        
        return sql, params
    
    @staticmethod
    def get_template_sql(template_id: str, parameters: Dict[str, Any]) -> Tuple[str, List]:
        """
        Get appropriate SQL based on template ID and parameters
        """
        template_id_lower = template_id.lower()
        
        # Customer-related templates
        if 'customer' in template_id_lower and ('by_id' in template_id_lower or 'customer_id' in parameters):
            return SQLValidationTemplates.get_customer_orders_sql(parameters)
        
        # Order value templates
        elif 'filter' in template_id_lower and ('total' in template_id_lower or 'range' in template_id_lower):
            return SQLValidationTemplates.get_order_value_filter_sql(parameters)
        
        # Order status templates
        elif 'status' in template_id_lower or 'filter' in template_id_lower and 'status' in parameters:
            return SQLValidationTemplates.get_order_status_filter_sql(parameters)
        
        # Location templates
        elif 'city' in template_id_lower or 'country' in template_id_lower or 'location' in template_id_lower:
            return SQLValidationTemplates.get_location_filter_sql(parameters)
        
        # Payment method templates
        elif 'payment' in template_id_lower:
            return SQLValidationTemplates.get_payment_filter_sql(parameters)
        
        # Summary/analytics templates
        elif 'summary' in template_id_lower or 'calculate' in template_id_lower:
            return SQLValidationTemplates.get_customer_summary_sql(parameters)
        
        # Top customers templates
        elif 'top' in template_id_lower or 'rank' in template_id_lower:
            return SQLValidationTemplates.get_top_customers_sql(parameters)
        
        # Customers by time period templates  
        elif 'list_customers_by_time_period' in template_id_lower or ('customer' in template_id_lower and 'time_period' in template_id_lower):
            return SQLValidationTemplates.get_customers_by_time_period_sql(parameters)
        
        # Default to customer orders
        else:
            return SQLValidationTemplates.get_customer_orders_sql(parameters)