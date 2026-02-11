"""List all Flask routes to verify endpoint registration"""
import requests

try:
    # Try to hit a known endpoint to verify server is running
    response = requests.get("http://localhost:5000/api/get-all-roadmaps", timeout=5)
    print(f"✅ Server is running (status: {response.status_code})")
    
    # Try the skill endpoint
    print(f"\nTesting /api/check-skill-completion-with-ai endpoint...")
    response = requests.post(
        "http://localhost:5000/api/check-skill-completion-with-ai",
        json={"mobile": "+91 8864862270", "monthNumber": 1, "weekNumber": 4},
        timeout=5
    )
    print(f"  Status: {response.status_code}")
    if response.status_code == 404:
        print(f"  ❌ Endpoint not found!")
    else:
        print(f"  ✅ Endpoint exists!")
        print(f"  Response: {response.json()}")
        
except requests.exceptions.ConnectionError:
    print(f"❌ Cannot connect to server on port 5000")
except Exception as e:
    print(f"❌ Error: {e}")
