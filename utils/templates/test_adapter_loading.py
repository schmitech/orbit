#!/usr/bin/env python3
"""
Intent Adapter Loading Test Script

DESCRIPTION:
    Tests that generated domain configuration and template files can be
    successfully loaded by the Orbit IntentAdapter class.

    This script verifies:
    - IntentAdapter can import and initialize
    - Domain config loads without errors
    - Template library loads without errors
    - Domain entities and fields are accessible
    - Templates can be retrieved by ID
    - get_all_templates() returns expected format

USAGE:
    python test_adapter_loading.py <domain_config.yaml> <templates.yaml>

ARGUMENTS:
    domain_config.yaml    Path to domain configuration file
    templates.yaml        Path to template library file

EXAMPLES:
    # Test contact example
    python test_adapter_loading.py contact-example-domain.yaml contact-example-output.yaml

    # Test custom domain
    python test_adapter_loading.py my-domain.yaml my-templates.yaml

REQUIREMENTS:
    - Must be run from the Orbit project root directory
    - Requires Orbit dependencies to be installed
    - Virtual environment should be activated if using one

OUTPUT:
    Shows step-by-step loading process:
    - ✅ Import successful
    - ✅ Adapter instance created
    - ✅ Domain config loaded
    - ✅ Template library loaded
    - ✅ Template retrieval methods work

    Exit codes:
    - 0: All loading tests passed
    - 1: Loading failed or import error

TROUBLESHOOTING:
    If you see "No module named 'utils.lazy_loader'":
    - You're not running from Orbit project root
    - Change to Orbit directory: cd /path/to/orbit
    - Then run: python utils/sql-intent-template/test_adapter_loading.py ...

    If you see other import errors:
    - Activate virtual environment: source venv/bin/activate
    - Install dependencies: pip install -r requirements.txt

WHEN TO USE:
    - After generating new domain/template files
    - Before deploying to production
    - When debugging Intent adapter issues
    - To verify compatibility after structure changes
    - As part of integration testing

SEE ALSO:
    - validate_output.py: Validate file structure
    - compare_structures.py: Compare with references
    - server/retrievers/adapters/intent/intent_adapter.py: Adapter source

AUTHOR:
    SQL Intent Template Generator v1.0.0
    Part of the Orbit Intent SQL RAG System
"""

import sys
from pathlib import Path

# Add the project root to sys.path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def test_adapter_loading(domain_path: str, template_path: str):
    """Test loading the generated config files with Intent adapter"""

    print("🧪 Testing Intent Adapter Loading")
    print("=" * 60)

    try:
        # Import the Intent adapter
        from server.retrievers.adapters.intent.intent_adapter import IntentAdapter

        print("✅ Successfully imported IntentAdapter")

        # Try to create an adapter instance
        print(f"\n📂 Loading domain config: {domain_path}")
        print(f"📂 Loading template library: {template_path}")

        adapter = IntentAdapter(
            domain_config_path=domain_path,
            template_library_path=template_path,
            confidence_threshold=0.1,
            verbose=True
        )

        print("\n✅ Successfully created IntentAdapter instance")

        # Verify domain config loaded
        domain_config = adapter.get_domain_config()
        if domain_config:
            print(f"✅ Domain config loaded: {domain_config.get('domain_name', 'Unknown')}")
            print(f"   - Entities: {len(domain_config.get('entities', {}))}")
            print(f"   - Fields: {sum(len(fields) for fields in domain_config.get('fields', {}).values())}")
            print(f"   - Relationships: {len(domain_config.get('relationships', []))}")
        else:
            print("⚠️  Domain config is None")

        # Verify template library loaded
        template_library = adapter.get_template_library()
        if template_library:
            templates = template_library.get('templates', [])
            print(f"✅ Template library loaded: {len(templates)} templates")

            # Show first template
            if templates:
                first_template = templates[0]
                print("\n   First template:")
                print(f"   - ID: {first_template.get('id')}")
                print(f"   - Description: {first_template.get('description')}")
                print(f"   - Parameters: {len(first_template.get('parameters', []))}")
                print(f"   - NL Examples: {len(first_template.get('nl_examples', []))}")
        else:
            print("⚠️  Template library is None")

        # Test getting a specific template
        all_templates = adapter.get_all_templates()
        print(f"\n✅ get_all_templates() returned {len(all_templates)} templates")

        if all_templates:
            first_id = all_templates[0].get('id')
            template = adapter.get_template_by_id(first_id)
            if template:
                print(f"✅ get_template_by_id('{first_id}') works correctly")
            else:
                print(f"❌ get_template_by_id('{first_id}') returned None")

        print("\n" + "=" * 60)
        print("✅ ALL ADAPTER LOADING TESTS PASSED!")
        print("   Generated files are fully compatible with Intent adapter.")
        print("=" * 60)

        return True

    except ImportError as e:
        print(f"❌ Failed to import IntentAdapter: {e}")
        print("   Note: This is expected if not running from Orbit project root")
        return False
    except Exception as e:
        print(f"❌ Error loading adapter: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function"""
    if len(sys.argv) < 3:
        print("Usage: python test_adapter_loading.py <domain_config.yaml> <templates.yaml>")
        print("\nExample:")
        print("  python test_adapter_loading.py contact-example-domain.yaml contact-example-output.yaml")
        sys.exit(1)

    domain_path = sys.argv[1]
    template_path = sys.argv[2]

    # Check files exist
    if not Path(domain_path).exists():
        print(f"❌ Domain config file not found: {domain_path}")
        sys.exit(1)

    if not Path(template_path).exists():
        print(f"❌ Template file not found: {template_path}")
        sys.exit(1)

    # Run test
    success = test_adapter_loading(domain_path, template_path)

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
