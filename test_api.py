#!/usr/bin/env python3
"""
Test script for the hierarchical classification API.
Run this after starting the Docker container to verify it's working correctly.
"""

import requests
import json
import sys

API_BASE_URL = "http://localhost:8001"

def test_health():
    """Test the health endpoint."""
    print("Testing /health endpoint...")
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        response.raise_for_status()
        result = response.json()
        assert result.get("status") == "ok", f"Unexpected health status: {result}"
        print("✓ Health check passed")
        return True
    except Exception as e:
        print(f"✗ Health check failed: {e}")
        return False

def test_predict():
    """Test the predict endpoint with sample text."""
    print("\nTesting /predict endpoint...")
    
    test_cases = [
        {
            "name": "Tax-related complaint",
            "text": "Прошу разобраться с начислением штрафа по налогам",
            "expected_category_keywords": ["НАЛОГ", "ТАМ"]
        },
        {
            "name": "Healthcare complaint",
            "text": "В больнице не оказали медицинскую помощь",
            "expected_category_keywords": ["ЗДРАВООХРАН"]
        },
        {
            "name": "Education complaint",
            "text": "Отказали в зачислении ребенка в школу",
            "expected_category_keywords": ["ОБРАЗОВАН"]
        }
    ]
    
    all_passed = True
    
    for test_case in test_cases:
        print(f"\n  Test: {test_case['name']}")
        print(f"  Text: {test_case['text']}")
        
        try:
            payload = {
                "text": test_case["text"],
                "topk_cat": 3,
                "topk_sub": 5
            }
            
            response = requests.post(
                f"{API_BASE_URL}/predict",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            # Verify response structure
            assert "predictions" in result, "Response missing 'predictions' field"
            assert len(result["predictions"]) > 0, "No predictions returned"
            
            top_category = result["predictions"][0]["category"]
            top_proba = result["predictions"][0]["proba"]
            
            print(f"  → Top category: {top_category} (prob: {top_proba:.4f})")
            
            # Display subissues
            if result["predictions"][0].get("subissues"):
                print(f"  → Subissues:")
                for sub in result["predictions"][0]["subissues"][:3]:
                    print(f"     - {sub['label']} (prob: {sub['proba']:.4f})")
            
            print(f"  ✓ Test passed")
            
        except Exception as e:
            print(f"  ✗ Test failed: {e}")
            all_passed = False
    
    return all_passed

def test_invalid_inputs():
    """Test API error handling."""
    print("\nTesting error handling...")
    
    test_cases = [
        {
            "name": "Empty text",
            "payload": {"text": ""},
            "expected_status": 400
        },
        {
            "name": "Missing text field",
            "payload": {},
            "expected_status": 400
        },
        {
            "name": "Invalid JSON",
            "payload": "not a json",
            "expected_status": 400
        }
    ]
    
    all_passed = True
    
    for test_case in test_cases:
        print(f"\n  Test: {test_case['name']}")
        
        try:
            if isinstance(test_case["payload"], str):
                response = requests.post(
                    f"{API_BASE_URL}/predict",
                    data=test_case["payload"],
                    headers={"Content-Type": "application/json"},
                    timeout=10
                )
            else:
                response = requests.post(
                    f"{API_BASE_URL}/predict",
                    json=test_case["payload"],
                    timeout=10
                )
            
            if response.status_code == test_case["expected_status"]:
                print(f"  ✓ Correctly returned {response.status_code}")
            else:
                print(f"  ✗ Expected {test_case['expected_status']}, got {response.status_code}")
                all_passed = False
                
        except Exception as e:
            print(f"  ✗ Test failed with exception: {e}")
            all_passed = False
    
    return all_passed

def main():
    """Run all tests."""
    print("=" * 60)
    print("Hierarchical Classification API Test Suite")
    print("=" * 60)
    
    results = []
    
    # Test health endpoint
    results.append(("Health Check", test_health()))
    
    # Test predict endpoint
    results.append(("Prediction Tests", test_predict()))
    
    # Test error handling
    results.append(("Error Handling", test_invalid_inputs()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{name}: {status}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("All tests passed! 🎉")
        sys.exit(0)
    else:
        print("Some tests failed. Please check the output above.")
        sys.exit(1)

if __name__ == "__main__":
    main()

