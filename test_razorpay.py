"""
Test script for Razorpay payment integration
Run this to verify the integration is working
"""
import requests
import json

BASE_URL = 'http://localhost:5000'

def test_create_order():
    """Test creating a payment order"""
    print("\n" + "="*60)
    print("TEST 1: Create Payment Order")
    print("="*60)
    
    url = f"{BASE_URL}/api/payment/create-order"
    data = {
        "amount": 50000,  # ₹500
        "currency": "INR",
        "receipt": "test_receipt_001",
        "notes": {
            "mobile": "+919876543210",
            "name": "Test User",
            "purpose": "Premium Subscription"
        }
    }
    
    print(f"\n📤 Sending request to: {url}")
    print(f"📋 Request data: {json.dumps(data, indent=2)}")
    
    try:
        response = requests.post(url, json=data)
        print(f"\n📊 Response Status: {response.status_code}")
        print(f"📄 Response Body:")
        print(json.dumps(response.json(), indent=2))
        
        if response.status_code == 200 and response.json().get('success'):
            print("\n✅ Order created successfully!")
            return response.json()['data']
        else:
            print("\n❌ Order creation failed!")
            return None
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return None


def test_get_payment_status(order_id):
    """Test getting payment status"""
    print("\n" + "="*60)
    print("TEST 2: Get Payment Status")
    print("="*60)
    
    url = f"{BASE_URL}/api/payment/status/{order_id}"
    
    print(f"\n📤 Sending request to: {url}")
    
    try:
        response = requests.get(url)
        print(f"\n📊 Response Status: {response.status_code}")
        print(f"📄 Response Body:")
        print(json.dumps(response.json(), indent=2))
        
        if response.status_code == 200 and response.json().get('success'):
            print("\n✅ Payment status retrieved successfully!")
        else:
            print("\n❌ Failed to get payment status!")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")


def test_get_user_payments(mobile):
    """Test getting user payments"""
    print("\n" + "="*60)
    print("TEST 3: Get User Payments")
    print("="*60)
    
    url = f"{BASE_URL}/api/payment/user-payments/{mobile}"
    
    print(f"\n📤 Sending request to: {url}")
    
    try:
        response = requests.get(url)
        print(f"\n📊 Response Status: {response.status_code}")
        print(f"📄 Response Body:")
        print(json.dumps(response.json(), indent=2))
        
        if response.status_code == 200 and response.json().get('success'):
            print("\n✅ User payments retrieved successfully!")
        else:
            print("\n❌ Failed to get user payments!")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")


def main():
    print("\n🧪 RAZORPAY INTEGRATION TEST SUITE")
    print("="*60)
    print("Make sure the backend server is running on localhost:5000")
    print("="*60)
    
    # Test 1: Create order
    order_data = test_create_order()
    
    if order_data:
        # Test 2: Get payment status
        test_get_payment_status(order_data['order_id'])
        
        # Test 3: Get user payments
        test_get_user_payments("+919876543210")
    
    print("\n" + "="*60)
    print("✅ TEST SUITE COMPLETE")
    print("="*60)
    print("\nNote: Payment verification test requires actual Razorpay checkout")
    print("Use the frontend integration example from RAZORPAY_INTEGRATION.md")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
