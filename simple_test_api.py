"""Simple test using API endpoint"""
import requests
import json

mobile = "+91 7302249246"

print(f"\nGenerating skill mappings for: {mobile}\n")

url = "http://localhost:5000/api/generate-skill-mappings-from-roadmap"
payload = {"mobile": mobile}

try:
    response = requests.post(url, json=payload, timeout=120)
    
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
except Exception as e:
    print(f"Error: {str(e)}")
