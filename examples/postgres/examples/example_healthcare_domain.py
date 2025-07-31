#!/usr/bin/env python3
"""
Example: Healthcare Domain Implementation
========================================

This example demonstrates how to use the RAG system for a 
healthcare domain with patients, appointments, and medical records.
"""

from datetime import datetime, date
from base_rag_system import RAGSystem
from domain_configuration import (
    DomainConfiguration, DomainEntity, DomainField, 
    DomainRelationship, DataType, EntityType, RelationType
)
from template_library import TemplateLibrary, QueryTemplateBuilder, TemplateType, ParameterType
from domain_plugin import DomainSpecificPlugin, DomainAnalyticsPlugin
from plugin_system import PluginManager
from base_classes import BaseEmbeddingClient, BaseInferenceClient, BaseDatabaseClient

# Import the actual implementations
from clients import OllamaEmbeddingClient, OllamaInferenceClient, PostgreSQLDatabaseClient


def create_healthcare_domain() -> DomainConfiguration:
    """Create a healthcare domain configuration"""
    
    domain = DomainConfiguration(
        domain_name="Healthcare",
        description="Healthcare system with patients, appointments, and medical records"
    )
    
    # === ENTITIES ===
    
    # Patient entity
    patient_entity = DomainEntity(
        name="patient",
        entity_type=EntityType.PRIMARY,
        table_name="patients",
        description="Patient information",
        primary_key="patient_id",
        display_name_field="full_name",
        searchable_fields=["full_name", "email", "phone", "medical_record_number"],
        common_filters=["age_group", "city", "insurance_provider"],
        default_sort_field="registration_date",
        default_sort_order="DESC"
    )
    domain.add_entity(patient_entity)
    
    # Appointment entity
    appointment_entity = DomainEntity(
        name="appointment",
        entity_type=EntityType.TRANSACTION,
        table_name="appointments",
        description="Medical appointments",
        primary_key="appointment_id",
        display_name_field="appointment_id",
        searchable_fields=["appointment_id", "status", "appointment_type"],
        common_filters=["status", "appointment_type", "appointment_date", "doctor_id"],
        default_sort_field="appointment_date",
        default_sort_order="DESC"
    )
    domain.add_entity(appointment_entity)
    
    # Doctor entity
    doctor_entity = DomainEntity(
        name="doctor",
        entity_type=EntityType.LOOKUP,
        table_name="doctors",
        description="Healthcare provider information",
        primary_key="doctor_id",
        display_name_field="doctor_name",
        searchable_fields=["doctor_name", "specialization", "license_number"],
        common_filters=["specialization", "department"],
        default_sort_field="doctor_name"
    )
    domain.add_entity(doctor_entity)
    
    # === FIELDS ===
    
    # Patient fields
    domain.add_field("patient", DomainField(
        name="patient_id",
        data_type=DataType.INTEGER,
        db_column="patient_id",
        description="Patient ID",
        required=True,
        searchable=True
    ))
    
    domain.add_field("patient", DomainField(
        name="full_name",
        data_type=DataType.STRING,
        db_column="full_name",
        description="Patient full name",
        required=True,
        searchable=True,
        aliases=["patient name", "name", "patient"]
    ))
    
    domain.add_field("patient", DomainField(
        name="date_of_birth",
        data_type=DataType.DATE,
        db_column="date_of_birth",
        description="Date of birth",
        required=True,
        display_format="date"
    ))
    
    domain.add_field("patient", DomainField(
        name="email",
        data_type=DataType.STRING,
        db_column="email",
        description="Email address",
        searchable=True,
        display_format="email"
    ))
    
    domain.add_field("patient", DomainField(
        name="phone",
        data_type=DataType.STRING,
        db_column="phone",
        description="Phone number",
        searchable=True,
        display_format="phone"
    ))
    
    domain.add_field("patient", DomainField(
        name="medical_record_number",
        data_type=DataType.STRING,
        db_column="medical_record_number",
        description="Medical record number (MRN)",
        required=True,
        searchable=True,
        aliases=["mrn", "record number"]
    ))
    
    domain.add_field("patient", DomainField(
        name="insurance_provider",
        data_type=DataType.STRING,
        db_column="insurance_provider",
        description="Insurance provider",
        filterable=True
    ))
    
    domain.add_field("patient", DomainField(
        name="age_group",
        data_type=DataType.ENUM,
        db_column="age_group",
        description="Age group category",
        filterable=True,
        enum_values=["pediatric", "adult", "senior"]
    ))
    
    # Appointment fields
    domain.add_field("appointment", DomainField(
        name="appointment_id",
        data_type=DataType.INTEGER,
        db_column="appointment_id",
        description="Appointment ID",
        required=True,
        searchable=True
    ))
    
    domain.add_field("appointment", DomainField(
        name="patient_id",
        data_type=DataType.INTEGER,
        db_column="patient_id",
        description="Patient ID",
        required=True
    ))
    
    domain.add_field("appointment", DomainField(
        name="doctor_id",
        data_type=DataType.INTEGER,
        db_column="doctor_id",
        description="Doctor ID",
        required=True,
        filterable=True
    ))
    
    domain.add_field("appointment", DomainField(
        name="appointment_date",
        data_type=DataType.DATETIME,
        db_column="appointment_date",
        description="Appointment date and time",
        required=True,
        filterable=True,
        sortable=True,
        display_format="datetime"
    ))
    
    domain.add_field("appointment", DomainField(
        name="appointment_type",
        data_type=DataType.ENUM,
        db_column="appointment_type",
        description="Type of appointment",
        required=True,
        searchable=True,
        filterable=True,
        enum_values=["consultation", "follow-up", "procedure", "emergency", "checkup"]
    ))
    
    domain.add_field("appointment", DomainField(
        name="status",
        data_type=DataType.ENUM,
        db_column="status",
        description="Appointment status",
        required=True,
        searchable=True,
        filterable=True,
        enum_values=["scheduled", "confirmed", "in-progress", "completed", "cancelled", "no-show"]
    ))
    
    domain.add_field("appointment", DomainField(
        name="duration_minutes",
        data_type=DataType.INTEGER,
        db_column="duration_minutes",
        description="Appointment duration in minutes",
        default=30
    ))
    
    domain.add_field("appointment", DomainField(
        name="notes",
        data_type=DataType.STRING,
        db_column="notes",
        description="Appointment notes"
    ))
    
    # Doctor fields
    domain.add_field("doctor", DomainField(
        name="doctor_id",
        data_type=DataType.INTEGER,
        db_column="doctor_id",
        description="Doctor ID",
        required=True,
        searchable=True
    ))
    
    domain.add_field("doctor", DomainField(
        name="doctor_name",
        data_type=DataType.STRING,
        db_column="doctor_name",
        description="Doctor full name",
        required=True,
        searchable=True,
        aliases=["physician", "provider", "doc"]
    ))
    
    domain.add_field("doctor", DomainField(
        name="specialization",
        data_type=DataType.ENUM,
        db_column="specialization",
        description="Medical specialization",
        required=True,
        searchable=True,
        filterable=True,
        enum_values=[
            "general_practice", "cardiology", "neurology", "pediatrics",
            "orthopedics", "dermatology", "psychiatry", "surgery"
        ]
    ))
    
    domain.add_field("doctor", DomainField(
        name="department",
        data_type=DataType.STRING,
        db_column="department",
        description="Hospital department",
        filterable=True
    ))
    
    # === RELATIONSHIPS ===
    
    domain.add_relationship(DomainRelationship(
        name="patient_appointments",
        from_entity="patient",
        to_entity="appointment",
        relation_type=RelationType.ONE_TO_MANY,
        from_field="patient_id",
        to_field="patient_id",
        description="Patient has many appointments"
    ))
    
    domain.add_relationship(DomainRelationship(
        name="doctor_appointments",
        from_entity="doctor",
        to_entity="appointment",
        relation_type=RelationType.ONE_TO_MANY,
        from_field="doctor_id",
        to_field="doctor_id",
        description="Doctor has many appointments"
    ))
    
    # === VOCABULARY ===
    
    domain.vocabulary.entity_synonyms = {
        "patient": ["patient", "client", "person", "individual"],
        "appointment": ["appointment", "visit", "consultation", "meeting", "slot"],
        "doctor": ["doctor", "physician", "provider", "specialist", "practitioner"]
    }
    
    domain.vocabulary.action_verbs = {
        "find": ["show", "list", "get", "find", "display", "retrieve", "lookup"],
        "calculate": ["count", "total", "calculate", "compute", "sum"],
        "filter": ["filter", "only", "just", "where", "with"],
        "schedule": ["schedule", "book", "arrange", "set up"]
    }
    
    domain.vocabulary.time_expressions = {
        "today": "0",
        "yesterday": "1",
        "tomorrow": "-1",
        "this week": "7",
        "last week": "14",
        "this month": "30",
        "last month": "60"
    }
    
    return domain


