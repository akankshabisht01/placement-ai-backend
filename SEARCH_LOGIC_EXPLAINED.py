"""
COMPREHENSIVE GUIDE: How Backend Searches Weekly_test_analysis and monthly_test Collections
============================================================================================

This document explains the search logic for both collections and shows the actual database structure.
"""

from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

# Connect to MongoDB
mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
client = MongoClient(mongo_uri)
db = client[os.getenv("MONGODB_DB", "Placement_Ai")]

print("="*100)
print("PART 1: Weekly_test_analysis COLLECTION")
print("="*100)

print("\n📋 ACTUAL DATABASE STRUCTURE:")
print("-"*100)

weekly_analysis = db["Weekly_test_analysis"]
sample_weekly = weekly_analysis.find_one()

print(f"""
Document Structure:
{{
    "_id": "{sample_weekly.get('_id')}",
    "mobile": "{sample_weekly.get('mobile')}",
    "analysis": {{
        "week": {sample_weekly.get('analysis', {}).get('week')},
        "month": {sample_weekly.get('analysis', {}).get('month')},
        ...
    }}
}}
""")

print("\n🔍 BACKEND SEARCH METHOD (in /api/check-month-test-eligibility):")
print("-"*100)

print("""
ENDPOINT: /api/check-month-test-eligibility/<mobile>
FILE: backend/app.py (Lines 1699-1900)

SEARCH LOGIC:
1. Normalize mobile number formats
2. Create search patterns: ["+91 9084117332", "919084117332", "9084117332"]
3. Search by 'mobile' FIELD (NOT _id)
4. Collect all weeks from found documents

CODE SNIPPET:
-------------
# Search by mobile field
for search_id in search_ids:
    found_docs = list(analysis_collection.find({'mobile': search_id}))
    if found_docs:
        print(f"Found {len(found_docs)} docs by mobile: {search_id}")
        completed_tests.extend(found_docs)
        break

# Extract week information
for doc in completed_tests:
    analysis = doc.get('analysis', {})
    month = analysis.get('month', 1)
    week = analysis.get('week', 1)
    
    if month not in month_completion:
        month_completion[month] = []
    
    if week not in month_completion[month]:
        month_completion[month].append(week)

# Check if all 4 weeks completed for Month 1
expected_weeks = [1, 2, 3, 4]
completed_weeks = month_completion.get(1, [])
all_weeks_completed = completed_weeks == expected_weeks
""")

print("\n✅ WHY IT WORKS:")
print("-"*100)
print("""
- Documents have _id like "+91 9084117332_week_1" (with week suffix)
- We search by 'mobile' FIELD which is "+91 9084117332" (no suffix)
- This matches all documents for that user (week 1, 2, 3, 4)
- We extract week numbers from the 'analysis' object
""")

print("\n💡 EXAMPLE QUERY:")
print("-"*100)

mobile = "+91 9084117332"
docs = list(weekly_analysis.find({'mobile': mobile}))
print(f"Query: db.Weekly_test_analysis.find({{'mobile': '{mobile}'}})")
print(f"Found: {len(docs)} documents")
for doc in docs:
    week = doc.get('analysis', {}).get('week')
    month = doc.get('analysis', {}).get('month')
    print(f"  - Week {week}, Month {month}")

print("\n" + "="*100)
print("PART 2: monthly_test COLLECTION")
print("="*100)

print("\n📋 ACTUAL DATABASE STRUCTURE:")
print("-"*100)

monthly_test = db["monthly_test"]
sample_monthly = monthly_test.find_one()

print(f"""
Document Structure:
{{
    "_id": "{sample_monthly.get('_id')}",
    "mobile": "{sample_monthly.get('mobile')}",
    "month": {sample_monthly.get('month')},
    "test_number": {sample_monthly.get('test_number')},
    "week1": {{ questions: [...] }},
    "week2": {{ questions: [...] }},
    "week3": {{ questions: [...] }},
    "week4": {{ questions: [...] }}
}}

⚠️ IMPORTANT:
   _id = "{sample_monthly.get('_id')}" (just mobile number)
   NOT "{sample_monthly.get('_id')}_month_1" (this format doesn't exist!)
""")

print("\n🔍 BACKEND SEARCH METHOD #1 (in /api/monthly-test-status):")
print("-"*100)

print("""
ENDPOINT: /api/monthly-test-status/<mobile>/<int:month>
FILE: backend/app.py (Lines 2200-2370)
PURPOSE: Check if test exists, if timer running, if completed

SEARCH LOGIC (FIXED):
1. Normalize mobile number formats
2. Search by 'mobile' FIELD + 'month' FIELD (matches N8N format)
3. Fallback: Search by _id pattern for backward compatibility

CODE SNIPPET:
-------------
# Primary: Search by mobile + month fields (N8N format)
for search_id in search_ids:
    test_doc = monthly_test_collection.find_one({
        "mobile": search_id, 
        "month": {"$in": [month, str(month)]}
    })
    if test_doc:
        test_id = str(test_doc.get('_id'))
        break

# Fallback: Old format (if any exist)
if not test_doc:
    for search_id in search_ids:
        test_id_variant = f"{search_id}_month_{month}"
        test_doc = monthly_test_collection.find_one({'_id': test_id_variant})
        if test_doc:
            test_id = test_id_variant
            break

test_generated = test_doc is not None
""")

