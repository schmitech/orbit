#!/usr/bin/env python3
"""
Example Plugins for RAG System
==============================

This module contains example plugins that demonstrate how to extend the RAG system
with custom functionality for different use cases.
"""

import re
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from plugin_system import BaseRAGPlugin, PluginContext, PluginPriority

logger = logging.getLogger(__name__)


class CustomerSegmentationPlugin(BaseRAGPlugin):
    """Plugin for customer segmentation and analysis"""
    
    def __init__(self):
        super().__init__("CustomerSegmentation", "1.0.0", PluginPriority.NORMAL)
        
        # Define customer segments
        self.segments = {
            'vip': {'min_orders': 10, 'min_total': 5000},
            'regular': {'min_orders': 3, 'min_total': 500},
            'new': {'max_orders': 2, 'max_days': 30},
            'inactive': {'max_days': 90}
        }
    
    def post_process_results(self, results: List[Dict], context: PluginContext) -> List[Dict]:
        """Add customer segmentation to results"""
        if not results or 'customer_id' not in results[0]:
            return results
        
        for result in results:
            # Calculate customer metrics
            total_orders = result.get('total_orders', 0)
            lifetime_value = result.get('lifetime_value', 0)
            days_since_last_order = result.get('days_since_last_order', 0)
            
            # Determine segment
            segment = self._determine_segment(total_orders, lifetime_value, days_since_last_order)
            result['customer_segment'] = segment
            
            # Add segment-specific insights
            result['segment_insights'] = self._get_segment_insights(segment, result)
        
        return results
    
    def _determine_segment(self, total_orders: int, lifetime_value: float, days_since_last: int) -> str:
        """Determine customer segment based on metrics"""
        if total_orders >= self.segments['vip']['min_orders'] and lifetime_value >= self.segments['vip']['min_total']:
            return 'VIP'
        elif total_orders >= self.segments['regular']['min_orders'] and lifetime_value >= self.segments['regular']['min_total']:
            return 'Regular'
        elif total_orders <= self.segments['new']['max_orders'] and days_since_last <= self.segments['new']['max_days']:
            return 'New'
        elif days_since_last >= self.segments['inactive']['max_days']:
            return 'Inactive'
        else:
            return 'Occasional'
    
    def _get_segment_insights(self, segment: str, result: Dict) -> str:
        """Get insights for customer segment"""
        insights = {
            'VIP': 'High-value customer with strong loyalty',
            'Regular': 'Consistent customer with good engagement',
            'New': 'Recent customer, opportunity for onboarding',
            'Inactive': 'Customer may need re-engagement campaign',
            'Occasional': 'Infrequent customer, potential for growth'
        }
        return insights.get(segment, 'Standard customer')


class RevenueAnalyticsPlugin(BaseRAGPlugin):
    """Plugin for revenue analytics and insights"""
    
    def __init__(self):
        super().__init__("RevenueAnalytics", "1.0.0", PluginPriority.NORMAL)
    
    def post_process_results(self, results: List[Dict], context: PluginContext) -> List[Dict]:
        """Add revenue analytics to results"""
        if not results:
            return results
        
        # Calculate overall metrics
        total_revenue = sum(r.get('total', 0) for r in results)
        avg_order_value = total_revenue / len(results) if results else 0
        max_order = max((r.get('total', 0) for r in results), default=0)
        
        # Add analytics to each result
        for result in results:
            result['revenue_analytics'] = {
                'total_revenue': total_revenue,
                'avg_order_value': avg_order_value,
                'max_order_value': max_order,
                'revenue_percentage': (result.get('total', 0) / total_revenue * 100) if total_revenue > 0 else 0,
                'is_above_average': result.get('total', 0) > avg_order_value
            }
        
        return results
    
    def enhance_response(self, response: str, context: PluginContext) -> str:
        """Add revenue insights to response"""
        if 'revenue' in context.user_query.lower() or 'sales' in context.user_query.lower():
            response += "\n\n📊 *Revenue Analytics: This data includes comprehensive revenue metrics and trends.*"
        
        return response


