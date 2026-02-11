"""
ANALYSIS: How Skill Ratings Are Calculated - The Problem
=========================================================

WHAT YOU ASKED:
If Week 1 has 2 topics:
  - "Machine Learning Fundamentals" (maps to skill "Machine Learning Models")
  - "scikit-learn" (maps to skill "Scikit-learn")

And the user scores:
  - Machine Learning Fundamentals: 90% (18/20 questions correct)
  - scikit-learn: 50% (10/20 questions correct)
  - Overall week score: 70% (28/40 questions correct)

QUESTION: Does the system show:
  A) Machine Learning Models: 90%, Scikit-learn: 50% (SEPARATE scores per topic)
  OR
  B) Machine Learning Models: 70%, Scikit-learn: 70% (SAME overall week score for both)

========================================
ANSWER: OPTION B (The Problem!)
========================================

THE CURRENT SYSTEM DOES:

1. ✅ STORES skill-wise breakdown in database:
   - When test is submitted, it saves 'skillPerformance' field
   - This contains SEPARATE percentages for each topic/skill
   - Example stored in week_test_result:
     {
       "scorePercentage": 70,  // Overall
       "skillPerformance": {
         "Machine Learning Fundamentals": {"percentage": 90},
         "scikit-learn": {"percentage": 50}
       }
     }

2. ❌ IGNORES skill-wise breakdown when calculating star ratings:
   - The /api/skill-ratings endpoint only uses 'scorePercentage' (overall)
   - Line 9941: score_pct = result.get('scorePercentage', 0)
   - It does NOT look at 'skillPerformance' at all!

3. ❌ APPLIES same overall score to ALL skills in that week:
   - Both "Machine Learning Models" and "Scikit-learn" get 70%
   - Even though the user scored 90% on ML and 50% on sklearn!

========================================
THE PROBLEM EXPLAINED
========================================

Current Code (Line 9936-9944):
```python
# Build a lookup: (month, week) -> scorePercentage
week_scores = {}
for result in all_week_results:
    month = result.get('month')
    week = result.get('week')
    score_pct = result.get('scorePercentage', 0)  # ← OVERALL SCORE ONLY!
    
    if month and week:
        week_scores[(month, week)] = score_pct  # ← Stores SAME score for whole week
```

Then when calculating skill ratings (Line 9983-9984):
```python
for week_num in week_numbers:
    if (month_num, week_num) in week_scores:
        week_percentages.append(week_scores[(month_num, week_num)])
        # ↑ Gets OVERALL week score, not skill-specific score!
```

RESULT:
- If Week 1 teaches "ML Fundamentals" and "scikit-learn"
- And overall week score is 70%
- Then BOTH skills get 70%, regardless of actual performance on each topic

========================================
EXAMPLE WITH REAL DATA
========================================

From the database check:
Week 4 for user +91 8864862270:
  - Overall: 46.23%
  - Topic 1 "overfitting/underfitting": 43.4% (8/20 correct)
  - Topic 2 "build and compare models": 49.06% (10/20 correct)

But if both topics map to skills in the resume, BOTH would get 46.23% stars!

========================================
WHAT SHOULD HAPPEN (CORRECT BEHAVIOR)
========================================

The system SHOULD:
1. Check skill_week_mapping to find which weeks teach "Machine Learning Models"
2. For each week, look at skillPerformance field (not overall scorePercentage)
3. Get the SPECIFIC percentage for "Machine Learning Fundamentals" topic
4. Average those specific percentages
5. Assign stars based on that average

This way:
- Machine Learning Models gets stars based on ML Fundamentals performance (90%)
- Scikit-learn gets stars based on sklearn performance (50%)

========================================
IMPACT ON USER EXPERIENCE
========================================

Current (Wrong):
- User masters ML (90%) but struggles with sklearn (50%)
- Week average: 70%
- Dashboard shows: ML ⭐⭐ (70%), sklearn ⭐⭐ (70%)
- User thinks: "Why do I have same rating? I was way better at ML!"

Correct (Should be):
- Dashboard shows: ML ⭐⭐⭐ (90%), sklearn ⭐ (50%)
- User sees accurate reflection of strengths and weaknesses
- Can focus on improving sklearn

========================================
THE FIX NEEDED
========================================

Need to modify /api/skill-ratings endpoint to:
1. Load skillPerformance data from week_test_result documents
2. Match skill names from skill_week_mapping to topics in skillPerformance
3. Use specific skill percentages instead of overall week percentage
4. Handle cases where skill name in mapping doesn't exactly match topic name

This would give ACCURATE, TOPIC-SPECIFIC ratings instead of generic week averages.
"""

print(__doc__)
