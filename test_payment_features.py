"""
Test script for new payment features:
- Error logging
- Payment failure handling
- Receipt generation
- Payment analytics
"""

import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:5000"

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def test_payment_failure():
    """Test payment failure logging endpoint"""
    print_section("TEST: Payment Failure Logging")
    
    url = f"{BASE_URL}/api/payment/failure"
    payload = {
        "order_id": "order_test_failure_123",
        "error": {
            "code": "BAD_REQUEST_ERROR",
            "description": "Payment failed due to insufficient funds",
            "reason": "payment_failed",
            "step": "payment_authentication",
            "source": "customer"
        },
        "mobile": "+919876543210"
    }
    
    print(f"POST {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        print(f"\nStatus Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("✅ Payment failure logged successfully")
        else:
            print("❌ Failed to log payment failure")
    except Exception as e:
        print(f"❌ Error: {e}")

def test_receipt_generation():
    """Test receipt generation endpoint"""
    print_section("TEST: Receipt Generation")
    
    # Note: This will fail if there's no successful payment with this order_id
    # You need to replace with an actual order_id from your database
    order_id = "order_test_123"
    
    url = f"{BASE_URL}/api/payment/receipt/{order_id}"
    
    print(f"GET {url}")
    
    try:
        response = requests.get(url, timeout=10)
        print(f"\nStatus Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Receipt generated successfully")
            print(f"\nReceipt Data:")
            print(json.dumps(data, indent=2))
        elif response.status_code == 404:
            print(f"⚠️ Payment not found for order: {order_id}")
            print("💡 TIP: Replace 'order_id' with actual order from successful payment")
        else:
            print(f"❌ Error: {response.json()}")
    except Exception as e:
        print(f"❌ Error: {e}")

def test_payment_analytics():
    """Test payment analytics endpoint"""
    print_section("TEST: Payment Analytics")
    
    url = f"{BASE_URL}/api/payment/analytics?days=30"
    
    print(f"GET {url}")
    
    try:
        response = requests.get(url, timeout=10)
        print(f"\nStatus Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("✅ Analytics retrieved successfully")
        else:
            print("❌ Failed to retrieve analytics")
    except Exception as e:
        print(f"❌ Error: {e}")

def test_payment_status():
    """Test payment status endpoint"""
    print_section("TEST: Payment Status")
    
    order_id = "order_test_123"
    url = f"{BASE_URL}/api/payment/status/{order_id}"
    
    print(f"GET {url}")
    
    try:
        response = requests.get(url, timeout=10)
        print(f"\nStatus Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("✅ Payment status retrieved successfully")
        elif response.status_code == 404:
            print(f"⚠️ Payment not found for order: {order_id}")
        else:
            print("❌ Failed to retrieve payment status")
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    print("\n" + "="*60)
    print("  PAYMENT FEATURES TEST SUITE")
    print("  Testing Enhanced Payment Endpoints")
    print("="*60)
    print(f"Base URL: {BASE_URL}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test all features
    test_payment_failure()
    test_payment_analytics()
    test_payment_status()
    test_receipt_generation()
    
    print("\n" + "="*60)
    print("  TEST SUITE COMPLETE")
    print("="*60)
    print("\n📝 NOTES:")
    print("  - Receipt test requires a successful payment order_id")
    print("  - Analytics shows data from last 30 days")
    print("  - Payment failure logging works independently")
    print("  - Check backend console for detailed error logs")
    print("\n")

if __name__ == "__main__":
    main()