class TimeBasedInsightsPlugin(BaseRAGPlugin):
    """Plugin for time-based analysis and insights"""
    
    def __init__(self):
        super().__init__("TimeBasedInsights", "1.0.0", PluginPriority.NORMAL)
    
    def post_process_results(self, results: List[Dict], context: PluginContext) -> List[Dict]:
        """Add time-based insights to results"""
        if not results:
            return results
        
        current_time = datetime.now()
        
        for result in results:
            # Add time-based fields
            if 'order_date' in result:
                order_date = self._parse_date(result['order_date'])
                if order_date:
                    result['time_insights'] = {
                        'days_ago': (current_time - order_date).days,
                        'is_recent': (current_time - order_date).days <= 7,
                        'is_this_month': order_date.month == current_time.month and order_date.year == current_time.year,
                        'is_this_year': order_date.year == current_time.year,
                        'day_of_week': order_date.strftime('%A'),
                        'month_name': order_date.strftime('%B')
                    }
        
        return results
    
    def _parse_date(self, date_value) -> Optional[datetime]:
        """Parse date from various formats"""
        if isinstance(date_value, datetime):
            return date_value
        elif isinstance(date_value, str):
            try:
                return datetime.fromisoformat(date_value.replace('Z', '+00:00'))
            except:
                try:
                    return datetime.strptime(date_value, '%Y-%m-%d')
                except:
                    return None
        return None


class GeographicInsightsPlugin(BaseRAGPlugin):
    """Plugin for geographic analysis and insights"""
    
    def __init__(self):
        super().__init__("GeographicInsights", "1.0.0", PluginPriority.NORMAL)
        
        # Define regions
        self.regions = {
            'north_america': ['usa', 'canada', 'mexico'],
            'europe': ['uk', 'france', 'germany', 'spain', 'italy'],
            'asia_pacific': ['japan', 'china', 'australia', 'india'],
            'latin_america': ['brazil', 'argentina', 'chile']
        }
    
    def post_process_results(self, results: List[Dict], context: PluginContext) -> List[Dict]:
        """Add geographic insights to results"""
        if not results:
            return results
        
        for result in results:
            country = result.get('customer_country', '').lower()
            city = result.get('customer_city', '').lower()
            
            # Determine region
            region = self._determine_region(country)
            
            result['geographic_insights'] = {
                'region': region,
                'is_international': country not in ['usa', 'united states', 'us'],
                'city_popularity': self._get_city_popularity(city),
                'timezone_estimate': self._estimate_timezone(country)
            }
        
        return results
    
    def _determine_region(self, country: str) -> str:
        """Determine geographic region from country"""
        for region, countries in self.regions.items():
            if country in countries:
                return region.replace('_', ' ').title()
        return 'Other'
    
    def _get_city_popularity(self, city: str) -> str:
        """Determine city popularity level"""
        major_cities = ['new york', 'los angeles', 'chicago', 'london', 'paris', 'tokyo']
        if city in major_cities:
            return 'Major'
        elif len(city) > 0:
            return 'Standard'
        return 'Unknown'
    
    def _estimate_timezone(self, country: str) -> str:
        """Estimate timezone from country"""
        timezones = {
            'usa': 'EST/PST',
            'uk': 'GMT',
            'france': 'CET',
            'germany': 'CET',
            'japan': 'JST',
            'australia': 'AEST'
        }
        return timezones.get(country, 'Unknown')


class PerformanceOptimizationPlugin(BaseRAGPlugin):
    """Plugin for performance optimization and caching"""
    
    def __init__(self):
        super().__init__("PerformanceOptimization", "1.0.0", PluginPriority.HIGH)
        self.query_cache = {}
        self.cache_size_limit = 100
    
    def pre_process_query(self, query: str, context: PluginContext) -> str:
        """Check cache for similar queries"""
        # Simple cache key based on query hash
        cache_key = hash(query.lower().strip())
        
        if cache_key in self.query_cache:
            logger.info(f"Cache hit for query: {query[:50]}...")
            # Could return cached result here if needed
        
        return query
    
    def post_process_results(self, results: List[Dict], context: PluginContext) -> List[Dict]:
        """Cache results for future use"""
        if results:
            cache_key = hash(context.user_query.lower().strip())
            
            # Simple LRU cache implementation
            if len(self.query_cache) >= self.cache_size_limit:
                # Remove oldest entry
                oldest_key = next(iter(self.query_cache))
                del self.query_cache[oldest_key]
            
            self.query_cache[cache_key] = {
                'results': results,
                'timestamp': datetime.now(),
                'template_id': context.template_id
            }
        
        return results


