"""
Locust performance tests for the Orbit Inference Server.

This file contains performance tests for various endpoints including:
- Health checks
- Chat endpoints
- Admin endpoints
- Authentication endpoints

Run with: locust -f locustfile.py --host=http://localhost:3000
"""

import os
import random
import time
from locust import HttpUser, task, between, events
from urllib3.util import Retry
from requests.adapters import HTTPAdapter


PERF_API_KEY_ENV = "ORBIT_PERF_API_KEY"


def str_to_bool(val):
    if isinstance(val, bool):
        return val
    return val.lower() in ('true', '1', 'yes', 'on')


@events.init_command_line_parser.add_listener
def init_parser(parser):
    parser.add_argument("--connection-timeout", type=int, default=60, help="Connection timeout in seconds")
    parser.add_argument("--max-redirects", type=int, default=5, help="Maximum number of redirects allowed")
    parser.add_argument("--max-retries", type=int, default=3, help="Maximum number of retries")
    parser.add_argument("--retry-delay", type=float, default=1.0, help="Delay between retries in seconds")
    parser.add_argument("--http2", type=str_to_bool, default=False, help="Enable HTTP/2")
    parser.add_argument("--keep-alive", type=str_to_bool, default=True, help="Enable keep-alive connections")
    parser.add_argument("--max-keep-alive-requests", type=int, default=100, help="Maximum number of keep-alive requests per connection")
    parser.add_argument("--insecure", type=str_to_bool, default=False, help="Disable SSL verification")
    parser.add_argument("--ssl-verify", type=str_to_bool, default=True, help="Enable SSL verification")


