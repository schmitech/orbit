#!/usr/bin/env python3
"""
Shared Domain Configuration
===========================

Single source of truth for domain configuration to ensure consistency
between conversational_demo.py and streamlit_demo.py
"""

from domain_configuration import DomainConfiguration, DomainEntity, DomainField, DomainRelationship
from domain_configuration import DataType, EntityType, RelationType


def create_customer_order_domain() -> DomainConfiguration:
    """Create customer order domain configuration - SINGLE SOURCE OF TRUTH"""
    domain = DomainConfiguration(
        domain_name="E-Commerce",
        description="Customer order management system"
    )
    
    # Customer entity
    customer_entity = DomainEntity(
        name="customer",
        entity_type=EntityType.PRIMARY,
        table_name="customers",
        description="Customer information",
        primary_key="id",
        display_name_field="name",
        searchable_fields=["name", "email", "phone"],
        common_filters=["city", "country", "created_at"],  # Include created_at
        default_sort_field="created_at"
    )
    domain.add_entity(customer_entity)
    
    # Order entity
    order_entity = DomainEntity(
        name="order",
        entity_type=EntityType.TRANSACTION,
        table_name="orders",
        description="Customer orders",
        primary_key="id",
        display_name_field="id",
        searchable_fields=["id", "status"],
        common_filters=["status", "payment_method", "order_date", "total"],
        default_sort_field="order_date"
    )
    domain.add_entity(order_entity)
    
    # Customer fields
    domain.add_field("customer", DomainField(
        name="id",
        data_type=DataType.INTEGER,
        db_column="id",
        description="Customer ID",
        required=True,
        searchable=True
    ))
    
    domain.add_field("customer", DomainField(
        name="name",
        data_type=DataType.STRING,
        db_column="name",
        description="Customer name",
        required=True,
        searchable=True,
        aliases=["customer name", "client name", "buyer name"]
    ))
    
    domain.add_field("customer", DomainField(
        name="email",
        data_type=DataType.STRING,
        db_column="email",
        description="Customer email",
        required=True,
        searchable=True,
        display_format="email"
    ))
    
    domain.add_field("customer", DomainField(
        name="phone",
        data_type=DataType.STRING,
        db_column="phone",
        description="Phone number",
        searchable=True,
        display_format="phone"
    ))
    
    domain.add_field("customer", DomainField(
        name="city",
        data_type=DataType.STRING,
        db_column="city",
        description="City",
        filterable=True
    ))
    
    domain.add_field("customer", DomainField(
        name="country",
        data_type=DataType.STRING,
        db_column="country",
        description="Country",
        filterable=True
    ))
    
    # ADD MISSING created_at field that was in conversational version
    domain.add_field("customer", DomainField(
        name="created_at",
        data_type=DataType.DATETIME,
        db_column="created_at",
        description="Customer creation date",
        required=True,
        filterable=True,
        sortable=True,
        display_format="date"
    ))
    
    # Order fields
    domain.add_field("order", DomainField(
        name="id",
        data_type=DataType.INTEGER,
        db_column="id",
        description="Order ID",
        required=True,
        searchable=True
    ))
    
    domain.add_field("order", DomainField(
        name="customer_id",
        data_type=DataType.INTEGER,
        db_column="customer_id",
        description="Customer ID",
        required=True
    ))
    
    domain.add_field("order", DomainField(
        name="order_date",
        data_type=DataType.DATETIME,
        db_column="order_date",
        description="Order date",
        required=True,
        filterable=True,
        sortable=True,
        display_format="date"
    ))
    
    domain.add_field("order", DomainField(
        name="total",
        data_type=DataType.DECIMAL,
        db_column="total",
        description="Order total amount",
        required=True,
        filterable=True,
        display_format="currency"
    ))
    
    domain.add_field("order", DomainField(
        name="status",
        data_type=DataType.ENUM,
        db_column="status",
        description="Order status",
        required=True,
        searchable=True,
        filterable=True,
        enum_values=["pending", "processing", "shipped", "delivered", "cancelled"]
    ))
    
    domain.add_field("order", DomainField(
        name="payment_method",
        data_type=DataType.ENUM,
        db_column="payment_method",
        description="Payment method",
        filterable=True,
        enum_values=["credit_card", "debit_card", "paypal", "bank_transfer", "cash"]
    ))
    
    domain.add_field("order", DomainField(
        name="shipping_address",
        data_type=DataType.STRING,
        db_column="shipping_address",
        description="Shipping address"
    ))
    
    domain.add_field("order", DomainField(
        name="shipping_city",
        data_type=DataType.STRING,
        db_column="shipping_city",
        description="Shipping city"
    ))
    
    domain.add_field("order", DomainField(
        name="shipping_country",
        data_type=DataType.STRING,
        db_column="shipping_country",
        description="Shipping country"
    ))
    
    # Relationship
    domain.add_relationship(DomainRelationship(
        name="customer_orders",
        from_entity="customer",
        to_entity="order",
        relation_type=RelationType.ONE_TO_MANY,
        from_field="id",
        to_field="customer_id",
        description="Customer has many orders"
    ))
    
    # Vocabulary - CONSISTENT across both demos
    domain.vocabulary.entity_synonyms = {
        "customer": ["client", "buyer", "user", "purchaser", "shopper"],
        "order": ["purchase", "transaction", "sale", "invoice"]
    }
    
    domain.vocabulary.action_verbs = {
        "find": ["show", "list", "get", "find", "display", "retrieve"],
        "calculate": ["sum", "total", "calculate", "compute", "aggregate"],
        "filter": ["filter", "only", "just", "where", "with"]
    }
    
    domain.vocabulary.time_expressions = {
        "today": "0",
        "yesterday": "1",
        "this week": "7",
        "last week": "14",
        "this month": "30",
        "last month": "60",
        "this year": "365"
    }
    
    return domain