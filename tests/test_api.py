import pytest
import requests
import time
import os
import secrets
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

@pytest.fixture(scope="module")
def homebox_container():
    # Generate a random pepper for the session
    pepper = secrets.token_urlsafe(36)
    
    container = DockerContainer("ghcr.io/sysadminsmedia/homebox:latest")
    container.with_env("HBOX_LOG_LEVEL", "info")
    container.with_env("HBOX_AUTH_API_KEY_PEPPER", pepper)
    container.with_exposed_ports(7745)
    
    with container as c:
        # Wait until the container logs show it's ready, or we just poll the root endpoint
        port = c.get_exposed_port(7745)
        host = c.get_container_host_ip()
        
        base_url = f"http://{host}:{port}"
        
        # Simple polling to ensure container is ready
        ready = False
        for _ in range(30):
            try:
                response = requests.get(base_url)
                if response.status_code == 200:
                    ready = True
                    break
            except requests.exceptions.ConnectionError:
                pass
            time.sleep(1)
            
        if not ready:
            raise Exception("HomeBox container failed to start in time.")
            
        yield base_url

@pytest.fixture(scope="module")
def auth_headers(homebox_container):
    base_url = homebox_container
    
    # 1. Register a test user
    register_data = {
        "email": "tester@example.com",
        "password": "securepassword123",
        "name": "Test User"
    }
    requests.post(f"{base_url}/api/v1/users/register", json=register_data)
    
    # 2. Login to get token
    login_data = {
        "username": "tester@example.com",
        "password": "securepassword123"
    }
    response = requests.post(f"{base_url}/api/v1/users/login", json=login_data)
    response.raise_for_status()
    
    token = response.json().get("token")
    return {
        "Authorization": token,
        "Content-Type": "application/json"
    }

def test_root_endpoint(homebox_container):
    response = requests.get(homebox_container)
    assert response.status_code == 200

def test_create_and_list_entity(homebox_container, auth_headers):
    # Create an entity
    entity_data = {
        "name": "Test Laptop",
        "description": "A laptop for testing",
        "fields": [
            {"name": "Manufacturer", "type": "text", "value": "TestCorp"}
        ]
    }
    
    create_resp = requests.post(f"{homebox_container}/api/v1/entities", json=entity_data, headers=auth_headers)
    assert create_resp.status_code == 201
    created_entity = create_resp.json()
    assert "id" in created_entity
    entity_id = created_entity["id"]
    assert created_entity["name"] == "Test Laptop"
    
    # List entities
    list_resp = requests.get(f"{homebox_container}/api/v1/entities", headers=auth_headers)
    assert list_resp.status_code == 200
    items = list_resp.json().get("items", [])
    
    # Find our entity in the list
    found = next((item for item in items if item["id"] == entity_id), None)
    assert found is not None
    assert found["name"] == "Test Laptop"
