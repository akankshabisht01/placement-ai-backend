"""Remove duplicate route definitions after app.run()"""
with open(r'b:\placement-AI-1\backend\app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Keep only lines up to and including app.run()
# app.run() is at line 9435 (index 9434)
# We want to keep up to line 9436 (index 9435) to include the newline after app.run
lines_to_keep = lines[:9436]

# Write back
with open(r'b:\placement-AI-1\backend\app.py', 'w', encoding='utf-8') as f:
    f.writelines(lines_to_keep)

print(f"✅ Removed duplicate routes")
print(f"   Original lines: {len(lines)}")
print(f"   New lines: {len(lines_to_keep)}")
print(f"   Deleted: {len(lines) - len(lines_to_keep)} lines")
