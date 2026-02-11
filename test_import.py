"""Test if app.py can be imported without errors"""
import sys
sys.path.insert(0, r'b:\placement-AI-1\backend')

try:
    print("Importing app module...")
    from app import app
    
    print("✅ App imported successfully!")
    print(f"\nRegistered routes containing 'skill':")
    
    for rule in app.url_map.iter_rules():
        if 'skill' in str(rule):
            print(f"  {rule.methods} {rule.rule}")
    
    print(f"\nAll routes:")
    for rule in app.url_map.iter_rules():
        print(f"  {rule.rule}")
        
except Exception as e:
    print(f"❌ Error importing app: {e}")
    import traceback
    traceback.print_exc()
