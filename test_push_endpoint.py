#!/usr/bin/env python3
"""
Test script for /push endpoint validation
Tests that the endpoint properly rejects malicious input and accepts valid metrics
"""

import requests
import json

BASE_URL = "http://localhost:5000"

def test_valid_integer():
    """Test that valid integer values are accepted"""
    response = requests.post(f"{BASE_URL}/push", 
                           json={"name": "cpu_usage", "value": 42})
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "ok"
    assert data["added"]["value"] == 42
    print("✓ Valid integer accepted")

def test_valid_float():
    """Test that valid float values are accepted"""
    response = requests.post(f"{BASE_URL}/push", 
                           json={"name": "memory_usage", "value": 75.5})
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "ok"
    assert data["added"]["value"] == 75.5
    print("✓ Valid float accepted")

def test_reject_html_injection():
    """Test that HTML content is rejected"""
    response = requests.post(f"{BASE_URL}/push", 
                           json={"name": "test", "value": "<img src='malicious.jpg'>"})
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "number" in data["error"].lower()
    print("✓ HTML injection blocked")

def test_reject_script_injection():
    """Test that script tags are rejected (XSS prevention)"""
    response = requests.post(f"{BASE_URL}/push", 
                           json={"name": "xss", "value": "<script>alert('XSS')</script>"})
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    print("✓ Script injection blocked")

def test_reject_url_string():
    """Test that URL strings are rejected"""
    response = requests.post(f"{BASE_URL}/push", 
                           json={"name": "image", "value": "https://example.com/image.jpg"})
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    print("✓ URL string blocked")

def test_reject_empty_name():
    """Test that empty metric names are rejected"""
    response = requests.post(f"{BASE_URL}/push", 
                           json={"name": "", "value": 50})
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "name" in data["error"].lower()
    print("✓ Empty name blocked")

def test_reject_whitespace_name():
    """Test that whitespace-only names are rejected"""
    response = requests.post(f"{BASE_URL}/push", 
                           json={"name": "   ", "value": 50})
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    print("✓ Whitespace-only name blocked")

def test_reject_boolean():
    """Test that boolean values are rejected"""
    response = requests.post(f"{BASE_URL}/push", 
                           json={"name": "test", "value": True})
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    print("✓ Boolean value blocked")

def test_get_method_helpful():
    """Test that GET requests return helpful error message"""
    response = requests.get(f"{BASE_URL}/push")
    assert response.status_code == 405
    data = response.json()
    assert "error" in data
    assert "example" in data
    assert data["example"]["method"] == "POST"
    print("✓ GET request returns helpful message")

if __name__ == "__main__":
    print("Testing /push endpoint security and validation...\n")
    
    try:
        test_valid_integer()
        test_valid_float()
        test_reject_html_injection()
        test_reject_script_injection()
        test_reject_url_string()
        test_reject_empty_name()
        test_reject_whitespace_name()
        test_reject_boolean()
        test_get_method_helpful()
        
        print("\n✅ All tests passed!")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ Error running tests: {e}")
        exit(1)
