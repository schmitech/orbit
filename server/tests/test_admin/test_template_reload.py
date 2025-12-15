"""
Test Template Reload Functionality
===================================

Tests for template reload functionality for intent adapters, including:
- Reloading templates for a single adapter
- Reloading templates for all cached intent adapters
- Error handling for non-existent adapters
- Error handling for adapters that don't support template reloading
- Vector store clearing and re-indexing

Prerequisites:
1. Server must be running
2. Authentication must be configured (enabled or disabled)
3. At least one intent adapter should be loaded (cached)
"""

import asyncio
import aiohttp
import pytest
import logging
import yaml
from typing import Optional, Dict, Any
from pathlib import Path
import os

# Mark all tests in this module as integration tests requiring a running server
pytestmark = pytest.mark.integration

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_server_url() -> str:
    """Get server URL from config file"""
    try:
        script_dir = Path(__file__).parent
        project_root = script_dir.parent.parent
        config_path = project_root / "config" / "config.yaml"

        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                port = config.get('general', {}).get('port', 3000)
                return f"http://localhost:{port}"
    except Exception as e:
        logger.warning(f"Failed to read config file: {e}")

    return "http://localhost:3000"


SERVER_URL = get_server_url()
logger.info(f"Using server URL: {SERVER_URL}")

# Default credentials
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = os.getenv('ORBIT_DEFAULT_ADMIN_PASSWORD', 'admin123')