def create_healthcare_templates(domain: DomainConfiguration) -> TemplateLibrary:
    """Create healthcare-specific query templates"""
    
    library = TemplateLibrary(domain)
    
    # 1. Find patient by MRN
    template = (QueryTemplateBuilder("find_patient_by_mrn", domain)
        .with_description("Find patient by medical record number")
        .of_type(TemplateType.SEARCH_FIND)
        .with_examples(
            "Find patient with MRN 12345",
            "Show me patient record MRN12345",
            "Look up medical record number 67890"
        )
        .with_parameter(
            name="mrn",
            param_type=ParameterType.STRING,
            description="Medical record number",
            required=True,
            pattern=r"^[A-Z0-9]+$"
        )
        .with_semantic_tags(
            action="search_find",
            primary_entity="patient",
            qualifiers=["mrn", "medical_record"]
        )
        .with_sql("""
            SELECT * FROM patients
            WHERE medical_record_number = %(mrn)s
        """)
        .with_tags("patient", "mrn", "medical_record", "find")
        .approve()
        .build()
    )
    library.add_template(template)
    
    # 2. Today's appointments for a doctor
    template = (QueryTemplateBuilder("doctor_appointments_today", domain)
        .with_description("Show today's appointments for a specific doctor")
        .of_type(TemplateType.FIND_LIST)
        .with_examples(
            "Show me Dr. Smith's appointments today",
            "What appointments does doctor 123 have today?",
            "List today's schedule for Dr. Johnson"
        )
        .with_parameter(
            name="doctor_name",
            param_type=ParameterType.STRING,
            description="Doctor's name",
            required=False,
            aliases=["physician", "provider"]
        )
        .with_parameter(
            name="doctor_id",
            param_type=ParameterType.INTEGER,
            description="Doctor ID",
            required=False
        )
        .with_semantic_tags(
            action="find_list",
            primary_entity="appointment",
            secondary_entity="doctor",
            qualifiers=["today", "schedule"]
        )
        .with_sql("""
            SELECT 
                a.*,
                p.full_name as patient_name,
                p.phone as patient_phone,
                d.doctor_name,
                d.specialization
            FROM appointments a
            JOIN patients p ON a.patient_id = p.patient_id
            JOIN doctors d ON a.doctor_id = d.doctor_id
            WHERE DATE(a.appointment_date) = CURRENT_DATE
              {% if doctor_id %}
                AND a.doctor_id = %(doctor_id)s
              {% elif doctor_name %}
                AND LOWER(d.doctor_name) LIKE LOWER(%(doctor_name)s)
              {% endif %}
            ORDER BY a.appointment_date ASC
        """)
        .with_tags("appointment", "doctor", "today", "schedule")
        .approve()
        .build()
    )
    library.add_template(template)
    
    # 3. Patient appointment history
    template = (QueryTemplateBuilder("patient_appointment_history", domain)
        .with_description("Show appointment history for a patient")
        .of_type(TemplateType.FIND_LIST)
        .with_examples(
            "Show me appointment history for patient 123",
            "What appointments has John Smith had?",
            "List all visits for MRN 45678"
        )
        .with_parameter(
            name="patient_id",
            param_type=ParameterType.INTEGER,
            description="Patient ID",
            required=False
        )
        .with_parameter(
            name="patient_name",
            param_type=ParameterType.STRING,
            description="Patient name",
            required=False
        )
        .with_parameter(
            name="mrn",
            param_type=ParameterType.STRING,
            description="Medical record number",
            required=False
        )
        .with_parameter(
            name="days_back",
            param_type=ParameterType.INTEGER,
            description="Number of days to look back",
            default=365
        )
        .with_semantic_tags(
            action="find_list",
            primary_entity="appointment",
            secondary_entity="patient",
            qualifiers=["history", "past"]
        )
        .with_sql("""
            SELECT 
                a.*,
                d.doctor_name,
                d.specialization
            FROM appointments a
            JOIN patients p ON a.patient_id = p.patient_id
            JOIN doctors d ON a.doctor_id = d.doctor_id
            WHERE 1=1
              {% if patient_id %}
                AND a.patient_id = %(patient_id)s
              {% elif patient_name %}
                AND LOWER(p.full_name) LIKE LOWER(%(patient_name)s)
              {% elif mrn %}
                AND p.medical_record_number = %(mrn)s
              {% endif %}
              AND a.appointment_date >= CURRENT_DATE - INTERVAL '%(days_back)s days'
            ORDER BY a.appointment_date DESC
            LIMIT 50
        """)
        .with_tags("appointment", "patient", "history", "medical_history")
        .approve()
        .build()
    )
    library.add_template(template)
    
    # 4. Upcoming appointments by status
    template = (QueryTemplateBuilder("upcoming_appointments_by_status", domain)
        .with_description("Find upcoming appointments filtered by status")
        .of_type(TemplateType.FILTER_BY)
        .with_examples(
            "Show me all scheduled appointments",
            "Find confirmed appointments for next week",
            "List upcoming appointments that need confirmation"
        )
        .with_parameter(
            name="status",
            param_type=ParameterType.ENUM,
            description="Appointment status",
            required=True,
            allowed_values=["scheduled", "confirmed", "in-progress", "completed", "cancelled", "no-show"]
        )
        .with_parameter(
            name="days_ahead",
            param_type=ParameterType.INTEGER,
            description="Number of days to look ahead",
            default=7,
            min_value=1,
            max_value=90
        )
        .with_semantic_tags(
            action="filter_by",
            primary_entity="appointment",
            qualifiers=["upcoming", "status"]
        )
        .with_sql("""
            SELECT 
                a.*,
                p.full_name as patient_name,
                p.phone as patient_phone,
                d.doctor_name,
                d.specialization
            FROM appointments a
            JOIN patients p ON a.patient_id = p.patient_id
            JOIN doctors d ON a.doctor_id = d.doctor_id
            WHERE a.status = %(status)s
              AND a.appointment_date BETWEEN CURRENT_TIMESTAMP 
                  AND CURRENT_TIMESTAMP + INTERVAL '%(days_ahead)s days'
            ORDER BY a.appointment_date ASC
            LIMIT 100
        """)
        .with_tags("appointment", "upcoming", "status", "filter")
        .approve()
        .build()
    )
    library.add_template(template)
    
    # 5. Doctor workload analysis
    template = (QueryTemplateBuilder("doctor_workload_summary", domain)
        .with_description("Calculate appointment workload for doctors")
        .of_type(TemplateType.AGGREGATE_REPORT)
        .with_examples(
            "Show doctor workload for this month",
            "Which doctors are busiest?",
            "Calculate appointment counts by doctor"
        )
        .with_parameter(
            name="days_back",
            param_type=ParameterType.INTEGER,
            description="Number of days to analyze",
            default=30
        )
        .with_parameter(
            name="specialization",
            param_type=ParameterType.ENUM,
            description="Filter by specialization",
            required=False,
            allowed_values=[
                "general_practice", "cardiology", "neurology", "pediatrics",
                "orthopedics", "dermatology", "psychiatry", "surgery"
            ]
        )
        .with_semantic_tags(
            action="aggregate_report",
            primary_entity="doctor",
            secondary_entity="appointment",
            qualifiers=["workload", "busy", "count"]
        )
        .with_sql("""
            SELECT 
                d.doctor_id,
                d.doctor_name,
                d.specialization,
                COUNT(a.appointment_id) as total_appointments,
                COUNT(CASE WHEN a.status = 'completed' THEN 1 END) as completed_appointments,
                COUNT(CASE WHEN a.status = 'cancelled' THEN 1 END) as cancelled_appointments,
                COUNT(CASE WHEN a.status = 'no-show' THEN 1 END) as no_show_appointments,
                AVG(a.duration_minutes) as avg_appointment_duration
            FROM doctors d
            LEFT JOIN appointments a ON d.doctor_id = a.doctor_id
                AND a.appointment_date >= CURRENT_DATE - INTERVAL '%(days_back)s days'
            WHERE 1=1
              {% if specialization %}
                AND d.specialization = %(specialization)s
              {% endif %}
            GROUP BY d.doctor_id, d.doctor_name, d.specialization
            HAVING COUNT(a.appointment_id) > 0
            ORDER BY total_appointments DESC
            LIMIT 20
        """)
        .with_result_format("table")
        .with_tags("doctor", "workload", "analytics", "summary")
        .approve()
        .build()
    )
    library.add_template(template)
    
    return library


