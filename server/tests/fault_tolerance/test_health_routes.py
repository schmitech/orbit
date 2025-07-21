"""
Tests for Health Routes with Focus on Circuit Breaker History
============================================================

This module tests the health monitoring endpoints, particularly the new
adapter history endpoints that provide detailed observability data.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
from fastapi import FastAPI, Request
import sys
import os

# Add server directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../'))

from routes.health_routes import create_health_router, get_adapter_manager, get_adapter_manager_optional
from services.parallel_adapter_executor import SimpleCircuitBreaker, CircuitState


class TestHealthRoutes:
    """Test health monitoring routes"""

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app with health routes"""
        app = FastAPI()
        health_router = create_health_router()
        app.include_router(health_router)
        return app

    @pytest.fixture
    def client(self, app):
        """Create a test client"""
        return TestClient(app)

    @pytest.fixture
    def mock_circuit_breaker(self):
        """Create a mock circuit breaker with test data"""
        cb = SimpleCircuitBreaker(
            adapter_name="test-adapter",
            failure_threshold=5,
            recovery_timeout=30,
            success_threshold=3
        )
        
        # Add some test history
        cb.stats.total_calls = 100
        cb.stats.total_successes = 85
        cb.stats.total_failures = 10
        cb.stats.timeout_calls = 5
        cb.stats.consecutive_failures = 0
        cb.stats.consecutive_successes = 10
        cb.stats.last_success_time = time.time() - 60
        cb.stats.last_failure_time = time.time() - 300
        
        # Add call history
        cb.stats.call_history = [
            {
                "timestamp": time.time() - 120,
                "outcome": "success",
                "execution_time": 0.5,
                "error": None
            },
            {
                "timestamp": time.time() - 90,
                "outcome": "failure",
                "execution_time": 10.0,
                "error": "Timeout"
            },
            {
                "timestamp": time.time() - 60,
                "outcome": "success",
                "execution_time": 0.3,
                "error": None
            }
        ]
        
        # Add state transitions
        cb.stats.state_transitions = [
            {
                "timestamp": time.time() - 1000,
                "from_state": "open",
                "to_state": "half_open",
                "reason": "Recovery timeout elapsed"
            },
            {
                "timestamp": time.time() - 800,
                "from_state": "half_open",
                "to_state": "closed",
                "reason": "Success threshold reached"
            }
        ]
        
        return cb

    @pytest.fixture
    def mock_parallel_executor(self, mock_circuit_breaker):
        """Create a mock parallel executor with circuit breakers"""
        executor = Mock()
        executor.circuit_breakers = {
            "test-adapter": mock_circuit_breaker,
            "another-adapter": mock_circuit_breaker
        }
        executor.get_health_status = Mock(return_value={
            "total_adapters": 2,
            "healthy_adapters": 2,
            "circuit_breakers": {
                "test-adapter": {"state": "closed"},
                "another-adapter": {"state": "closed"}
            }
        })
        executor.get_circuit_breaker_states = Mock(return_value={
            "test-adapter": {"state": "closed"},
            "another-adapter": {"state": "closed"}
        })
        return executor

    @pytest.fixture
    def mock_adapter_manager(self, mock_parallel_executor):
        """Create a mock adapter manager"""
        manager = Mock()
        manager.parallel_executor = mock_parallel_executor
        manager.get_health_status = Mock(return_value={
            "fault_tolerance_enabled": True,
            "total_adapters": 2,
            "healthy_adapters": 2,
            "circuit_breakers": {
                "test-adapter": {"state": "closed"},
                "another-adapter": {"state": "closed"}
            }
        })
        return manager

    def test_basic_health_check(self, client):
        """Test basic health check endpoint"""
        response = client.get("/health/")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}

    def test_get_adapter_health(self, client, app, mock_adapter_manager):
        """Test adapter health status endpoint"""
        # Mock the dependency
        app.dependency_overrides[get_adapter_manager] = lambda: mock_adapter_manager
        
        response = client.get("/health/adapters")
        assert response.status_code == 200
        
        data = response.json()
        assert data["fault_tolerance_enabled"] is True
        assert data["total_adapters"] == 2
        assert data["healthy_adapters"] == 2

    def test_get_adapter_history(self, client, app, mock_adapter_manager):
        """Test adapter history endpoint"""
        # Mock the dependency
        app.dependency_overrides[get_adapter_manager] = lambda: mock_adapter_manager
        
        response = client.get("/health/adapters/test-adapter/history")
        assert response.status_code == 200
        
        data = response.json()
        assert data["adapter_name"] == "test-adapter"
        assert data["current_state"] == "closed"
        
        # Check statistics
        stats = data["statistics"]
        assert stats["total_calls"] == 100
        assert stats["total_successes"] == 85
        assert stats["total_failures"] == 10
        assert stats["timeout_calls"] == 5
        assert stats["success_rate"] == 0.85
        assert stats["consecutive_successes"] == 10
        
        # Check history is limited
        assert len(data["call_history"]) <= 50
        assert len(data["state_transitions"]) <= 20
        
        # Check configuration
        config = data["configuration"]
        assert config["failure_threshold"] == 5
        assert config["recovery_timeout"] == 30
        assert config["success_threshold"] == 3
        assert config["max_recovery_timeout"] == 300.0

    def test_get_adapter_full_history(self, client, app, mock_adapter_manager):
        """Test adapter full history endpoint"""
        # Mock the dependency
        app.dependency_overrides[get_adapter_manager] = lambda: mock_adapter_manager
        
        response = client.get("/health/adapters/test-adapter/history/full")
        assert response.status_code == 200
        
        data = response.json()
        assert data["adapter_name"] == "test-adapter"
        assert "warning" in data
        assert "complete history" in data["warning"].lower()
        
        # Full history should include all data
        assert data["call_history"] == mock_adapter_manager.parallel_executor.circuit_breakers["test-adapter"].stats.call_history
        assert data["state_transitions"] == mock_adapter_manager.parallel_executor.circuit_breakers["test-adapter"].stats.state_transitions

    def test_adapter_history_not_found(self, client, app, mock_adapter_manager):
        """Test adapter history for non-existent adapter"""
        # Mock the dependency
        app.dependency_overrides[get_adapter_manager] = lambda: mock_adapter_manager
        
        response = client.get("/health/adapters/non-existent-adapter/history")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_adapter_history_no_parallel_executor(self, client, app):
        """Test adapter history when parallel executor is not available"""
        # Create adapter manager without parallel executor
        manager = Mock()
        manager.parallel_executor = None
        
        app.dependency_overrides[get_adapter_manager] = lambda: manager
        
        response = client.get("/health/adapters/test-adapter/history")
        assert response.status_code == 503
        assert "not available" in response.json()["detail"].lower()

    def test_reset_adapter_circuit(self, client, app, mock_adapter_manager):
        """Test reset circuit breaker endpoint"""
        # Make sure adapter manager doesn't have reset method (so it uses parallel executor)
        if hasattr(mock_adapter_manager, 'reset_circuit_breaker'):
            delattr(mock_adapter_manager, 'reset_circuit_breaker')
        
        # Add reset method to parallel executor
        mock_adapter_manager.parallel_executor.reset_circuit_breaker = Mock()
        
        app.dependency_overrides[get_adapter_manager] = lambda: mock_adapter_manager
        
        response = client.post("/health/adapters/test-adapter/reset")
        assert response.status_code == 200
        assert "reset" in response.json()["message"].lower()
        
        # Verify reset was called
        mock_adapter_manager.parallel_executor.reset_circuit_breaker.assert_called_once_with("test-adapter")

    def test_readiness_check(self, client, app, mock_adapter_manager):
        """Test readiness check endpoint"""
        app.dependency_overrides[get_adapter_manager_optional] = lambda: mock_adapter_manager
        
        response = client.get("/health/ready")
        assert response.status_code == 200
        
        data = response.json()
        assert data["ready"] is True
        assert data["healthy_ratio"] == 1.0
        assert data["healthy_adapters"] == 2
        assert data["total_adapters"] == 2

    def test_readiness_check_no_manager(self, client, app):
        """Test readiness check when no adapter manager is available"""
        app.dependency_overrides[get_adapter_manager_optional] = lambda: None
        
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["ready"] is False

    def test_system_status(self, client, app, mock_adapter_manager):
        """Test system status endpoint"""
        app.dependency_overrides[get_adapter_manager_optional] = lambda: mock_adapter_manager
        
        response = client.get("/health/system")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert data["fault_tolerance"]["enabled"] is True
        assert len(data["fault_tolerance"]["adapters"]) == 2

    def test_adapter_history_with_empty_history(self, client, app):
        """Test adapter history with empty call history"""
        # Create circuit breaker with no history
        cb = SimpleCircuitBreaker(adapter_name="empty-adapter", failure_threshold=5, recovery_timeout=30)
        
        executor = Mock()
        executor.circuit_breakers = {"empty-adapter": cb}
        
        manager = Mock()
        manager.parallel_executor = executor
        
        app.dependency_overrides[get_adapter_manager] = lambda: manager
        
        response = client.get("/health/adapters/empty-adapter/history")
        assert response.status_code == 200
        
        data = response.json()
        assert data["adapter_name"] == "empty-adapter"
        assert len(data["call_history"]) == 0
        assert len(data["state_transitions"]) == 0
        assert data["statistics"]["total_calls"] == 0

    @pytest.mark.asyncio
    async def test_adapter_history_error_handling(self, client, app):
        """Test error handling in adapter history endpoint"""
        # Create a circuit breaker that raises an error
        executor = Mock()
        executor.circuit_breakers = {}
        
        # Mock circuit_breakers to raise an exception when accessed
        type(executor).circuit_breakers = property(lambda self: (_ for _ in ()).throw(Exception("Test error")))
        
        manager = Mock()
        manager.parallel_executor = executor
        
        app.dependency_overrides[get_adapter_manager] = lambda: manager
        
        response = client.get("/health/adapters/test-adapter/history")
        assert response.status_code == 500
        assert "Internal server error" in response.json()["detail"]


