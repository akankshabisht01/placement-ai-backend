import re

def normalize_text(val):
    try:
        s = str(val)
    except Exception:
        s = ''
    # Remove simple HTML tags
    s = re.sub(r'<[^>]*>', '', s)
    # Collapse whitespace
    s = ' '.join(s.split())
    return s.strip().lower()

# Test cases
correct_answer = "A"
user_answer = "A) ="
options = ["A) =", "B) /", "C) #", "D) @"]

normalized_user = normalize_text(user_answer)
print(f"Correct Answer: {repr(correct_answer)}")
print(f"User Answer: {repr(user_answer)}")
print(f"Normalized User: {repr(normalized_user)}")
print()

# Check if correct_answer is a single letter
if len(str(correct_answer).strip()) == 1 and str(correct_answer).strip().upper() in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
    letter = str(correct_answer).strip().upper()
    print(f"Single letter detected: {letter}")
    
    # Check if user answer starts with "A)", "a)", etc.
    if normalized_user.startswith(letter.lower() + ')') or normalized_user.startswith(letter.lower() + ' '):
        print(f"✅ CORRECT: User answer starts with '{letter.lower()})'")
        is_correct = True
    else:
        print(f"❌ No match")
        is_correct = False
else:
    print("Not a single letter")
    is_correct = False

print(f"\nFinal result: {'CORRECT' if is_correct else 'INCORRECT'}")
