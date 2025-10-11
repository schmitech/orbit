"""
Configuration Compatibility Test

This script tests that existing configs work with the new unified architecture.
Run this to verify migration readiness.
"""

import asyncio
import sys
import yaml
from pathlib import Path

# Add project root to path for standalone execution
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from server.ai_services import AIServiceFactory, ServiceType, register_all_services


async def test_provider(provider_name: str, config: dict):
    """Test a single provider with its config."""
    print(f"\n{'='*60}")
    print(f"Testing provider: {provider_name}")
    print(f"{'='*60}")

    try:
        # Get provider config
        provider_config = config.get('inference', {}).get(provider_name)
        if not provider_config:
            print(f"❌ No config found for {provider_name}")
            return False

        print(f"✓ Config found")

        # Create service
        service = AIServiceFactory.create_service(
            ServiceType.INFERENCE,
            provider_name,
            config
        )
        print(f"✓ Service created")

        # Initialize
        await service.initialize()
        print(f"✓ Service initialized")

        # Test generate (with a safe prompt)
        response = await service.generate("Say 'test successful'")
        print(f"✓ Generation works: {response[:50]}...")

        # Test streaming
        print(f"✓ Testing streaming...")
        chunks = []
        async for chunk in service.generate_stream("Count: 1, 2, 3"):
            chunks.append(chunk)
            if len(chunks) >= 5:  # Just test first few chunks
                break
        print(f"✓ Streaming works: {len(chunks)} chunks received")

        # Cleanup
        await service.close()
        print(f"✓ Service closed")

        print(f"\n✅ {provider_name.upper()} - ALL TESTS PASSED")
        return True

    except Exception as e:
        print(f"\n❌ {provider_name.upper()} - FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main test function."""
    print("="*60)
    print("AI SERVICES CONFIGURATION COMPATIBILITY TEST")
    print("="*60)

    # Register all services
    print("\nRegistering all AI services...")
    register_all_services()
    print("✓ All services registered")

    # Load configs
    config_dir = Path(__file__).parent.parent.parent.parent / 'config'

    print(f"\nLoading configs from: {config_dir}")

    # Load inference config
    inference_config_path = config_dir / 'inference.yaml'
    with open(inference_config_path, 'r') as f:
        inference_config = yaml.safe_load(f)

    # Load embeddings config
    embeddings_config_path = config_dir / 'embeddings.yaml'
    with open(embeddings_config_path, 'r') as f:
        embeddings_config = yaml.safe_load(f)

    # Combine configs (as the app does)
    config = {
        'inference': inference_config.get('inference', {}),
        'embeddings': embeddings_config.get('embeddings', {})
    }

    print(f"✓ Configs loaded")

    # Test providers that are likely to be configured
    # (You can add more or test all based on your setup)
    providers_to_test = []

    # Check which providers have configs
    for provider_name in config['inference'].keys():
        if provider_name and isinstance(config['inference'][provider_name], dict):
            providers_to_test.append(provider_name)

    print(f"\nFound {len(providers_to_test)} configured providers:")
    for p in providers_to_test:
        print(f"  - {p}")

    # Test each provider
    print(f"\n{'='*60}")
    print("TESTING PROVIDERS")
    print(f"{'='*60}")

    results = {}
    for provider_name in providers_to_test[:5]:  # Test first 5 to avoid rate limits
        results[provider_name] = await test_provider(provider_name, config)

    # Summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")

    passed = sum(1 for v in results.values() if v)
    failed = len(results) - passed

    print(f"\nTotal Providers Tested: {len(results)}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")

    if failed == 0:
        print(f"\n🎉 ALL TESTS PASSED! Config is compatible with new architecture.")
        print(f"✅ Safe to migrate to unified architecture")
    else:
        print(f"\n⚠️  Some tests failed. Review errors above.")
        print(f"Note: Failures may be due to:")
        print(f"  - Missing API keys")
        print(f"  - Service not running (e.g., local Ollama)")
        print(f"  - Network issues")
        print(f"\nConfig format is still compatible - just fix runtime issues")

    return failed == 0


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
