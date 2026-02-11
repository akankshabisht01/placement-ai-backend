import os, json, requests
from typing import Dict, Any

SUGGESTION_PROMPT_TEMPLATE = """You are an expert career advisor and ATS optimizer.
Analyze the student's resume data and placement score.
Give structured, actionable suggestions to improve their chances.

---

### INPUT:
{resume_data}

---

### TASKS:
1. **Corrections**
   - Fix grammar or vague wording in career objective, skills, or projects.
   - Suggest stronger action verbs and impact-driven phrasing.

2. **Missing Skills**
   - List at least 3 missing but critical skills for the chosen job role/domain.

3. **Project Refinements**
   - Rephrase projects to emphasize tools, metrics, and outcomes.
   - Classify projects as Basic / Intermediate / Advanced.
   - Suggest at least 1 new project idea.

4. **Recommended Certifications**
   - Suggest relevant certifications (free or paid).

5. **ATS Optimization**
   - Suggest missing keywords for ATS screening.

---

### OUTPUT FORMAT:
📌 Resume Suggestions

**Corrections**
1. ...
2. ...

**Missing Skills**
1. ...
2. ...
3. ...

**Project Refinements**
1. ...
2. ...
3. New Idea: ...

**Recommended Certifications**
1. ...
2. ...

**ATS Optimization Tips**
1. ...
2. ...
"""

PERPLEXITY_MODEL = os.getenv("PERPLEXITY_MODEL", "sonar-pro")
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"

class PerplexitySuggestionError(Exception):
    pass

def build_resume_context(data: Dict[str, Any]) -> str:
    safe = {}
    for k,v in (data or {}).items():
        if isinstance(v, (str, int, float, list, dict)):
            safe[k] = v
    return json.dumps(safe, ensure_ascii=False, indent=2)

def generate_suggestions(resume_payload: Dict[str, Any]) -> Dict[str, Any]:
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        raise PerplexitySuggestionError("PERPLEXITY_API_KEY missing")
    context = build_resume_context(resume_payload)
    prompt = SUGGESTION_PROMPT_TEMPLATE.replace("{resume_data}", context)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {
        "model": PERPLEXITY_MODEL,
        "messages": [
            {"role": "system", "content": "You are a concise expert career advisor."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 900
    }
    try:
        resp = requests.post(PERPLEXITY_API_URL, headers=headers, json=body, timeout=60)
        if resp.status_code != 200:
            raise PerplexitySuggestionError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        content = data.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
        if not content:
            raise PerplexitySuggestionError("Empty response from model")
        return {"success": True, "suggestions_raw": content}
    except Exception as e:
        return {"success": False, "error": str(e)}