def main():
    """Demonstrate healthcare domain usage"""
    
    print("🏥 Healthcare RAG System Demo")
    print("=" * 60)
    
    # Create domain configuration
    healthcare_domain = create_healthcare_domain()
    
    # Create template library
    template_library = create_healthcare_templates(healthcare_domain)
    
    # Initialize clients (reusing from customer_order_rag.py)
    embedding_client = OllamaEmbeddingClient()
    inference_client = OllamaInferenceClient()
    db_client = PostgreSQLDatabaseClient()
    
    # Create RAG system
    rag_system = RAGSystem(
        domain=healthcare_domain,
        template_library=template_library,
        embedding_client=embedding_client,
        inference_client=inference_client,
        db_client=db_client
    )
    
    # Register domain-specific plugins
    domain_plugin = DomainSpecificPlugin(healthcare_domain, inference_client)
    analytics_plugin = DomainAnalyticsPlugin(healthcare_domain)
    
    # Would register with plugin manager if using the full system
    print("✅ Healthcare domain configured")
    print(f"📋 Loaded {len(template_library.templates)} query templates")
    print(f"🔌 Domain plugins ready")
    
    # Export configuration for reference
    healthcare_domain.to_yaml("healthcare_domain.yaml")
    template_library.export_to_yaml("healthcare_templates.yaml")
    
    print("\n📁 Configuration exported:")
    print("  - healthcare_domain.yaml")
    print("  - healthcare_templates.yaml")
    
    # Example queries
    print("\n🧪 Example Healthcare Queries:")
    example_queries = [
        "Find patient with MRN 12345",
        "Show me Dr. Smith's appointments today",
        "What appointments has patient John Smith had?",
        "Show me all scheduled appointments for next week",
        "Which doctors are busiest this month?",
        "List upcoming appointments that need confirmation",
        "Show appointment history for patient 456",
        "Find all pediatric appointments this week",
        "Calculate doctor workload by specialization",
        "Show me no-show appointments from last month"
    ]
    
    for i, query in enumerate(example_queries, 1):
        print(f"{i}. {query}")
    
    print("\n💡 The system can now process these natural language queries")
    print("   and convert them to appropriate SQL using the domain configuration!")


if __name__ == "__main__":
    main()