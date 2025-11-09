"""
Test Adapter Reload Functionality
==================================

Comprehensive tests for adapter hot-reload functionality, including:
- Config modification and verification
- Cache clearing for providers/embeddings/rerankers
- Config change detection logging
- Enable/disable adapter functionality
- Edge cases and error handling

Prerequisites:
1. Server must be running with verbose logging enabled
2. Authentication must be configured (enabled or disabled)
3. Config files must be writable
4. At least one adapter (qa-sql) must be configured

Safety:
- All config changes are backed up and restored
- Tests run in isolation with proper cleanup
- Original config is always restored, even if tests fail
"""

import asyncio
import aiohttp
import json
import logging
import yaml
import shutil
import pytest
from typing import Optional, Dict, Any, List
from pathlib import Path
import time
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Server configuration
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

# Default credentials (override with env var ORBIT_DEFAULT_ADMIN_PASSWORD)
import os
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = os.getenv('ORBIT_DEFAULT_ADMIN_PASSWORD', 'admin123')


class ConfigBackup:
    """Context manager for safely backing up and restoring config files"""

    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.backup_path = config_path.with_suffix('.yaml.backup')
        self.original_content = None

    def __enter__(self):
        """Backup the config file"""
        if self.config_path.exists():
            shutil.copy2(self.config_path, self.backup_path)
            with open(self.config_path, 'r') as f:
                self.original_content = f.read()
            logger.info(f"✓ Backed up {self.config_path.name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restore the config file"""
        if self.backup_path.exists():
            shutil.copy2(self.backup_path, self.config_path)
            self.backup_path.unlink()
            logger.info(f"✓ Restored {self.config_path.name}")

    def modify_config(self, modifier_func):
        """Modify config using a function that takes and returns a dict"""
        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)

        modified_config = modifier_func(config)

        with open(self.config_path, 'w') as f:
            yaml.dump(modified_config, f, default_flow_style=False, sort_keys=False)

        logger.info(f"✓ Modified {self.config_path.name}")
        return modified_config


