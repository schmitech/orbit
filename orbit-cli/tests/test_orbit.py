#!/usr/bin/env python3
"""
ORBIT Manager Test Suite
=========================================

This script runs tests for the ORBIT Manager utility.
It tests the API key management functionality.

Usage:
  python test_orbit.py
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
import datetime
from pathlib import Path

# Add the src directory to the Python path
current_dir = Path(__file__).parent
src_dir = current_dir.parent / "src"
sys.path.insert(0, str(src_dir))

# Import the module after adding the path
from orbit import DbApiKeyManager

class TestOrbitManager(unittest.TestCase):
    """Test cases for the ORBIT Manager utility"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment before running tests"""
        # Create temporary directory for test database and files
        cls.test_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.test_dir, "test_api_keys.db")
        
        # Use the actual prompts directory
        cls.prompts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "prompts")
        if not os.path.exists(cls.prompts_dir):
            raise RuntimeError(f"Prompts directory not found at {cls.prompts_dir}")
        
        # Create test config
        cls.config = {
            "database": {
                "engine": "sqlite",
                "connection": {
                    "sqlite": {
                        "database": cls.db_path
                    }
                }
            },
            "application": {
                "log_level": "INFO"
            }
        }
        
        # Write config file
        cls.config_path = os.path.join(cls.test_dir, "config.yaml")
        with open(cls.config_path, 'w') as f:
            import yaml
            yaml.dump(cls.config, f)
        
        # Set up paths to actual prompt files
        cls.city_prompt = os.path.join(cls.prompts_dir, "examples", "city", "city-assistant-normal-prompt.txt")
        cls.activity_prompt = os.path.join(cls.prompts_dir, "examples", "activity", "activity-assistant-normal-prompt.txt")
        
        # Verify prompt files exist
        if not os.path.exists(cls.city_prompt):
            raise RuntimeError(f"City prompt file not found at {cls.city_prompt}")
        if not os.path.exists(cls.activity_prompt):
            raise RuntimeError(f"Activity prompt file not found at {cls.activity_prompt}")
        
        # Initialize manager
        cls.manager = DbApiKeyManager(config_file=cls.config_path)
        
        # Initialize IDs as class variables
        cls.city_prompt_id = None
        cls.activity_prompt_id = None
        cls.city_api_key = None
        cls.activity_api_key = None
    
    def setUp(self):
        """Set up each test"""
        # Ensure we have the IDs from previous tests
        if not hasattr(self, 'city_prompt_id'):
            self.city_prompt_id = self.__class__.city_prompt_id
        if not hasattr(self, 'activity_prompt_id'):
            self.activity_prompt_id = self.__class__.activity_prompt_id
        if not hasattr(self, 'city_api_key'):
            self.city_api_key = self.__class__.city_api_key
        if not hasattr(self, 'activity_api_key'):
            self.activity_api_key = self.__class__.activity_api_key
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test environment after running tests"""
        # Remove temporary directory and all its contents
        shutil.rmtree(cls.test_dir)
    
    def test_01_create_city_prompt(self):
        """Test creating a city assistant prompt"""
        with open(self.city_prompt, 'r') as f:
            prompt_text = f.read()
        
        result = self.manager.create_prompt(
            name="City Assistant",
            prompt_text=prompt_text,
            version="1.0"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "City Assistant")
        self.assertEqual(result["version"], "1.0")
        self.__class__.city_prompt_id = result["id"]  # Store as class variable
    
    def test_02_create_activity_prompt(self):
        """Test creating an activity assistant prompt"""
        with open(self.activity_prompt, 'r') as f:
            prompt_text = f.read()
        
        result = self.manager.create_prompt(
            name="Activity Assistant",
            prompt_text=prompt_text,
            version="1.0"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Activity Assistant")
        self.assertEqual(result["version"], "1.0")
        self.__class__.activity_prompt_id = result["id"]  # Store as class variable
    
    def test_03_list_prompts(self):
        """Test listing all prompts"""
        prompts = self.manager.list_prompts()
        self.assertIsInstance(prompts, list)
        self.assertTrue(len(prompts) >= 2)
        self.assertTrue(any(p["id"] == self.city_prompt_id for p in prompts))
        self.assertTrue(any(p["id"] == self.activity_prompt_id for p in prompts))
    
    def test_04_get_prompt(self):
        """Test getting a specific prompt"""
        prompt = self.manager.get_prompt(self.city_prompt_id)
        self.assertIsNotNone(prompt)
        self.assertEqual(prompt["id"], self.city_prompt_id)
        self.assertEqual(prompt["name"], "City Assistant")
    
    def test_05_update_prompt(self):
        """Test updating a prompt"""
        with open(self.city_prompt, 'r') as f:
            updated_text = f.read() + "\nUpdated with additional information."
        
        result = self.manager.update_prompt(
            prompt_id=self.city_prompt_id,
            prompt_text=updated_text,
            version="1.1"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["version"], "1.1")
        self.assertIn("Updated with additional information", result["prompt_text"])
    
    def test_06_create_city_api_key(self):
        """Test creating an API key for city assistant"""
        result = self.manager.create_api_key(
            collection_name="city_data",
            client_name="City Assistant Client",
            notes="For city information queries",
            prompt_id=self.city_prompt_id
        )
        self.assertIsNotNone(result)
        self.assertIn("api_key", result)
        self.__class__.city_api_key = result["api_key"]  # Store as class variable
    
    def test_07_create_activity_api_key(self):
        """Test creating an API key for activity assistant"""
        result = self.manager.create_api_key(
            collection_name="activity_data",
            client_name="Activity Assistant Client",
            notes="For activity recommendations",
            prompt_id=self.activity_prompt_id
        )
        self.assertIsNotNone(result)
        self.assertIn("api_key", result)
        self.__class__.activity_api_key = result["api_key"]  # Store as class variable
    
    def test_08_list_api_keys(self):
        """Test listing all API keys"""
        keys = self.manager.list_api_keys()
        self.assertIsInstance(keys, list)
        self.assertTrue(len(keys) >= 2)
        self.assertTrue(any(k["api_key"] == self.city_api_key for k in keys))
        self.assertTrue(any(k["api_key"] == self.activity_api_key for k in keys))
    
    def test_09_get_api_key_status(self):
        """Test getting API key status"""
        status = self.manager.get_api_key_status(self.city_api_key)
        self.assertIsNotNone(status)
        self.assertEqual(status["api_key"], self.city_api_key)
        self.assertTrue(status["active"])
        self.assertEqual(status["collection_name"], "city_data")
    
    def test_10_test_api_key(self):
        """Test testing an API key"""
        result = self.manager.test_api_key(self.city_api_key)
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "success")
    
    def test_11_get_prompt_for_api_key(self):
        """Test getting prompt for an API key"""
        prompt = self.manager.get_prompt_for_api_key(self.city_api_key)
        self.assertIsNotNone(prompt)
        self.assertEqual(prompt["id"], self.city_prompt_id)
        self.assertEqual(prompt["name"], "City Assistant")
    
    def test_12_deactivate_api_key(self):
        """Test deactivating an API key"""
        result = self.manager.deactivate_api_key(self.city_api_key)
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "success")
        
        # Verify deactivation
        status = self.manager.get_api_key_status(self.city_api_key)
        self.assertFalse(status["active"])
    
    def test_13_delete_api_key(self):
        """Test deleting an API key"""
        # First, delete the API key (cascade will handle the prompt association)
        result = self.manager.delete_api_key(self.city_api_key)
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "success")
        
        # Verify deletion
        keys = self.manager.list_api_keys()
        self.assertFalse(any(k["api_key"] == self.city_api_key for k in keys))
    
    def test_14_delete_prompt(self):
        """Test deleting a prompt"""
        # First, delete any API keys associated with this prompt
        keys = self.manager.list_api_keys()
        for key in keys:
            if key.get("prompt_id") == self.city_prompt_id:
                self.manager.delete_api_key(key["api_key"])
        
        # Then delete the prompt
        result = self.manager.delete_prompt(self.city_prompt_id)
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "success")
        
        # Verify deletion
        prompts = self.manager.list_prompts()
        self.assertFalse(any(p["id"] == self.city_prompt_id for p in prompts))

def generate_html_report(results):
    """Generate an HTML report of test results"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Orbit API Key Manager Test Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background-color: #f5f5f5; padding: 20px; border-radius: 5px; }}
        .summary {{ margin: 20px 0; padding: 15px; border-radius: 5px; }}
        .success {{ background-color: #dff0d8; color: #3c763d; }}
        .failure {{ background-color: #f2dede; color: #a94442; }}
        .test-case {{ margin: 10px 0; padding: 10px; border: 1px solid #ddd; border-radius: 5px; }}
        .test-case h3 {{ margin: 0 0 10px 0; }}
        .test-case pre {{ background-color: #f8f8f8; padding: 10px; border-radius: 3px; overflow-x: auto; }}
        .timestamp {{ color: #666; font-size: 0.9em; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Orbit API Key Manager Test Report</h1>
        <p class="timestamp">Generated on: {timestamp}</p>
    </div>
    
    <div class="summary {results['status']}">
        <h2>Test Summary</h2>
        <p>Total Tests: {results['total']}</p>
        <p>Passed: {results['passed']}</p>
        <p>Failed: {results['failed']}</p>
        <p>Errors: {results['errors']}</p>
        <p>Status: {results['status'].upper()}</p>
    </div>
    
    <h2>Test Cases</h2>
"""

    for test in results['tests']:
        status_class = 'success' if test['status'] == 'passed' else 'failure'
        html += f"""
    <div class="test-case {status_class}">
        <h3>{test['name']}</h3>
        <p>Status: {test['status'].upper()}</p>
        <p>Duration: {test['duration']:.3f}s</p>
"""
        if test['status'] != 'passed':
            html += f"""
        <pre>{test['error']}</pre>
"""
        html += """
    </div>
"""

    html += """
</body>
</html>
"""
    return html

def main():
    """Run the test suite and generate a report"""
    # Create a test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestOrbitManager)
    
    # Create a test runner that collects results
    class ResultCollector(unittest.TestResult):
        def __init__(self):
            super().__init__()
            self.test_results = []
            self.start_time = None
            self.end_time = None
        
        def startTest(self, test):
            self.start_time = datetime.datetime.now()
            super().startTest(test)
        
        def stopTest(self, test):
            self.end_time = datetime.datetime.now()
            duration = (self.end_time - self.start_time).total_seconds()
            
            status = 'passed'
            error = None
            
            if test in self.failures:
                status = 'failed'
                error = self.failures[test][1]
            elif test in self.errors:
                status = 'error'
                error = self.errors[test][1]
            
            self.test_results.append({
                'name': test._testMethodName,
                'status': status,
                'duration': duration,
                'error': error
            })
    
    # Run the tests
    result = ResultCollector()
    suite.run(result)
    
    # Prepare results for the report
    report_data = {
        'total': len(result.test_results),
        'passed': len([t for t in result.test_results if t['status'] == 'passed']),
        'failed': len([t for t in result.test_results if t['status'] == 'failed']),
        'errors': len([t for t in result.test_results if t['status'] == 'error']),
        'status': 'success' if result.wasSuccessful() else 'failure',
        'tests': result.test_results
    }
    
    # Generate and save the HTML report
    report_dir = os.path.join(os.path.dirname(__file__), 'test_reports')
    os.makedirs(report_dir, exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = os.path.join(report_dir, f'test_report_{timestamp}.html')
    
    with open(report_file, 'w') as f:
        f.write(generate_html_report(report_data))
    
    print(f"\nTest report generated: {report_file}")
    
    # Also print a summary to the console
    print("\nTest Summary:")
    print(f"Total Tests: {report_data['total']}")
    print(f"Passed: {report_data['passed']}")
    print(f"Failed: {report_data['failed']}")
    print(f"Errors: {report_data['errors']}")
    print(f"Status: {report_data['status'].upper()}")
    
    # Return non-zero exit code if tests failed
    return 0 if result.wasSuccessful() else 1

if __name__ == "__main__":
    sys.exit(main()) 