class DataValidationPlugin(BaseRAGPlugin):
    """Plugin for data validation and quality checks"""
    
    def __init__(self):
        super().__init__("DataValidation", "1.0.0", PluginPriority.CRITICAL)
    
    def post_process_results(self, results: List[Dict], context: PluginContext) -> List[Dict]:
        """Validate and clean data"""
        if not results:
            return results
        
        validated_results = []
        
        for result in results:
            # Validate required fields
            if self._validate_record(result):
                # Clean data
                cleaned_result = self._clean_record(result)
                validated_results.append(cleaned_result)
            else:
                logger.warning(f"Skipping invalid record: {result}")
        
        return validated_results
    
    def _validate_record(self, record: Dict) -> bool:
        """Validate a single record"""
        # Check for required fields
        required_fields = ['customer_id', 'order_id']
        for field in required_fields:
            if field not in record or record[field] is None:
                return False
        
        # Validate numeric fields
        if 'total' in record and not isinstance(record['total'], (int, float)):
            return False
        
        return True
    
    def _clean_record(self, record: Dict) -> Dict:
        """Clean a single record"""
        cleaned = record.copy()
        
        # Clean string fields
        for key, value in cleaned.items():
            if isinstance(value, str):
                cleaned[key] = value.strip()
        
        # Ensure numeric fields are proper types
        if 'total' in cleaned and cleaned['total'] is not None:
            try:
                cleaned['total'] = float(cleaned['total'])
            except (ValueError, TypeError):
                cleaned['total'] = 0.0
        
        return cleaned


class BusinessRulesPlugin(BaseRAGPlugin):
    """Plugin for applying business rules and policies"""
    
    def __init__(self):
        super().__init__("BusinessRules", "1.0.0", PluginPriority.NORMAL)
        
        # Define business rules
        self.rules = {
            'min_order_amount': 10.0,
            'max_discount_percentage': 25.0,
            'vip_threshold': 1000.0,
            'suspicious_amount_threshold': 10000.0
        }
    
    def post_process_results(self, results: List[Dict], context: PluginContext) -> List[Dict]:
        """Apply business rules to results"""
        if not results:
            return results
        
        for result in results:
            # Apply business rules
            result['business_flags'] = self._apply_business_rules(result)
            
            # Add recommendations
            result['recommendations'] = self._generate_recommendations(result)
        
        return results
    
    def _apply_business_rules(self, result: Dict) -> Dict:
        """Apply business rules to a result"""
        flags = {}
        
        # Check for suspicious amounts
        total = result.get('total', 0)
        if total > self.rules['suspicious_amount_threshold']:
            flags['suspicious_amount'] = True
        
        # Check for VIP status
        if total >= self.rules['vip_threshold']:
            flags['vip_candidate'] = True
        
        # Check for low-value orders
        if total < self.rules['min_order_amount']:
            flags['low_value'] = True
        
        return flags
    
    def _generate_recommendations(self, result: Dict) -> List[str]:
        """Generate business recommendations"""
        recommendations = []
        total = result.get('total', 0)
        
        if total >= self.rules['vip_threshold']:
            recommendations.append("Consider VIP customer program")
        
        if result.get('status') == 'pending' and total > 500:
            recommendations.append("High-value pending order - prioritize processing")
        
        if result.get('days_since_last_order', 0) > 90:
            recommendations.append("Customer re-engagement opportunity")
        
        return recommendations


# Example usage function
def create_example_plugins() -> List[BaseRAGPlugin]:
    """Create a list of example plugins for demonstration"""
    return [
        CustomerSegmentationPlugin(),
        RevenueAnalyticsPlugin(),
        TimeBasedInsightsPlugin(),
        GeographicInsightsPlugin(),
        PerformanceOptimizationPlugin(),
        DataValidationPlugin(),
        BusinessRulesPlugin()
    ]


if __name__ == "__main__":
    # Example of how to use these plugins
    from customer_order_rag import SemanticRAGSystem
    
    # Create RAG system with custom plugins
    rag_system = SemanticRAGSystem(enable_default_plugins=False)
    
    # Register example plugins
    example_plugins = create_example_plugins()
    for plugin in example_plugins:
        rag_system.register_plugin(plugin)
    
    print("🔌 Example plugins registered:")
    for plugin in rag_system.list_plugins():
        print(f"  - {plugin['name']} v{plugin['version']} ({plugin['priority']})") 