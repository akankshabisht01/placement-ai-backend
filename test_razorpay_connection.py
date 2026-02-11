"""
Test script to diagnose Razorpay API connectivity issues
"""
import socket
import requests
from dotenv import load_dotenv
import os

load_dotenv()

def test_dns_resolution():
    """Test if api.razorpay.com can be resolved"""
    print("🔍 Testing DNS Resolution...")
    try:
        ip = socket.gethostbyname('api.razorpay.com')
        print(f"✅ DNS Resolution Successful: api.razorpay.com -> {ip}")
        return True
    except socket.gaierror as e:
        print(f"❌ DNS Resolution Failed: {e}")
        print("\n⚠️  SOLUTIONS:")
        print("1. Change DNS to Google DNS (8.8.8.8, 8.8.4.4)")
        print("2. Change DNS to Cloudflare (1.1.1.1, 1.0.0.1)")
        print("3. Flush DNS cache: ipconfig /flushdns")
        return False

def test_internet_connectivity():
    """Test basic internet connectivity"""
    print("\n🌐 Testing Internet Connectivity...")
    try:
        response = requests.get('https://www.google.com', timeout=5)
        print(f"✅ Internet Connection: OK (Status {response.status_code})")
        return True
    except Exception as e:
        print(f"❌ Internet Connection Failed: {e}")
        return False

def test_razorpay_api():
    """Test Razorpay API connectivity"""
    print("\n🔐 Testing Razorpay API Connection...")
    
    key_id = os.getenv('RAZORPAY_KEY_ID')
    key_secret = os.getenv('RAZORPAY_KEY_SECRET')
    
    if not key_id or not key_secret:
        print("❌ Razorpay credentials not found in .env")
        return False
    
    print(f"Key ID: {key_id}")
    
    try:
        # Try to ping Razorpay API
        response = requests.get(
            'https://api.razorpay.com/v1/payments',
            auth=(key_id, key_secret),
            timeout=10
        )
        print(f"✅ Razorpay API Connection: OK (Status {response.status_code})")
        return True
    except requests.exceptions.ConnectionError as e:
        print(f"❌ Cannot connect to Razorpay API: {e}")
        print("\n⚠️  Possible Issues:")
        print("- DNS resolution problem")
        print("- Firewall blocking the connection")
        print("- Proxy/VPN interfering")
        return False
    except Exception as e:
        print(f"⚠️  Razorpay API Error: {e}")
        return False

def main():
    print("="*60)
    print("🔧 RAZORPAY CONNECTION DIAGNOSTIC TOOL")
    print("="*60)
    
    # Run tests
    dns_ok = test_dns_resolution()
    internet_ok = test_internet_connectivity()
    razorpay_ok = test_razorpay_api()
    
    # Summary
    print("\n" + "="*60)
    print("📊 SUMMARY")
    print("="*60)
    print(f"DNS Resolution: {'✅ PASS' if dns_ok else '❌ FAIL'}")
    print(f"Internet Connection: {'✅ PASS' if internet_ok else '❌ FAIL'}")
    print(f"Razorpay API: {'✅ PASS' if razorpay_ok else '❌ FAIL'}")
    print("="*60)
    
    if not dns_ok:
        print("\n🔧 RECOMMENDED ACTION:")
        print("Change your DNS settings to use Google DNS or Cloudflare DNS")
        print("\nWindows Command (Run as Administrator):")
        print("netsh interface ip set dns \"Wi-Fi\" static 8.8.8.8")
        print("netsh interface ip add dns \"Wi-Fi\" 8.8.4.4 index=2")

if __name__ == "__main__":
    main()