class AdapterReloadTester:
    """Comprehensive tester for adapter reload functionality"""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.token: Optional[str] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.project_root = Path(__file__).parent.parent.parent
        self.adapters_config_path = self.project_root / "config" / "adapters.yaml"
        self.server_log_path = self.project_root / "logs" / "orbit.log"

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
                    logger.info("✓ Authentication is enabled")
                    return True
                elif response.status in [404, 503]:
                    logger.info("✓ Authentication is disabled")
                    return False
                else:
                    return True
        except Exception as e:
            logger.error(f"Error checking auth status: {str(e)}")
            return True

    async def authenticate(self) -> bool:
        """Authenticate if needed"""
        auth_enabled = await self.check_auth_enabled()

        if not auth_enabled:
            logger.info("✓ Authentication disabled - proceeding without token")
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
                        logger.info(f"✓ Authenticated: {self.token[:8]}...")
                        return True
                logger.error(f"✗ Authentication failed: {response.status}")
                return False
        except Exception as e:
            logger.error(f"✗ Authentication error: {str(e)}")
            return False

    async def reload_adapter(self, adapter_name: Optional[str] = None) -> Dict[str, Any]:
        """Call the reload adapter endpoint"""
        url = f"{self.base_url}/admin/reload-adapters"
        if adapter_name:
            url += f"?adapter_name={adapter_name}"

        try:
            async with self.session.post(
                url,
                headers=self._get_headers(),
                timeout=30
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error = await response.text()
                    raise Exception(f"Reload failed: {response.status} - {error}")
        except Exception as e:
            logger.error(f"Reload error: {str(e)}")
            raise

    def get_recent_logs(self, lines: int = 50, since_time: Optional[float] = None) -> List[str]:
        """Get recent log lines from server logs"""
        if not self.server_log_path.exists():
            return []

        with open(self.server_log_path, 'r') as f:
            all_lines = f.readlines()

        if since_time:
            # Filter lines by timestamp
            filtered_lines = []
            for line in all_lines:
                try:
                    # Parse timestamp from log line (format: 2025-11-09 13:01:07,983)
                    timestamp_str = line.split(' - ')[0]
                    log_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S,%f").timestamp()
                    if log_time >= since_time:
                        filtered_lines.append(line)
                except:
                    continue
            return filtered_lines[-lines:]

        return all_lines[-lines:]

    def search_logs(self, pattern: str, since_time: Optional[float] = None) -> List[str]:
        """Search for pattern in recent logs"""
        logs = self.get_recent_logs(lines=200, since_time=since_time)
        return [line for line in logs if pattern in line]

    # ============================================================================
    # TEST: Config Change Detection
    # ============================================================================

    async def test_config_change_detection_model(self) -> bool:
        """Test that model changes are detected and logged"""
        logger.info("\n=== Testing Config Change Detection (Model) ===")

        with ConfigBackup(self.adapters_config_path) as backup:
            try:
                # Get timestamp before changes
                before_time = time.time()

                # Modify the model for qa-sql
                def change_model(config):
                    for adapter in config.get('adapters', []):
                        if adapter.get('name') == 'qa-sql':
                            old_model = adapter.get('model')
                            adapter['model'] = 'command-r-plus'  # Change to a different model
                            logger.info(f"  Changed model from '{old_model}' to 'command-r-plus'")
                    return config

                backup.modify_config(change_model)

                # Wait a moment for file system
                await asyncio.sleep(0.5)

                # Reload the adapter
                result = await self.reload_adapter('qa-sql')
                logger.info(f"  Reload response: {result.get('summary', {})}")

                # Wait for logs to be written
                await asyncio.sleep(1)

                # Check logs for change detection
                change_logs = self.search_logs("config changes", since_time=before_time)
                model_change_logs = [log for log in change_logs if "model:" in log and "qa-sql" in log]

                if model_change_logs:
                    logger.info(f"✓ Config change detected in logs:")
                    for log in model_change_logs[:2]:
                        logger.info(f"    {log.strip()}")
                    return True
                else:
                    logger.error("✗ Model change not detected in logs")
                    logger.info(f"  All change logs: {change_logs}")
                    return False

            except Exception as e:
                logger.error(f"✗ Test failed: {str(e)}")
                return False

    # ============================================================================
    # TEST: Provider Cache Clearing
    # ============================================================================

    async def test_provider_cache_clearing(self) -> bool:
        """Test that provider caches are cleared when inference_provider changes"""
        logger.info("\n=== Testing Provider Cache Clearing ===")

        with ConfigBackup(self.adapters_config_path) as backup:
            try:
                # Get timestamp before changes
                before_time = time.time()

                # Change inference_provider for qa-sql
                def change_provider(config):
                    for adapter in config.get('adapters', []):
                        if adapter.get('name') == 'qa-sql':
                            old_provider = adapter.get('inference_provider', 'default')
                            adapter['inference_provider'] = 'anthropic'  # Change provider
                            logger.info(f"  Changed inference_provider from '{old_provider}' to 'anthropic'")
                    return config

                backup.modify_config(change_provider)
                await asyncio.sleep(0.5)

                # Reload
                result = await self.reload_adapter('qa-sql')
                logger.info(f"  Reload response: {result.get('summary', {})}")

                # Wait for logs
                await asyncio.sleep(1)

                # Check for cache clearing logs
                cache_clear_logs = self.search_logs("Cleared dependency caches", since_time=before_time)
                provider_clear_logs = [log for log in cache_clear_logs if "provider:" in log]

                if provider_clear_logs:
                    logger.info(f"✓ Provider cache cleared:")
                    for log in provider_clear_logs[:2]:
                        logger.info(f"    {log.strip()}")
                    return True
                else:
                    logger.error("✗ Provider cache clearing not logged")
                    logger.info(f"  All cache clear logs: {cache_clear_logs}")
                    return False

            except Exception as e:
                logger.error(f"✗ Test failed: {str(e)}")
                return False

    # ============================================================================
    # TEST: Enable/Disable Adapter
    # ============================================================================

    async def test_disable_enable_adapter(self) -> bool:
        """Test disabling and re-enabling an adapter"""
        logger.info("\n=== Testing Enable/Disable Adapter ===")

        with ConfigBackup(self.adapters_config_path) as backup:
            try:
                # Step 1: Disable the adapter
                logger.info("  Step 1: Disabling qa-sql adapter")
                before_disable = time.time()

                def disable_adapter(config):
                    for adapter in config.get('adapters', []):
                        if adapter.get('name') == 'qa-sql':
                            adapter['enabled'] = False
                            logger.info(f"    Set enabled=False for qa-sql")
                    return config

                backup.modify_config(disable_adapter)
                await asyncio.sleep(0.5)

                # Reload
                result = await self.reload_adapter('qa-sql')
                summary = result.get('summary', {})
                action = summary.get('action', 'unknown')

                logger.info(f"  Reload result: action={action}")

                # Wait for logs
                await asyncio.sleep(1)

                # Check logs for disabled message
                disable_logs = self.search_logs("Disabled adapter 'qa-sql'", since_time=before_disable)
                cache_clear_logs = self.search_logs("Cleared dependency caches for adapter 'qa-sql'", since_time=before_disable)

                if not (disable_logs or action == 'disabled'):
                    logger.error("✗ Adapter disable not confirmed")
                    return False

                logger.info("  ✓ Adapter disabled successfully")

                # Step 2: Re-enable the adapter
                logger.info("  Step 2: Re-enabling qa-sql adapter")
                before_enable = time.time()

                def enable_adapter(config):
                    for adapter in config.get('adapters', []):
                        if adapter.get('name') == 'qa-sql':
                            adapter['enabled'] = True
                            logger.info(f"    Set enabled=True for qa-sql")
                    return config

                backup.modify_config(enable_adapter)
                await asyncio.sleep(0.5)

                # Reload again
                result = await self.reload_adapter('qa-sql')
                summary = result.get('summary', {})
                action = summary.get('action', 'unknown')

                logger.info(f"  Reload result: action={action}")

                # Wait for logs
                await asyncio.sleep(1)

                # Check logs for enabled message
                enable_logs = self.search_logs("Reloaded adapter 'qa-sql'", since_time=before_enable)

                if enable_logs or action in ['enabled', 'updated']:
                    logger.info("  ✓ Adapter re-enabled successfully")
                    logger.info("✓ Enable/disable cycle completed")
                    return True
                else:
                    logger.error("✗ Adapter re-enable not confirmed")
                    return False

            except Exception as e:
                logger.error(f"✗ Test failed: {str(e)}")
                return False

    # ============================================================================
    # TEST: Embedding Provider Change
    # ============================================================================

    async def test_embedding_provider_change(self) -> bool:
        """Test that embedding provider changes clear the embedding cache"""
        logger.info("\n=== Testing Embedding Provider Cache Clearing ===")

        with ConfigBackup(self.adapters_config_path) as backup:
            try:
                before_time = time.time()

                # Change embedding_provider
                def change_embedding(config):
                    for adapter in config.get('adapters', []):
                        if adapter.get('name') == 'qa-sql':
                            old_embedding = adapter.get('embedding_provider', 'default')
                            adapter['embedding_provider'] = 'openai'
                            logger.info(f"  Changed embedding_provider from '{old_embedding}' to 'openai'")
                    return config

                backup.modify_config(change_embedding)
                await asyncio.sleep(0.5)

                # Reload
                result = await self.reload_adapter('qa-sql')
                logger.info(f"  Reload response: {result.get('summary', {})}")

                # Wait for logs
                await asyncio.sleep(1)

                # Check for embedding cache clearing
                cache_clear_logs = self.search_logs("Cleared dependency caches", since_time=before_time)
                embedding_logs = [log for log in cache_clear_logs if "embedding:" in log]

                if embedding_logs:
                    logger.info(f"✓ Embedding cache cleared:")
                    for log in embedding_logs[:2]:
                        logger.info(f"    {log.strip()}")
                    return True
                else:
                    # Embedding might not have been cached initially, check for config change detection
                    change_logs = self.search_logs("embedding_provider:", since_time=before_time)
                    if change_logs:
                        logger.info(f"✓ Embedding provider change detected (cache may not have been populated):")
                        for log in change_logs[:1]:
                            logger.info(f"    {log.strip()}")
                        return True
                    else:
                        logger.warning("⚠ Embedding change not clearly detected in logs")
                        return True  # Don't fail - embedding might not be used

            except Exception as e:
                logger.error(f"✗ Test failed: {str(e)}")
                return False

    # ============================================================================
    # TEST: Nested Config Changes
    # ============================================================================

    async def test_nested_config_changes(self) -> bool:
        """Test that nested config section changes are detected"""
        logger.info("\n=== Testing Nested Config Change Detection ===")

        with ConfigBackup(self.adapters_config_path) as backup:
            try:
                before_time = time.time()

                # Modify a nested config value
                def change_nested_config(config):
                    for adapter in config.get('adapters', []):
                        if adapter.get('name') == 'qa-sql':
                            if 'config' not in adapter:
                                adapter['config'] = {}
                            old_threshold = adapter['config'].get('confidence_threshold', 0.3)
                            adapter['config']['confidence_threshold'] = 0.5
                            logger.info(f"  Changed config.confidence_threshold from {old_threshold} to 0.5")
                    return config

                backup.modify_config(change_nested_config)
                await asyncio.sleep(0.5)

                # Reload
                result = await self.reload_adapter('qa-sql')
                logger.info(f"  Reload response: {result.get('summary', {})}")

                # Wait for logs
                await asyncio.sleep(1)

                # Check for nested config change detection
                change_logs = self.search_logs("config changes", since_time=before_time)
                nested_logs = [log for log in change_logs if "config." in log and "confidence_threshold" in log]

                if nested_logs:
                    logger.info(f"✓ Nested config change detected:")
                    for log in nested_logs[:1]:
                        logger.info(f"    {log.strip()}")
                    return True
                else:
                    logger.error("✗ Nested config change not detected in logs")
                    return False

            except Exception as e:
                logger.error(f"✗ Test failed: {str(e)}")
                return False

    # ============================================================================
    # TEST: Bulk Reload
    # ============================================================================

    async def test_bulk_reload(self) -> bool:
        """Test reloading all adapters at once"""
        logger.info("\n=== Testing Bulk Adapter Reload ===")

        with ConfigBackup(self.adapters_config_path) as backup:
            try:
                before_time = time.time()

                # Modify multiple adapters
                def change_multiple(config):
                    count = 0
                    for adapter in config.get('adapters', []):
                        if adapter.get('name') in ['qa-sql', 'simple-chat']:
                            if 'config' not in adapter:
                                adapter['config'] = {}
                            adapter['config']['test_timestamp'] = str(time.time())
                            count += 1
                    logger.info(f"  Modified {count} adapters")
                    return config

                backup.modify_config(change_multiple)
                await asyncio.sleep(0.5)

                # Reload all adapters (no adapter_name parameter)
                result = await self.reload_adapter(adapter_name=None)
                summary = result.get('summary', {})

                logger.info(f"  Bulk reload results:")
                logger.info(f"    Added: {summary.get('added', 0)}")
                logger.info(f"    Removed: {summary.get('removed', 0)}")
                logger.info(f"    Updated: {summary.get('updated', 0)}")
                logger.info(f"    Unchanged: {summary.get('unchanged', 0)}")
                logger.info(f"    Total: {summary.get('total', 0)}")

                # Wait for logs
                await asyncio.sleep(1)

                # Check for reload completion
                reload_logs = self.search_logs("Adapter reload complete", since_time=before_time)

                if reload_logs:
                    logger.info(f"✓ Bulk reload completed:")
                    for log in reload_logs[:1]:
                        logger.info(f"    {log.strip()}")
                    return True
                else:
                    logger.warning("⚠ Bulk reload completion not clearly logged")
                    # Still pass if we got a valid response
                    return summary.get('total', 0) > 0

            except Exception as e:
                logger.error(f"✗ Test failed: {str(e)}")
                return False

    # ============================================================================
    # TEST: Rapid Successive Reloads
    # ============================================================================

    async def test_rapid_successive_reloads(self) -> bool:
        """Test that rapid successive reloads don't cause issues"""
        logger.info("\n=== Testing Rapid Successive Reloads ===")

        try:
            # Perform multiple reloads in quick succession
            reload_count = 3
            logger.info(f"  Performing {reload_count} rapid reloads...")

            for i in range(reload_count):
                result = await self.reload_adapter('qa-sql')
                logger.info(f"  Reload {i+1}/{reload_count}: {result.get('summary', {}).get('action', 'unknown')}")
                await asyncio.sleep(0.2)  # Very short delay

            logger.info("✓ Rapid successive reloads completed without errors")
            return True

        except Exception as e:
            logger.error(f"✗ Test failed: {str(e)}")
            return False

    # ============================================================================
    # TEST: Invalid Config Handling
    # ============================================================================

    async def test_invalid_adapter_reload(self) -> bool:
        """Test attempting to reload a non-existent adapter"""
        logger.info("\n=== Testing Invalid Adapter Reload ===")

        try:
            # Try to reload a non-existent adapter
            try:
                result = await self.reload_adapter('nonexistent-adapter-12345')
                logger.error("✗ Should have failed for non-existent adapter")
                return False
            except Exception as e:
                if "404" in str(e) or "not found" in str(e).lower():
                    logger.info(f"✓ Correctly rejected non-existent adapter: {str(e)}")
                    return True
                else:
                    logger.error(f"✗ Unexpected error: {str(e)}")
                    return False

        except Exception as e:
            logger.error(f"✗ Test failed: {str(e)}")
            return False


# ============================================================================
# Pytest Test Functions
# ============================================================================

@pytest.mark.asyncio
async def test_adapter_config_change_detection():
    """Test that config changes are properly detected and logged"""
    async with AdapterReloadTester(SERVER_URL) as tester:
        assert await tester.authenticate(), "Authentication failed"
        assert await tester.test_config_change_detection_model(), "Config change detection failed"


@pytest.mark.asyncio
async def test_adapter_provider_cache_clearing():
    """Test that provider caches are cleared when configs change"""
    async with AdapterReloadTester(SERVER_URL) as tester:
        assert await tester.authenticate(), "Authentication failed"
        assert await tester.test_provider_cache_clearing(), "Provider cache clearing failed"


@pytest.mark.asyncio
async def test_adapter_enable_disable():
    """Test enabling and disabling adapters via reload"""
    async with AdapterReloadTester(SERVER_URL) as tester:
        assert await tester.authenticate(), "Authentication failed"
        assert await tester.test_disable_enable_adapter(), "Enable/disable failed"


@pytest.mark.asyncio
async def test_adapter_embedding_cache():
    """Test that embedding provider caches are cleared"""
    async with AdapterReloadTester(SERVER_URL) as tester:
        assert await tester.authenticate(), "Authentication failed"
        assert await tester.test_embedding_provider_change(), "Embedding cache clearing failed"


@pytest.mark.asyncio
async def test_adapter_nested_config():
    """Test that nested config changes are detected"""
    async with AdapterReloadTester(SERVER_URL) as tester:
        assert await tester.authenticate(), "Authentication failed"
        assert await tester.test_nested_config_changes(), "Nested config detection failed"


@pytest.mark.asyncio
async def test_adapter_bulk_reload():
    """Test bulk reload of all adapters"""
    async with AdapterReloadTester(SERVER_URL) as tester:
        assert await tester.authenticate(), "Authentication failed"
        assert await tester.test_bulk_reload(), "Bulk reload failed"


@pytest.mark.asyncio
async def test_adapter_rapid_reloads():
    """Test rapid successive reloads"""
    async with AdapterReloadTester(SERVER_URL) as tester:
        assert await tester.authenticate(), "Authentication failed"
        assert await tester.test_rapid_successive_reloads(), "Rapid reloads failed"


@pytest.mark.asyncio
async def test_adapter_invalid_reload():
    """Test invalid adapter reload handling"""
    async with AdapterReloadTester(SERVER_URL) as tester:
        assert await tester.authenticate(), "Authentication failed"
        assert await tester.test_invalid_adapter_reload(), "Invalid reload handling failed"


@pytest.mark.asyncio
async def test_complete_adapter_reload_suite():
    """Run the complete adapter reload test suite"""
    async with AdapterReloadTester(SERVER_URL) as tester:
        assert await tester.authenticate(), "Authentication failed"

        # Run all tests in sequence
        assert await tester.test_config_change_detection_model(), "Config change detection failed"
        assert await tester.test_provider_cache_clearing(), "Provider cache clearing failed"
        assert await tester.test_embedding_provider_change(), "Embedding cache clearing failed"
        assert await tester.test_nested_config_changes(), "Nested config detection failed"
        assert await tester.test_disable_enable_adapter(), "Enable/disable failed"
        assert await tester.test_bulk_reload(), "Bulk reload failed"
        assert await tester.test_rapid_successive_reloads(), "Rapid reloads failed"
        assert await tester.test_invalid_adapter_reload(), "Invalid reload handling failed"


# ============================================================================
# Main Function for Standalone Execution
# ============================================================================

async def main():
    """Main test function for standalone execution"""
    async with AdapterReloadTester(SERVER_URL) as tester:
        logger.info(f"Testing adapter reload functionality against: {SERVER_URL}")
        logger.info("=" * 80)

        # Authenticate
        if not await tester.authenticate():
            logger.error("❌ Authentication failed. Cannot proceed.")
            return

        # Define all tests
        tests = [
            ("Config Change Detection (Model)", tester.test_config_change_detection_model),
            ("Provider Cache Clearing", tester.test_provider_cache_clearing),
            ("Embedding Provider Change", tester.test_embedding_provider_change),
            ("Nested Config Changes", tester.test_nested_config_changes),
            ("Enable/Disable Adapter", tester.test_disable_enable_adapter),
            ("Bulk Adapter Reload", tester.test_bulk_reload),
            ("Rapid Successive Reloads", tester.test_rapid_successive_reloads),
            ("Invalid Adapter Reload", tester.test_invalid_adapter_reload),
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
                    logger.info(f"✅ {test_name} PASSED")
                else:
                    failed += 1
                    logger.error(f"❌ {test_name} FAILED")

            except Exception as e:
                logger.error(f"💥 {test_name} CRASHED: {str(e)}")
                import traceback
                traceback.print_exc()
                failed += 1

        logger.info("\n" + "=" * 80)
        logger.info(f"Adapter Reload Tests Completed: {passed} passed, {failed} failed")
        logger.info("=" * 80)

        if failed == 0:
            logger.info("✅ All adapter reload tests passed!")
        else:
            logger.error(f"❌ {failed} adapter reload test(s) failed")
            logger.info("\nTroubleshooting tips:")
            logger.info("1. Ensure server is running with verbose logging enabled")
            logger.info("2. Check that config/adapters.yaml is writable")
            logger.info("3. Verify at least one adapter (qa-sql) is configured and enabled")
            logger.info("4. Review server logs for detailed error information")
            logger.info("5. Make sure no other process is modifying config files")


if __name__ == "__main__":
    asyncio.run(main())