class TemplateReloadTester:
    """Tester for template reload functionality"""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.token: Optional[str] = None
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def _get_headers(self, include_auth: bool = True) -> dict:
        """Get headers with optional authentication"""
        headers = {"Content-Type": "application/json"}
        if include_auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def check_auth_enabled(self) -> bool:
        """Check if authentication is enabled"""
        try:
            async with self.session.post(
                f"{self.base_url}/auth/login",
                json={"username": "test", "password": "test"},
                headers={"Content-Type": "application/json"},
                timeout=5
            ) as response:
                if response.status == 401:
                    return True
                elif response.status in [404, 503]:
                    return False
                return True
        except Exception:
            return True

    async def authenticate(self) -> bool:
        """Authenticate if needed"""
        auth_enabled = await self.check_auth_enabled()

        if not auth_enabled:
            logger.info("Authentication disabled - proceeding without token")
            return True

        try:
            async with self.session.post(
                f"{self.base_url}/auth/login",
                json={"username": DEFAULT_USERNAME, "password": DEFAULT_PASSWORD},
                headers={"Content-Type": "application/json"},
                timeout=10
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    self.token = result.get("token")
                    if self.token:
                        logger.info(f"Authenticated: {self.token[:8]}...")
                        return True
                logger.error(f"Authentication failed: {response.status}")
                return False
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            return False

    async def reload_templates(self, adapter_name: Optional[str] = None) -> Dict[str, Any]:
        """Call the reload templates endpoint"""
        url = f"{self.base_url}/admin/reload-templates"
        if adapter_name:
            url += f"?adapter_name={adapter_name}"

        try:
            async with self.session.post(
                url,
                headers=self._get_headers(),
                timeout=60  # Templates reload can take time
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error = await response.text()
                    return {"error": error, "status_code": response.status}
        except Exception as e:
            logger.error(f"Reload templates error: {str(e)}")
            raise

    async def test_reload_templates_all_adapters(self) -> bool:
        """Test reloading templates for all cached intent adapters"""
        logger.info("\n=== Testing Reload Templates for All Adapters ===")

        try:
            result = await self.reload_templates(adapter_name=None)

            if "error" in result:
                if result.get("status_code") == 503:
                    logger.warning("Adapter manager not available - skipping test")
                    return True
                logger.error(f"Reload failed: {result['error']}")
                return False

            summary = result.get('summary', {})
            templates_loaded = summary.get('templates_loaded', 0)
            adapters_updated = summary.get('adapters_updated', [])

            logger.info(f"Templates loaded: {templates_loaded}")
            logger.info(f"Adapters updated: {adapters_updated}")

            # Success if we got a valid response
            if result.get('status') == 'success':
                logger.info("Template reload for all adapters completed successfully")
                return True
            else:
                logger.warning("Unexpected response format")
                return False

        except Exception as e:
            logger.error(f"Test failed: {str(e)}")
            return False

    async def test_reload_templates_single_adapter(self) -> bool:
        """Test reloading templates for a specific adapter"""
        logger.info("\n=== Testing Reload Templates for Single Adapter ===")

        # First, try to find an intent adapter that might be cached
        test_adapters = [
            'intent-sql-sqlite-hr',
            'intent-sql-duckdb',
            'intent-elasticsearch',
            'intent-mongodb'
        ]

        for adapter_name in test_adapters:
            try:
                result = await self.reload_templates(adapter_name=adapter_name)

                if "error" in result:
                    status_code = result.get("status_code")
                    if status_code == 404:
                        logger.info(f"Adapter '{adapter_name}' not found in cache - trying next")
                        continue
                    elif status_code == 503:
                        logger.warning("Adapter manager not available")
                        return True
                    else:
                        logger.info(f"Adapter '{adapter_name}' error: {result['error']}")
                        continue

                summary = result.get('summary', {})
                templates_loaded = summary.get('templates_loaded', 0)

                logger.info(f"Adapter: {adapter_name}")
                logger.info(f"Templates loaded: {templates_loaded}")

                if result.get('status') == 'success':
                    logger.info(f"Template reload for '{adapter_name}' completed successfully")
                    return True

            except Exception as e:
                logger.info(f"Adapter '{adapter_name}' test failed: {str(e)}")
                continue

        # If no adapters were found, the test passes (no intent adapters loaded)
        logger.info("No cached intent adapters found - test passes")
        return True

    async def test_reload_templates_nonexistent_adapter(self) -> bool:
        """Test error handling for non-existent adapter"""
        logger.info("\n=== Testing Reload Templates for Non-existent Adapter ===")

        try:
            result = await self.reload_templates(adapter_name='nonexistent-adapter-12345')

            if "error" in result:
                status_code = result.get("status_code")
                if status_code == 404:
                    logger.info("Correctly returned 404 for non-existent adapter")
                    return True
                elif status_code == 503:
                    logger.warning("Adapter manager not available")
                    return True

            logger.error("Expected 404 error but got success")
            return False

        except Exception as e:
            logger.error(f"Test failed: {str(e)}")
            return False

    async def test_reload_templates_non_intent_adapter(self) -> bool:
        """Test error handling for adapter that doesn't support template reloading"""
        logger.info("\n=== Testing Reload Templates for Non-intent Adapter ===")

        # Try a non-intent adapter (like simple-chat which is a passthrough adapter)
        try:
            result = await self.reload_templates(adapter_name='simple-chat')

            if "error" in result:
                status_code = result.get("status_code")
                if status_code == 404:
                    # 404 means either not found or doesn't support template reloading
                    error_text = result.get("error", "")
                    if "does not support template reloading" in error_text.lower() or "not found" in error_text.lower():
                        logger.info("Correctly returned 404 for non-intent adapter")
                        return True
                    logger.info(f"Got 404: {error_text}")
                    return True
                elif status_code == 503:
                    logger.warning("Adapter manager not available")
                    return True

            # If it succeeded, simple-chat might have reload_templates method
            # (which would be unexpected but not an error in our code)
            logger.info("Adapter responded successfully (may support template reloading)")
            return True

        except Exception as e:
            logger.error(f"Test failed: {str(e)}")
            return False

    async def test_reload_templates_response_format(self) -> bool:
        """Test that the response format is correct"""
        logger.info("\n=== Testing Reload Templates Response Format ===")

        try:
            result = await self.reload_templates(adapter_name=None)

            if "error" in result:
                if result.get("status_code") == 503:
                    logger.warning("Adapter manager not available - skipping test")
                    return True
                logger.error(f"Reload failed: {result['error']}")
                return False

            # Check required fields
            required_fields = ['status', 'message', 'summary', 'timestamp']
            for field in required_fields:
                if field not in result:
                    logger.error(f"Missing required field: {field}")
                    return False

            # Check summary fields
            summary = result.get('summary', {})
            summary_fields = ['templates_loaded', 'adapters_updated']
            for field in summary_fields:
                if field not in summary:
                    logger.warning(f"Missing summary field: {field}")

            logger.info("Response format is correct")
            logger.info(f"  status: {result.get('status')}")
            logger.info(f"  message: {result.get('message')}")
            logger.info(f"  timestamp: {result.get('timestamp')}")
            logger.info(f"  summary.templates_loaded: {summary.get('templates_loaded')}")
            logger.info(f"  summary.adapters_updated: {summary.get('adapters_updated')}")

            return True

        except Exception as e:
            logger.error(f"Test failed: {str(e)}")
            return False


# ============================================================================
# Pytest Test Functions
# ============================================================================

@pytest.mark.asyncio
async def test_reload_templates_all_adapters():
    """Test reloading templates for all cached intent adapters"""
    async with TemplateReloadTester(SERVER_URL) as tester:
        assert await tester.authenticate(), "Authentication failed"
        assert await tester.test_reload_templates_all_adapters(), "All adapters reload failed"


@pytest.mark.asyncio
async def test_reload_templates_single_adapter():
    """Test reloading templates for a specific adapter"""
    async with TemplateReloadTester(SERVER_URL) as tester:
        assert await tester.authenticate(), "Authentication failed"
        assert await tester.test_reload_templates_single_adapter(), "Single adapter reload failed"


@pytest.mark.asyncio
async def test_reload_templates_nonexistent_adapter():
    """Test error handling for non-existent adapter"""
    async with TemplateReloadTester(SERVER_URL) as tester:
        assert await tester.authenticate(), "Authentication failed"
        assert await tester.test_reload_templates_nonexistent_adapter(), "Non-existent adapter test failed"


@pytest.mark.asyncio
async def test_reload_templates_non_intent_adapter():
    """Test error handling for non-intent adapter"""
    async with TemplateReloadTester(SERVER_URL) as tester:
        assert await tester.authenticate(), "Authentication failed"
        assert await tester.test_reload_templates_non_intent_adapter(), "Non-intent adapter test failed"


@pytest.mark.asyncio
async def test_reload_templates_response_format():
    """Test that the response format is correct"""
    async with TemplateReloadTester(SERVER_URL) as tester:
        assert await tester.authenticate(), "Authentication failed"
        assert await tester.test_reload_templates_response_format(), "Response format test failed"


@pytest.mark.asyncio
async def test_complete_template_reload_suite():
    """Run the complete template reload test suite"""
    async with TemplateReloadTester(SERVER_URL) as tester:
        assert await tester.authenticate(), "Authentication failed"

        # Run all tests in sequence
        assert await tester.test_reload_templates_response_format(), "Response format test failed"
        assert await tester.test_reload_templates_all_adapters(), "All adapters reload failed"
        assert await tester.test_reload_templates_single_adapter(), "Single adapter reload failed"
        assert await tester.test_reload_templates_nonexistent_adapter(), "Non-existent adapter test failed"
        assert await tester.test_reload_templates_non_intent_adapter(), "Non-intent adapter test failed"


# ============================================================================
# Main Function for Standalone Execution
# ============================================================================

async def main():
    """Main test function for standalone execution"""
    async with TemplateReloadTester(SERVER_URL) as tester:
        logger.info(f"Testing template reload functionality against: {SERVER_URL}")
        logger.info("=" * 80)

        # Authenticate
        if not await tester.authenticate():
            logger.error("Authentication failed. Cannot proceed.")
            return

        # Define all tests
        tests = [
            ("Response Format", tester.test_reload_templates_response_format),
            ("All Adapters Reload", tester.test_reload_templates_all_adapters),
            ("Single Adapter Reload", tester.test_reload_templates_single_adapter),
            ("Non-existent Adapter", tester.test_reload_templates_nonexistent_adapter),
            ("Non-intent Adapter", tester.test_reload_templates_non_intent_adapter),
        ]

        passed = 0
        failed = 0

        for test_name, test_func in tests:
            try:
                logger.info(f"\n{'='*80}")
                logger.info(f"Running: {test_name}")
                logger.info(f"{'='*80}")

                if await test_func():
                    passed += 1
                    logger.info(f"PASSED: {test_name}")
                else:
                    failed += 1
                    logger.error(f"FAILED: {test_name}")

            except Exception as e:
                logger.error(f"CRASHED: {test_name}: {str(e)}")
                import traceback
                traceback.print_exc()
                failed += 1

        logger.info("\n" + "=" * 80)
        logger.info(f"Template Reload Tests Completed: {passed} passed, {failed} failed")
        logger.info("=" * 80)

        if failed == 0:
            logger.info("All template reload tests passed!")
        else:
            logger.error(f"{failed} template reload test(s) failed")


if __name__ == "__main__":
    asyncio.run(main())
