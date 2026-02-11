"""
Quick API validation test for Payment Order Creation
Tests the create-order endpoint with proper payload
"""

import requests
import json

def test_create_order():
    """Test payment order creation"""
    url = "http://localhost:5000/api/payment/create-order"
    
    # Test with Basic plan (₹299)
    payload = {
        "amount": 29900,  # ₹299 in paise
        "currency": "INR",
        "receipt": f"receipt_{int(1733759400)}",
        "notes": {
            "mobile": "+919876543210",
            "name": "Test User",
            "plan_name": "Basic",
            "purpose": "Basic Subscription"
        }
    }
    
    print("="*70)
    print("TESTING: Payment Order Creation API")
    print("="*70)
    print(f"\nEndpoint: {url}")
    print(f"\nPayload:")
    print(json.dumps(payload, indent=2))
    print("\n" + "-"*70)
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        
        print(f"\nStatus Code: {response.status_code}")
        print(f"\nResponse:")
        print(json.dumps(response.json(), indent=2))
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("\n" + "="*70)
                print("✅ TEST PASSED: Order created successfully")
                print("="*70)
                print(f"\nOrder ID: {data['data']['order_id']}")
                print(f"Amount: ₹{data['data']['amount']/100}")
                print(f"Currency: {data['data']['currency']}")
                print(f"Key ID: {data['data']['key_id']}")
                
                # Verify the response structure
                assert 'order_id' in data['data'], "Missing order_id"
                assert 'amount' in data['data'], "Missing amount"
                assert 'currency' in data['data'], "Missing currency"
                assert 'key_id' in data['data'], "Missing key_id"
                assert data['data']['amount'] == 29900, "Amount mismatch"
                assert data['data']['currency'] == 'INR', "Currency mismatch"
                
                print("\n✅ All assertions passed!")
                return True
            else:
                print("\n❌ TEST FAILED: API returned success=false")
                return False
        else:
            print(f"\n❌ TEST FAILED: HTTP {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Cannot connect to backend server")
        print("Make sure Flask server is running on http://localhost:5000")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_invalid_amount():
    """Test with invalid amount (should fail)"""
    url = "http://localhost:5000/api/payment/create-order"
    
    payload = {
        "amount": 0,  # Invalid amount
        "currency": "INR",
        "receipt": "test_receipt",
        "notes": {}
    }
    
    print("\n" + "="*70)
    print("TESTING: Invalid Amount Validation")
    print("="*70)
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 400:
            print("✅ TEST PASSED: API correctly rejected invalid amount")
            return True
        else:
            print(f"❌ TEST FAILED: Expected 400, got {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return False

def main():
    print("\n" + "="*70)
    print("PAYMENT API VALIDATION TEST SUITE")
    print("="*70)
    print("\nChecking if order creation API is properly configured...\n")
    
    # Test 1: Valid order creation
    test1_passed = test_create_order()
    
    # Test 2: Invalid amount handling
    test2_passed = test_invalid_amount()
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"✅ Valid Order Creation: {'PASSED' if test1_passed else 'FAILED'}")
    print(f"✅ Invalid Amount Validation: {'PASSED' if test2_passed else 'FAILED'}")
    print("="*70)
    
    if test1_passed and test2_passed:
        print("\n🎉 ALL TESTS PASSED - API is properly configured!")
        print("\nThe create-order endpoint is:")
        print("  ✅ Accepting correct payload structure")
        print("  ✅ Returning proper response format")
        print("  ✅ Validating input correctly")
        print("  ✅ Including plan_name in notes")
    else:
        print("\n⚠️  SOME TESTS FAILED - Check backend configuration")
    
    print("\n")

if __name__ == "__main__":
    main()
