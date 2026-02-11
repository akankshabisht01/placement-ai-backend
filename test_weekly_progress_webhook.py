"""
Test script for weekly progress webhook endpoint
Run this to verify the webhook trigger is working
"""
import requests
import json

# Test configuration
BACKEND_URL = "http://localhost:5000"
TEST_MOBILE = "+91 9876543210"

def test_weekly_progress_webhook():
    """Test the weekly progress webhook endpoint"""
    
    print("=" * 60)
    print("Testing Weekly Progress Webhook Endpoint")
    print("=" * 60)
    
    url = f"{BACKEND_URL}/api/trigger-weekly-progress-webhook"
    payload = {"mobile": TEST_MOBILE}
    
    print(f"\n📍 URL: {url}")
    print(f"📤 Payload: {json.dumps(payload, indent=2)}")
    print("\n🔄 Sending request...")
    
    try:
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=20
        )
        
        print(f"\n📥 Response Status: {response.status_code}")
        print(f"📊 Response Headers: {dict(response.headers)}")
        
        try:
            data = response.json()
            print(f"\n✅ Response JSON:")
            print(json.dumps(data, indent=2))
            
            if data.get('success'):
                print("\n🎉 SUCCESS! Webhook triggered successfully!")
                if data.get('data'):
                    print(f"📋 Data returned: {json.dumps(data['data'], indent=2)}")
            else:
                print(f"\n❌ FAILED: {data.get('message', 'Unknown error')}")
                
        except json.JSONDecodeError:
            print(f"\n⚠️ Response is not JSON:")
            print(response.text[:500])
            
    except requests.Timeout:
        print("\n⏱️ Request timed out!")
    except requests.ConnectionError:
        print("\n🔌 Connection error! Is the backend running?")
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    test_weekly_progress_webhook()