def configure_client(user: HttpUser):
    """Configure the HTTP client based on custom command line options."""
    options = user.environment.parsed_options
    if not options:
        return
        
    # SSL verification
    if getattr(options, "insecure", False):
        user.client.verify = False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    elif hasattr(options, "ssl_verify"):
        user.client.verify = options.ssl_verify
        if not options.ssl_verify:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
    # Max redirects
    if hasattr(options, "max_redirects"):
        user.client.max_redirects = options.max_redirects
        
    # Timeout
    if hasattr(options, "connection_timeout"):
        timeout = options.connection_timeout
        original_request = user.client.request
        def request_with_timeout(*args, **kwargs):
            if 'timeout' not in kwargs:
                kwargs['timeout'] = timeout
            return original_request(*args, **kwargs)
        user.client.request = request_with_timeout

    # Retries
    retries = getattr(options, "max_retries", 3)
    retry_delay = getattr(options, "retry_delay", 1.0)
    if retries > 0:
        retry_strategy = Retry(
            total=retries,
            backoff_factor=retry_delay,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        user.client.mount("http://", adapter)
        user.client.mount("https://", adapter)
        
    # Warn if http2 is requested
    if getattr(options, "http2", False):
        print("⚠️ HTTP/2 requested but not supported by HTTP client. Falling back to HTTP/1.1.")


def get_perf_api_key():
    """Return the API key supplied by run_performance_tests.sh, if any."""
    return os.environ.get(PERF_API_KEY_ENV) or None


class OrbitInferenceServerUser(HttpUser):
    """
    Simulates a user interacting with the Orbit Inference Server.
    
    This user performs various operations including:
    - Health checks
    - Chat requests
    - Admin operations (if authenticated)
    """
    
    # Wait between 1-3 seconds between tasks
    wait_time = between(1, 3)
    
    def on_start(self):
        """Initialize user state when starting."""
        configure_client(self)
        self.api_key = get_perf_api_key()
        self.session_id = None
        self.user_id = None
        self.admin_token = None

        if self.api_key:
            self.client.headers.update({"X-API-Key": self.api_key})
        else:
            # Try to authenticate if auth is enabled
            self._try_authenticate()
    
    def _try_authenticate(self):
        """Attempt to authenticate the user."""
        try:
            # Try to create an API key (admin operation)
            api_key_data = {
                "name": f"perf_test_key_{int(time.time())}",
                "collections": ["test_collection"],
                "client_id": f"perf_test_client_{int(time.time())}",
                "notes": "Performance test API key"
            }
            
            response = self.client.post(
                "/admin/api-keys",
                json=api_key_data,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                self.api_key = response.json().get("api_key")
                self.client.headers.update({"X-API-Key": self.api_key})
                print(f"Successfully created API key: {self.api_key[:8]}...")
            else:
                print(f"Failed to create API key: {response.status_code}")
                
        except Exception as e:
            print(f"Authentication failed: {e}")
    
    @task(3)
    def health_check(self):
        """Test the health endpoint - high frequency."""
        with self.client.get("/health", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed: {response.status_code}")
    
    @task(2)
    def health_adapters(self):
        """Test the adapters health endpoint."""
        with self.client.get("/health/adapters", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Adapters health check failed: {response.status_code}")
    
    @task(2)
    def health_ready(self):
        """Test the readiness endpoint."""
        with self.client.get("/health/ready", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Readiness check failed: {response.status_code}")
    
    @task(1)
    def chat_request(self):
        """Test the main chat endpoint with MCP protocol."""
        if not self.api_key:
            return
            
        # Generate a unique session ID
        self.session_id = f"perf_session_{int(time.time())}_{random.randint(1000, 9999)}"
        
        chat_data = {
            "messages": [
                {
                    "role": "user",
                    "content": "Hello, this is a performance test message."
                }
            ],
            "stream": False
        }
        
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
            "X-Session-ID": self.session_id
        }
        
        with self.client.post("/v1/chat", json=chat_data, headers=headers, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Chat request failed: {response.status_code}")
    
    @task(1)
    def admin_api_keys_list(self):
        """Test listing API keys (admin endpoint)."""
        if not self.api_key:
            return
            
        with self.client.get("/admin/api-keys", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"API keys list failed: {response.status_code}")
    
    @task(1)
    def admin_prompts_list(self):
        """Test listing system prompts (admin endpoint)."""
        if not self.api_key:
            return
            
        with self.client.get("/admin/prompts", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Prompts list failed: {response.status_code}")


class HealthCheckUser(HttpUser):
    """
    Dedicated user for health check monitoring.
    
    This user only performs health checks to simulate monitoring systems.
    """
    
    wait_time = between(5, 10)  # Less frequent checks
    
    def on_start(self):
        """Initialize health check user."""
        configure_client(self)
        
    @task(1)
    def health_check(self):
        """Basic health check."""
        with self.client.get("/health", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed: {response.status_code}")
    
    @task(1)
    def health_ready(self):
        """Readiness check."""
        with self.client.get("/health/ready", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Readiness check failed: {response.status_code}")


class ChatUser(HttpUser):
    """
    Dedicated user for chat operations.
    
    This user focuses on chat requests to test chat endpoint performance.
    """
    
    wait_time = between(2, 5)
    
    def on_start(self):
        """Initialize chat user."""
        configure_client(self)
        self.api_key = get_perf_api_key()
        self.session_id = None
        if self.api_key:
            self.client.headers.update({"X-API-Key": self.api_key})
        else:
            self._try_get_api_key()
    
    def _try_get_api_key(self):
        """Try to get an existing API key."""
        try:
            # Try to list existing API keys
            response = self.client.get("/admin/api-keys")
            if response.status_code == 200:
                keys = response.json()
                if keys and len(keys) > 0:
                    self.api_key = keys[0].get("api_key")
                    self.client.headers.update({"X-API-Key": self.api_key})
        except Exception:
            pass
    
    @task(1)
    def chat_request(self):
        """Send a chat request."""
        if not self.api_key:
            return
            
        self.session_id = f"chat_user_{int(time.time())}_{random.randint(1000, 9999)}"
        
        chat_data = {
            "messages": [
                {
                    "role": "user",
                    "content": "This is a performance test chat message. Please respond briefly."
                }
            ],
            "stream": False
        }
        
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
            "X-Session-ID": self.session_id
        }
        
        with self.client.post("/v1/chat", json=chat_data, headers=headers, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Chat request failed: {response.status_code}")


# Event handlers for monitoring
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when a test is starting."""
    print("🚀 Starting Orbit Inference Server performance tests")
    print(f"Target host: {environment.host}")
    print(f"Number of users: {environment.runner.user_count if environment.runner else 'N/A'}")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when a test is stopping."""
    print("🏁 Orbit Inference Server performance tests completed")


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, response, context, exception, start_time, url, **kwargs):
    """Called for every request."""
    if exception:
        print(f"❌ Request failed: {name} - {exception}")
    elif response.status_code >= 400:
        print(f"⚠️  Request warning: {name} - {response.status_code}")