class TestHealthRouteDependencies:
    """Test the dependency injection functions"""

    def test_get_adapter_manager_success(self):
        """Test successful adapter manager retrieval"""
        request = Mock()
        request.app.state.fault_tolerant_adapter_manager = Mock()
        
        manager = get_adapter_manager(request)
        assert manager == request.app.state.fault_tolerant_adapter_manager

    def test_get_adapter_manager_fallback(self):
        """Test fallback to regular adapter manager"""
        request = Mock()
        request.app.state.fault_tolerant_adapter_manager = None
        request.app.state.adapter_manager = Mock()
        
        manager = get_adapter_manager(request)
        assert manager == request.app.state.adapter_manager

    def test_get_adapter_manager_not_found(self):
        """Test when no adapter manager is available"""
        request = Mock()
        request.app.state.fault_tolerant_adapter_manager = None
        request.app.state.adapter_manager = None
        
        with pytest.raises(HTTPException) as exc_info:
            get_adapter_manager(request)
        
        assert exc_info.value.status_code == 503
        assert "not available" in exc_info.value.detail.lower()

    def test_get_adapter_manager_optional(self):
        """Test optional adapter manager retrieval"""
        request = Mock()
        request.app.state.fault_tolerant_adapter_manager = None
        request.app.state.adapter_manager = None
        
        manager = get_adapter_manager_optional(request)
        assert manager is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])