print("\n🔍 BACKEND SEARCH METHOD #2 (in /api/monthly-test-fetcher):")
print("-"*100)

print("""
ENDPOINT: /api/monthly-test-fetcher
FILE: backend/app.py (Lines 6478-6660)
PURPOSE: Get test questions to display in frontend

SEARCH LOGIC (ALREADY CORRECT):
1. Search directly by 'mobile' FIELD + 'month' FIELD
2. Try alternative mobile formats if not found

CODE SNIPPET:
-------------
# Search by mobile + month fields
test_doc = collection.find_one({
    "mobile": mobile, 
    "month": {"$in": [month, str(month)]}
})

# Try alternative formats
if not test_doc:
    candidates = [
        mobile,
        mobile.replace(' ', ''),
        mobile.replace('+', ''),
        ''.join([c for c in mobile if c.isdigit()])
    ]
    
    for cand in candidates:
        test_doc = collection.find_one({
            "mobile": cand, 
            "month": {"$in": [month, str(month)]}
        })
        if test_doc:
            break
""")

print("\n✅ WHY IT WORKS:")
print("-"*100)
print("""
- N8N creates documents with _id = mobile (not mobile_month_X)
- We search by 'mobile' FIELD + 'month' FIELD
- This matches how N8N actually stores the data
- No need to construct _id patterns
""")

print("\n💡 EXAMPLE QUERY:")
print("-"*100)

mobile = "+91 9084117332"
month = 1
doc = monthly_test.find_one({"mobile": mobile, "month": {"$in": [month, str(month)]}})
print(f"Query: db.monthly_test.find_one({{'mobile': '{mobile}', 'month': {{'$in': [{month}, '{month}']}}}})")
if doc:
    print(f"Found: _id = {doc.get('_id')}, month = {doc.get('month')}")
    print(f"Keys: {list(doc.keys())}")
else:
    print("Not found")

print("\n" + "="*100)
print("COMPARISON SUMMARY")
print("="*100)

print("""
┌────────────────────────────────────────────────────────────────────────────────────┐
│ Collection: Weekly_test_analysis                                                   │
├────────────────────────────────────────────────────────────────────────────────────┤
│ Document _id:     "+91 9084117332_week_1"  (mobile + week suffix)                │
│ Search by:        'mobile' FIELD = "+91 9084117332"                              │
│ Why:              To find ALL weeks for a user (week 1, 2, 3, 4)                 │
│ Used in:          /api/check-month-test-eligibility                               │
│ Returns:          List of completed weeks to check month unlock                   │
└────────────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────────────────┐
│ Collection: monthly_test                                                           │
├────────────────────────────────────────────────────────────────────────────────────┤
│ Document _id:     "+91 9084117332"  (just mobile, no suffix)                     │
│ Search by:        'mobile' FIELD + 'month' FIELD                                 │
│ Why:              N8N stores with simple _id = mobile                             │
│ Used in:          /api/monthly-test-status, /api/monthly-test-fetcher            │
│ Returns:          Single test document with all questions                         │
└────────────────────────────────────────────────────────────────────────────────────┘

KEY DIFFERENCES:
================
1. Weekly_test_analysis has MULTIPLE documents per user (one per week)
   monthly_test has ONE document per user per month

2. Weekly_test_analysis _id includes "_week_X" suffix
   monthly_test _id is just the mobile number

3. Both searches use 'mobile' FIELD, not _id pattern matching
   This is more reliable than trying to construct _id patterns

4. Monthly search adds 'month' FIELD filter to distinguish months
   Weekly search filters by extracting week from 'analysis' object
""")

print("\n" + "="*100)
print("FIXES APPLIED")
print("="*100)

print("""
ISSUE #1: Month Not Unlocking (Weekly_test_analysis)
-----------------------------------------------------
BEFORE: Searched by _id field first, then fallback to mobile field
AFTER:  Search directly by mobile field (more reliable)
RESULT: ✅ Correctly finds all 4 weeks, unlocks Month 1

ISSUE #2: Monthly Test Not Detected (monthly_test)
--------------------------------------------------
BEFORE: Searched by _id = "mobile_month_1" pattern (didn't match reality)
AFTER:  Search by mobile + month FIELDS (matches N8N format)
RESULT: ✅ Correctly detects generated tests, shows timer/start/analysis
""")

print("\n" + "="*100)
print("END OF GUIDE")
print("="*100)

client.close()
