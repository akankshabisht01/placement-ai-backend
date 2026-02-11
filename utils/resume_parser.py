import os
import re
import json
from typing import Dict, List

import PyPDF2
import requests
from dotenv import load_dotenv

# Always load environment variables from .env file
load_dotenv()

try:
    import docx2txt  # Better text extraction from .docx
except Exception:  # Library may not be installed yet; we'll handle gracefully
    docx2txt = None

try:
    from pdfminer.high_level import extract_text as pdfminer_extract_text  # optional
except Exception:
    pdfminer_extract_text = None

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"


def _ocr_via_ocr_space(path: str) -> str:
    """Send PDF to OCR.space API and return extracted text.
    
    Uses OCR_SPACE_API_KEY from environment, or falls back to public 'helloworld' key.
    Returns empty string on failure.
    """
    api_key = os.getenv('OCR_SPACE_API_KEY', 'helloworld')
    url = 'https://api.ocr.space/parse/image'
    
    print(f"[OCR] Attempting OCR.space with key: {api_key[:8]}...")
    
    try:
        with open(path, 'rb') as fh:
            files = {'file': fh}
            data = {
                'apikey': api_key,
                'language': 'eng',
                'isOverlayRequired': False,
                'OCREngine': 2,  # Engine 2 is better for scanned documents
            }
            resp = requests.post(url, files=files, data=data, timeout=90)
            resp.raise_for_status()
            
            result = resp.json()
            print(f"[OCR] API Response Status: {result.get('OCRExitCode', 'unknown')}")
            
            if result.get('IsErroredOnProcessing'):
                error_msg = result.get('ErrorMessage', ['Unknown error'])
                print(f"[OCR] Processing error: {error_msg}")
                return ""
            
            parsed = result.get('ParsedResults', [])
            if parsed and isinstance(parsed, list) and len(parsed) > 0:
                text = parsed[0].get('ParsedText', '') or ''
                print(f"[OCR] Extracted {len(text)} characters")
                return text.strip()
            else:
                print("[OCR] No parsed results in response")
                return ""
                
    except Exception as e:
        print(f"[OCR] Request failed: {type(e).__name__}: {e}")
        return ""


def _clean_email(e: str) -> str:
    if not e:
        return ""
    e = e.strip().strip('<>()[]{}').strip().strip(',;')
    # Remove trailing punctuation after TLD accidentally included
    e = re.sub(r"([A-Za-z]{2,})[\.,;:]+$", r"\1", e)
    return e.lower()


def _extract_primary_email(text: str) -> str:
    """Extract the most plausible primary email from text.
    Strategy:
      1. Collect all regex candidates.
      2. Normalize & dedupe.
      3. Rank: prioritize personal/common domains, then shortest local part, then first occurrence.
      4. Fallback: lines containing 'email' label.
    """
    # Negative lookbehind prevents gluing trailing letters of a previous word to the email (e.g., 'pejohn.doe@..').
    email_regex = re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    domain_priority = [
        "gmail.com", "outlook.com", "yahoo.com", "hotmail.com",
        "proton.me", "protonmail.com", "icloud.com"
    ]

    candidates = {}
    for m in email_regex.finditer(text):
        raw = m.group(0)
        cleaned = _clean_email(raw)
        if not cleaned or cleaned.count('@') != 1:
            continue
        # Filter out obviously malformed (multiple consecutive dots before @ or after)
        if '..' in cleaned.split('@')[0]:
            continue
        if len(cleaned.split('@')[0]) < 2:
            continue
        # Record first index for tie-breaking
        if cleaned not in candidates:
            candidates[cleaned] = m.start()

    if not candidates:
        # Attempt explicit label pattern e.g. 'Email: something'
        label_match = re.search(r"Email\s*[:\-]\s*([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", text, re.IGNORECASE)
        if label_match:
            return _clean_email(label_match.group(1))
        return ""

    # Ranking
    def _rank(email: str):
        local, domain = email.split('@', 1)
        # Priority index; lower is better
        pri = domain_priority.index(domain) if domain in domain_priority else len(domain_priority)
        return (pri, len(local), candidates[email])

    best = sorted(candidates.keys(), key=_rank)[0]

    return best


def _trim_spurious_email_prefix(email: str) -> str:
    """Remove common 1–2 letter garbage prefixes (from PDF icon/ligature extraction) before actual email local part.
    Conservative: only for common personal domains and when length/format still valid after trim.
    """
    if not email or '@' not in email:
        return email
    local, domain = email.split('@', 1)
    domain_l = domain.lower()
    if domain_l not in {"gmail.com", "outlook.com", "yahoo.com", "hotmail.com", "proton.me", "protonmail.com"}:
        return email
    if len(local) < 8:  # too short to risk trimming
        return email
    suspicious_prefixes = {"pe", "em", "ma", "re", "ce", "de"}
    for cut in (2, 1):  # prefer removing two first
        prefix = local[:cut].lower()
        rest = local[cut:]
        if prefix in suspicious_prefixes and len(rest) >= 6 and re.match(r"^[a-z][a-z0-9._%+-]+$", rest, re.IGNORECASE):
            return rest + '@' + domain
    return email


def _extract_text_from_pdf(path: str) -> str:
    text = ""
    print(f"[PDF] Extracting text from: {os.path.basename(path)}")
    
    try:
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            num_pages = len(reader.pages)
            print(f"[PDF] Document has {num_pages} pages")
            
            for i, page in enumerate(reader.pages):
                # extract_text() can return None; guard it
                page_text = page.extract_text() or ""
                text += ("\n" + page_text)
                
        text = text.strip()
        print(f"[PDF] PyPDF2 extracted {len(text)} characters")
    except Exception as e:
        print(f"[PDF] PyPDF2 extraction failed: {type(e).__name__}: {e}")
        text = ""

    # If PyPDF2 produced too little text, try pdfminer if available
    if (not text or len(text) < 100) and pdfminer_extract_text is not None:
        print("[PDF] Trying pdfminer fallback...")
        try:
            text2 = pdfminer_extract_text(path) or ""
            print(f"[PDF] pdfminer extracted {len(text2)} characters")
            if len(text2) > len(text):
                text = text2
        except Exception as e:
            print(f"[PDF] pdfminer failed: {type(e).__name__}: {e}")
            pass

    # If still too little text, attempt OCR via API
    if not text or len(text) < 100:
        print("[PDF] Text extraction failed - attempting OCR...")
        ocr_text = _ocr_via_ocr_space(path)
        if ocr_text and len(ocr_text) > len(text):
            print("[PDF] Using OCR result")
            text = ocr_text
        else:
            print(f"[PDF] OCR produced insufficient text ({len(ocr_text)} chars)")

    return text.strip()


def _extract_text_from_docx(path: str) -> str:
    if docx2txt is None:
        return ""
    try:
        return (docx2txt.process(path) or "").strip()
    except Exception:
        return ""


def _extract_text_from_txt(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    except Exception:
        return ""


def _extract_text(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return _extract_text_from_pdf(path)
    if ext == ".docx":
        return _extract_text_from_docx(path)
    if ext in {".txt", ".text"}:
        return _extract_text_from_txt(path)
    return ""


def _clean_json_text(text: str) -> str:
    """Clean and fix JSON text from API responses."""
    # Strip code fences if the model included them
    text = text.strip()
    if text.startswith("```"):
        # Remove first fence line and optional language
        text = re.sub(r"^```[a-zA-Z0-9_-]*\n", "", text)
    if text.endswith("```"):
        text = text[:-3]
    
    text = text.strip()
    
    # Fix truncated JSON by adding missing closing brackets
    # Count opening and closing braces/brackets
    open_braces = text.count('{')
    close_braces = text.count('}')
    open_brackets = text.count('[')
    close_brackets = text.count(']')
    
    # Add missing closing brackets/braces if truncated
    if open_braces > close_braces:
        text += '}' * (open_braces - close_braces)
    if open_brackets > close_brackets:
        text += ']' * (open_brackets - close_brackets)
    
    return text.strip()


def _to_float(val, default=0.0) -> float:
    try:
        if val is None:
            return float(default)
        # Extract first number in string if needed
        if isinstance(val, str):
            m = re.search(r"-?\d+(?:\.\d+)?", val.replace(",", "."))
            if m:
                return float(m.group(0))
        return float(val)
    except Exception:
        return float(default)


def _extract_json_from_text(text: str) -> Dict:
    """Extract the first JSON object from free-form text."""
    text = text.strip()
    # Quick path: try direct parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # Find the first {...} block by braces balance
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except Exception:
                        break
        start = text.find("{", start + 1)
    # As a last resort, try to find [...] list and coerce if it looks like skills
    return {}


def _find_section_lines(text: str, headers: List[str], max_lines: int = 10) -> List[str]:
    lines = [ln.rstrip() for ln in text.splitlines()]
    out: List[str] = []
    header_idx = -1
    # Known headers to stop at
    stop_headers = [
        "Skills", "Technical Skills", "Technologies",
        "Projects", "Academic Projects",
        "Internship", "Internships",
        "Achievements", "Awards", "Honors",
        "Experience", "Work Experience",
        "Education", "Certifications", "Certification",
    ]
    for i, ln in enumerate(lines):
        if any(h.lower() in ln.lower() for h in headers):
            header_idx = i
            break
    if header_idx >= 0:
        for ln in lines[header_idx + 1 : header_idx + 1 + max_lines]:
            s = ln.strip()
            if not s:
                break
            # If next section header appears, stop
            if any(h.lower() in s.lower() for h in stop_headers):
                break
            out.append(s)
    return out


def _regex_fallback(text: str) -> Dict:
    """Simpler, robust fallback parser (no fancy heuristics) to ensure backend stability."""
    email = _extract_primary_email(text)

    # Phone extraction: gather candidates, normalize, rank by plausibility
    raw_phone_candidates = set()
    # Patterns to catch: with country code, parentheses, spaces, dashes
    phone_patterns = [
        r"\+?\d[\d\s\-()]{8,}\d",  # generic international-ish
        r"\(\+?\d{1,3}\)\s?\d[\d\s\-]{6,}\d",  # (+91) 98765 43210
    ]
    for pat in phone_patterns:
        for m in re.finditer(pat, text):
            raw = m.group(0)
            # Exclude lines that look like years ranges (e.g., 2019-2023)
            if re.match(r"20\d{2}\s*[-–]\s*20\d{2}$", raw.strip()):
                continue
            raw_phone_candidates.add(raw)

    def _normalize_phone(raw: str) -> str:
        # Remove surrounding punctuation and multiple spaces
        cleaned = raw.strip()
        # Replace common separators
        cleaned = re.sub(r"[\s\-()]+", "", cleaned)
        # Keep leading + only
        if cleaned.count('+') > 1:
            cleaned = '+' + cleaned.replace('+', '')
        # Strip non-digits except leading +
        if cleaned.startswith('+'):
            cleaned = '+' + re.sub(r"[^\d]", "", cleaned[1:])
        else:
            cleaned = re.sub(r"[^\d]", "", cleaned)
        # Heuristic: if appears to be Indian mobile with 12-13 incl +91
        if cleaned.startswith('+91') and len(cleaned) >= 13:
            return '+91 ' + cleaned[-10:]
        # If no country code and length >=10, attempt to format last 10 digits
        if not cleaned.startswith('+') and len(cleaned) >= 10:
            return cleaned[-10:]
        return cleaned

    normalized_candidates = []
    for raw in raw_phone_candidates:
        norm = _normalize_phone(raw)
        if 10 <= len(re.sub(r"[^\d]", "", norm)) <= 15:
            normalized_candidates.append(norm)

    # Rank: prefer those with +91 formatting, then length 10-12
    def _rank_phone(p: str):
        digits = re.sub(r"[^\d]", "", p)
        score = 0
        if p.startswith('+91 '):
            score -= 20
        if len(digits) == 10:
            score -= 5
        return (score, len(digits))

    phone = normalized_candidates and sorted(normalized_candidates, key=_rank_phone)[0] or ""
    phone_raw = phone  # for name filtering below

    # CGPA / percentages
    cgpa = None
    cgpa_pat = re.search(r"CGPA\s*:?\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if cgpa_pat:
        try: cgpa = float(cgpa_pat.group(1));
        except: cgpa = None
    tenth = None
    twelfth = None
    tenth_pat = re.search(r"10th[^0-9\n]*(\d{1,3}(?:\.\d+)?)%", text, re.IGNORECASE)
    if tenth_pat:
        try: tenth = float(tenth_pat.group(1));
        except: pass
    twelfth_pat = re.search(r"12th[^0-9\n]*(\d{1,3}(?:\.\d+)?)%", text, re.IGNORECASE)
    if twelfth_pat:
        try: twelfth = float(twelfth_pat.group(1));
        except: pass

    # --- Degree parsing upgrade: attempt to separate bachelor's and master's ---
    bachelor_degree = ""
    bachelor_university = ""
    bachelor_cgpa = None
    masters_degree = ""
    masters_university = ""
    masters_cgpa = None

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    bachelor_pattern = re.compile(r"\b(Bachelor(?:'s)? of [A-Za-z& /]+|B\.?\s?Tech(?:nology)?|B\.?\s?E\.?(?:ngineering)?|BSc|B\.?\s?Sc|BCA|BBA)\b", re.IGNORECASE)
    # Use word boundaries and require explicit degree abbreviations to avoid false matches like 'me' from 'E-commerce'
    masters_pattern = re.compile(r"\b(Master(?:'s)? of [A-Za-z& /]+|M\.?\s?Tech(?:nology)?|M\.?E\.?(?:ngineering)?|MSc|M\.?\s?Sc|MBA|MCA)\b", re.IGNORECASE)

    def _extract_nearby_university(idx: int) -> str:
        # Look on the same line then next 2 lines for 'University' or 'College'
        for j in range(idx, min(idx + 3, len(lines))):
            m = re.search(r"([A-Z][A-Za-z0-9&,.()\- ]{3,})(University|Institute|College|School)", lines[j], re.IGNORECASE)
            if m:
                return lines[j]
        return ""

    def _extract_nearby_cgpa(idx: int) -> float | None:
        # Search same + next 3 lines for CGPA pattern
        for j in range(idx, min(idx + 4, len(lines))):
            cg = re.search(r"CGPA[^0-9]{0,10}(\d(?:\.\d{1,2})?)", lines[j], re.IGNORECASE)
            if cg:
                try:
                    return float(cg.group(1))
                except Exception:
                    return None
        return None

    for idx, ln in enumerate(lines):
        if not bachelor_degree:
            bmatch = bachelor_pattern.search(ln)
            if bmatch:
                bachelor_degree = bmatch.group(0).strip()
                if not bachelor_university:
                    bachelor_university = _extract_nearby_university(idx)
                if bachelor_cgpa is None:
                    bachelor_cgpa = _extract_nearby_cgpa(idx)
        if not masters_degree:
            mmatch = masters_pattern.search(ln)
            if mmatch:
                masters_degree = mmatch.group(0).strip()
                if not masters_university:
                    masters_university = _extract_nearby_university(idx)
                if masters_cgpa is None:
                    masters_cgpa = _extract_nearby_cgpa(idx)
        if bachelor_degree and masters_degree:
            break

    # Generic (backwards compatible) university/degree fields default to bachelor if present.
    uni = bachelor_university or masters_university or ""
    degree = bachelor_degree or masters_degree or ""

    # Skills - try section-based extraction first, then inline
    skills = []
    skills_sec = _find_section_lines(text, ["Skills", "Technical Skills", "Core Skills", "Key Skills", "Skill Set", "Technical Expertise", "Technologies"])
    if skills_sec:
        for line in skills_sec[:20]:
            line = line.strip("-•:*→➤ \t")
            if line and len(line) > 1:
                # Split by common delimiters
                parts = re.split(r",|\||;|•|\u2022", line)
                for p in parts:
                    p = p.strip()
                    if p and len(p) > 1 and len(p) < 50:  # Skip very long items (likely descriptions)
                        skills.append(p)
    # Fallback to inline pattern
    if not skills:
        skills_inline = re.search(r"Skills?\s*[:\-]\s*(.+)", text, re.IGNORECASE)
        if skills_inline:
            parts = re.split(r",|\n|•|\u2022|;", skills_inline.group(1))
            skills = [p.strip() for p in parts if len(p.strip()) > 1][:30]
    # Dedupe and limit
    seen_skills = set()
    unique_skills = []
    for s in skills:
        if s.lower() not in seen_skills:
            seen_skills.add(s.lower())
            unique_skills.append(s)
    skills = unique_skills[:30]

    # Projects (structured objects with title and description)
    projects = []
    proj_sec = _find_section_lines(text, ["Projects", "Academic Projects"])
    if proj_sec:
        for line in proj_sec[:10]:
            line = line.strip("-•: ")
            if not line:
                continue
            # Try to split title and description by common separators
            if " - " in line:
                parts = line.split(" - ", 1)
                title = parts[0].strip()
                description = parts[1].strip() if len(parts) > 1 else ""
            elif " : " in line:
                parts = line.split(" : ", 1)
                title = parts[0].strip()
                description = parts[1].strip() if len(parts) > 1 else ""
            else:
                # If no separator found, use entire line as title
                title = line.strip()
                description = ""
            
            if title:
                projects.append({"title": title, "description": description})

    # Internships extraction
    internships = []
    intern_sec = _find_section_lines(text, [
        "Internships", "Internship", "Work Experience", "Experience",
        "Professional Experience", "Employment", "Training"
    ])
    if intern_sec:
        for line in intern_sec[:15]:
            line = line.strip("-•:*→➤ \t")
            if line and len(line) > 5:
                lower_line = line.lower()
                # Look for internship indicators
                if any(keyword in lower_line for keyword in ["intern", "trainee", "apprentice"]) or \
                   (len(line.split()) >= 3 and not line.isupper()):
                    internships.append(line.strip())
    # Dedupe internships
    internships = list(dict.fromkeys(internships))[:10]

    # Achievements extraction
    achievements = []
    achieve_sec = _find_section_lines(text, [
        "Achievements", "Achievement", "Awards", "Honors", "Honours",
        "Accomplishments", "Recognition", "Awards & Achievements"
    ])
    if achieve_sec:
        for line in achieve_sec[:15]:
            line = line.strip("-•:*→➤ \t")
            if line and len(line) > 5:
                lower_line = line.lower()
                # Skip section headers
                if not any(skip in lower_line for skip in ["experience", "project", "education", "skill"]):
                    achievements.append(line.strip())
    # Dedupe achievements
    achievements = list(dict.fromkeys(achievements))[:10]

    # Certifications extraction - Enhanced to catch more patterns
    certifications = []
    
    # First try to find certification section
    cert_sec = _find_section_lines(text, [
        "Certifications", "Certification", "Certificates", "Certificate",
        "Professional Certifications", "Licenses & Certifications",
        "Licenses and Certifications", "Training & Certifications",
        "Courses & Certifications", "Online Certifications"
    ])
    
    if cert_sec:
        for line in cert_sec[:15]:
            line = line.strip("-•:*→➤ \t")
            # Skip very short lines or section headers
            if line and len(line) > 5 and len(line.split()) > 1:
                # Skip common non-certification lines
                lower_line = line.lower()
                if not any(skip in lower_line for skip in ["experience", "project", "education", "skill", "summary"]):
                    certifications.append(line.strip())
    
    # Enhanced heuristic fallback for certifications with more patterns
    if not certifications:
        cert_patterns = [
            # Platform-specific
            r"AWS\s+(Certified|Certificate)",
            r"Azure\s+(Certified|Certificate|Fundamentals)",
            r"Google\s+(Cloud|Certified|Certificate)",
            r"Microsoft\s+(Certified|Certificate)",
            r"Oracle\s+(Certified|Certificate)",
            r"Cisco\s+(Certified|CCNA|CCNP)",
            r"Red\s+Hat\s+Certified",
            r"CompTIA\s+",
            
            # Course platforms
            r"Coursera",
            r"Udemy",
            r"edX",
            r"Udacity",
            r"LinkedIn\s+Learning",
            r"Pluralsight",
            
            # General certification keywords
            r"Certified\s+\w+\s+(Professional|Associate|Expert|Developer|Engineer|Administrator)",
            r"\w+\s+Certification",
            r"Certificate\s+(of|in)\s+\w+",
            
            # Specific technologies
            r"Python\s+(Certified|Certificate|Certification)",
            r"Java\s+(Certified|Certificate|Certification)",
            r"Docker\s+(Certified|Certificate)",
            r"Kubernetes\s+(Certified|Certificate|CKAD|CKA)",
            r"Terraform\s+(Associate|Certified)",
            r"Scrum\s+(Master|Product Owner|PSM|PSPO)",
            r"PMP\s+Certified",
            r"ITIL\s+(Foundation|Certified)",
            
            # AI/ML specific
            r"Machine\s+Learning\s+(Certification|Certificate)",
            r"Deep\s+Learning\s+(Specialization|Certificate)",
            r"Data\s+Science\s+(Certification|Certificate)",
            r"AI\s+(Certification|Certificate)",
        ]
        
        combined_pattern = "|".join(cert_patterns)
        
        for line in text.splitlines():
            l = line.strip()
            if not l or len(l) < 5:
                continue
                
            # Check against patterns
            if re.search(combined_pattern, l, re.IGNORECASE):
                # Avoid adding section headers alone
                lower_l = l.lower()
                if (len(l.split()) > 1 and 
                    not lower_l.startswith(("experience", "project", "education", "skill")) and
                    not l.isupper()):  # Skip ALL CAPS headers
                    certifications.append(l)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_certs = []
        for cert in certifications:
            cert_lower = cert.lower()
            if cert_lower not in seen:
                seen.add(cert_lower)
                unique_certs.append(cert)
        certifications = unique_certs[:15]

    # Basic name heuristic: first line with 2-4 words, mostly capitalized
    name = ""
    for ln in text.splitlines():
        s = ln.strip()
        if not s or email in s or (phone_raw and phone_raw in s):
            continue
        words = s.split()
        if 2 <= len(words) <= 5 and sum(w[:1].isupper() for w in words) >= 2:
            name = s
            break
    for prefix in ("Dr.", "Mr.", "Ms.", "Mrs.", "Prof."):
        if name.startswith(prefix):
            name = name[len(prefix):].strip()
            break

    return {
        "name": name,
        "email": _trim_spurious_email_prefix(email),
        "phone": phone,
        # Backwards compatible generic fields (mapped to bachelor when available)
        "university": (bachelor_university or masters_university or uni or ""),
        "degree": (bachelor_degree or masters_degree or degree or ""),
        "cgpa": float(bachelor_cgpa if bachelor_cgpa is not None else (cgpa if cgpa is not None else 0.0)),
        "tenthPercentage": float(tenth) if tenth is not None else 0.0,
        "twelfthPercentage": float(twelfth) if twelfth is not None else 0.0,
        "skills": skills,
        "projects": projects,
    "internships": internships,
    "achievements": achievements,
    "certifications": certifications,
        # New explicit bachelor / masters fields
        "bachelorDegree": bachelor_degree or "",
        "bachelorUniversity": bachelor_university or "",
        "bachelorCGPA": float(bachelor_cgpa) if bachelor_cgpa is not None else (float(cgpa) if cgpa is not None else 0.0),
        "mastersDegree": masters_degree or "",
        "mastersUniversity": masters_university or "",
        "mastersCGPA": float(masters_cgpa) if masters_cgpa is not None else 0.0,
    }


def _call_perplexity_api(resume_text: str) -> Dict:
    # Force reload .env to ensure fresh API key
    load_dotenv(override=True)
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        raise RuntimeError("PERPLEXITY_API_KEY not set in .env file")
    
    # Debug: Log which API key is being used (first 12 and last 6 chars for security)
    print(f"Using Perplexity API key: {api_key[:12]}...{api_key[-6:]}")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    system = (
        "You are an expert resume parser. Return ONLY a compact JSON object with EXACT keys: "
        "name, email, phone, "
        "bachelorDegree, bachelorUniversity, bachelorCGPA, "
        "mastersDegree, mastersUniversity, mastersCGPA, "
        "tenthPercentage, twelfthPercentage, "
        "skills (array of strings), "
        "projects (array of objects with 'title' and 'description' keys), "
        "internships (array of strings), "
        "achievements (array of strings), "
        "certifications (array of strings - extract ALL certificates, online courses, professional certifications, training programs, licenses). "
        "For certifications, include: AWS, Azure, Google Cloud, Coursera, Udemy, edX, LinkedIn Learning, Pluralsight, "
        "PMP, Scrum, ITIL, CompTIA, Cisco, Red Hat, Oracle, Microsoft certifications, Docker, Kubernetes, "
        "programming language certifications, AI/ML certifications, data science courses, and any other professional credentials. "
        "Extract complete certification names with issuing organization if mentioned. "
        "For projects, extract both title and description. If only title is available, set description to empty string. "
        "If a master's degree is not present, set mastersDegree to null and mastersUniversity to null and mastersCGPA to null. "
        "Bachelor fields must always be populated if any degree is present. Use numbers for all *_CGPA and percentage fields. "
        "Do NOT include any explanatory text—ONLY the JSON."
    )

    # Truncate to keep prompt size manageable
    MAX_CHARS = 18000
    truncated = resume_text[:MAX_CHARS]
    if len(resume_text) > MAX_CHARS:
        truncated += "\n\n(Note: input truncated)"

    user = (
        "Parse the following resume text and return the JSON described above. Do not include explanations.\n\n"
        f"RESUME:\n{truncated}"
    )

    payload = {
        "model": "sonar-pro",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": 2000,  # Increased from 800 to handle complete JSON responses
    }

    resp = requests.post(PERPLEXITY_API_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    content = _clean_json_text(content)
    parsed = _extract_json_from_text(content)

    # Normalize keys to expected schema
    name = parsed.get("name") or parsed.get("Name") or ""
    email = _trim_spurious_email_prefix(_clean_email(parsed.get("email") or parsed.get("Email") or ""))
    phone = parsed.get("phone") or parsed.get("Phone") or ""
    university = parsed.get("university") or parsed.get("University") or ""
    # New explicit fields (gracefully handle absence by falling back to legacy keys)
    bachelor_degree = parsed.get("bachelorDegree") or parsed.get("BachelorDegree") or parsed.get("degree") or parsed.get("Degree") or ""
    bachelor_university = parsed.get("bachelorUniversity") or parsed.get("BachelorUniversity") or parsed.get("university") or parsed.get("University") or ""
    bachelor_cgpa = _to_float(parsed.get("bachelorCGPA") or parsed.get("BachelorCGPA") or parsed.get("cgpa") or parsed.get("CGPA"), 0.0)
    masters_degree = parsed.get("mastersDegree") or parsed.get("MastersDegree") or ""
    masters_university = parsed.get("mastersUniversity") or parsed.get("MastersUniversity") or ""
    masters_cgpa = _to_float(parsed.get("mastersCGPA") or parsed.get("MastersCGPA"), 0.0)
    degree = bachelor_degree  # legacy compatibility
    university = bachelor_university  # legacy compatibility
    cgpa = bachelor_cgpa  # legacy compatibility
    tenth = _to_float(parsed.get("tenthPercentage") or parsed.get("10th Percentage"), 0.0)
    twelfth = _to_float(parsed.get("twelfthPercentage") or parsed.get("12th Percentage"), 0.0)

    def _as_list(v):
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            return [s.strip() for s in re.split(r",|\n|•|\u2022|\|", v) if s.strip()]
        return []

    def _as_project_list(v):
        """Convert projects to structured objects with title and description"""
        if v is None:
            return []
        if isinstance(v, list):
            # Handle both string arrays and object arrays
            result = []
            for item in v:
                if isinstance(item, dict):
                    # Already structured object
                    result.append({
                        "title": item.get("title", ""),
                        "description": item.get("description", "")
                    })
                elif isinstance(item, str):
                    # Convert string to structured object
                    result.append({
                        "title": item.strip(),
                        "description": ""
                    })
            return result
        if isinstance(v, str):
            # Convert comma/line separated string to structured objects
            titles = [s.strip() for s in re.split(r",|\n|•|\u2022|\|", v) if s.strip()]
            return [{"title": title, "description": ""} for title in titles]
        return []

    skills = _as_list(parsed.get("skills") or parsed.get("Skills"))
    projects = _as_project_list(parsed.get("projects") or parsed.get("Projects"))
    internships = _as_list(parsed.get("internships") or parsed.get("Internships"))
    achievements = _as_list(parsed.get("achievements") or parsed.get("Achievements"))
    # Certifications may appear under multiple possible keys
    certifications = _as_list(
        parsed.get("certifications") or parsed.get("Certifications") or 
        parsed.get("certs") or parsed.get("Certificates") or
        parsed.get("certificates") or parsed.get("training") or
        parsed.get("Training") or parsed.get("licenses")
    )

    # Enhanced heuristic fallback: if still empty, scan raw content for certification patterns
    if not certifications:
        possible = []
        cert_patterns = [
            # Platform-specific
            r"AWS\s+(Certified|Certificate)",
            r"Azure\s+(Certified|Certificate|Fundamentals)",
            r"Google\s+(Cloud|Certified|Certificate)",
            r"Microsoft\s+(Certified|Certificate)",
            r"Oracle\s+(Certified|Certificate)",
            r"Cisco\s+(Certified|CCNA|CCNP)",
            r"Red\s+Hat\s+Certified",
            r"CompTIA\s+",
            
            # Course platforms
            r"Coursera",
            r"Udemy",
            r"edX",
            r"Udacity",
            r"LinkedIn\s+Learning",
            r"Pluralsight",
            
            # General patterns
            r"Certified\s+\w+\s+(Professional|Associate|Expert|Developer|Engineer|Administrator)",
            r"\w+\s+Certification",
            r"Certificate\s+(of|in)\s+\w+",
            
            # Technology specific
            r"(Python|Java|JavaScript|Docker|Kubernetes|Terraform)\s+(Certified|Certificate|Certification)",
            r"Scrum\s+(Master|Product Owner|PSM|PSPO)",
            r"PMP\s+Certified",
            r"ITIL\s+(Foundation|Certified)",
            r"(Machine Learning|Deep Learning|Data Science|AI)\s+(Certification|Certificate|Specialization)",
        ]
        
        combined_pattern = "|".join(cert_patterns)
        
        for line in content.splitlines():
            l = line.strip()
            if not l or len(l) < 5:
                continue
                
            if re.search(combined_pattern, l, re.IGNORECASE):
                # Avoid adding section headers or very short lines
                lower_l = l.lower()
                if (len(l.split()) > 1 and 
                    not lower_l.startswith(("experience", "project", "education", "skill")) and
                    not l.isupper()):
                    possible.append(l)
        
        # Remove duplicates
        seen = set()
        unique_certs = []
        for cert in possible:
            cert_lower = cert.lower()
            if cert_lower not in seen:
                seen.add(cert_lower)
                unique_certs.append(cert)
        certifications = unique_certs[:15]

    # Normalize phone formatting a bit (enhanced)
    if isinstance(phone, str):
        raw_phone = phone
        ph_digits = re.sub(r"[^+\d]", "", raw_phone)
        if ph_digits.startswith('+'):
            cc_body = ph_digits[1:]
            phone = '+' + re.sub(r"\D", "", cc_body)
        else:
            phone = re.sub(r"\D", "", ph_digits)
        # Indian formatting heuristic
        if phone.startswith('+91') and len(phone) >= 13:
            phone = '+91 ' + phone[-10:]
        elif len(phone) == 10 and not phone.startswith('+'):
            phone = phone  # leave plain 10-digit

    # Dedupe and trim skills
    def _dedupe(seq: List[str]) -> List[str]:
        seen = set()
        out = []
        for item in seq:
            key = item.strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(item.strip())
        return out

    skills = _dedupe(skills)[:50]
    projects = projects[:20]
    internships = internships[:20]
    achievements = achievements[:20]
    certifications = certifications[:30]

    return {
        "name": name,
        "email": email,
        "phone": phone,
        # Legacy generic fields (mapped to bachelor)
        "university": university,
        "degree": degree,
        "cgpa": cgpa,
        "tenthPercentage": tenth,
        "twelfthPercentage": twelfth,
        "skills": skills,
        "projects": projects,
    "internships": internships,
    "achievements": achievements,
    "certifications": certifications,
        # New explicit structured fields
        "bachelorDegree": bachelor_degree or "",
        "bachelorUniversity": bachelor_university or "",
        "bachelorCGPA": bachelor_cgpa,
        "mastersDegree": masters_degree or "",
        "mastersUniversity": masters_university or "",
        "mastersCGPA": masters_cgpa,
    }


def parse_resume(file_path: str) -> Dict:
    """Parse a resume file and return a dict.

        Returned fields (when detectable):
            - name, email, phone
            - university / degree / cgpa (bachelor), optional masters*
            - tenthPercentage, twelfthPercentage
            - skills (list[str])
            - projects (list[str])
            - internships (list[str])
            - achievements (list[str])
            - certifications (list[str])   <-- newly added
            - bachelorDegree, bachelorUniversity, bachelorCGPA
            - mastersDegree, mastersUniversity, mastersCGPA

        Extraction order prefers explicit JSON keys if an LLM response produced structured output; otherwise
        a lightweight regex / heuristic fallback is used.
        """
    print(f"\n{'='*70}")
    print(f"[PARSE] Starting resume parse: {os.path.basename(file_path)}")
    print(f"{'='*70}")
    
    text = _extract_text(file_path)
    
    if not text:
        print("[PARSE] ERROR: No text extracted from file!")
        return {
            "name": "",
            "email": "",
            "phone": "",
            "university": "",
            "degree": "",
            "cgpa": 0.0,
            "tenthPercentage": 0.0,
            "twelfthPercentage": 0.0,
            "skills": [],
            "projects": [],
            "internships": [],
            "achievements": [],
            "certifications": [],
            "bachelorDegree": "",
            "bachelorUniversity": "",
            "bachelorCGPA": 0.0,
            "mastersDegree": "",
            "mastersUniversity": "",
            "mastersCGPA": 0.0,
        }
    
    print(f"[PARSE] Extracted {len(text)} characters total")
    print(f"[PARSE] First 200 chars: {text[:200]}...")

    # Try API-first, but handle corporate network issues gracefully
    try:
        print("[PARSE] Attempting Perplexity API parsing...")
        result = _call_perplexity_api(text)
        print(f"[PARSE] ✓ API parsing successful")
        print(f"[PARSE] Extracted: name={result.get('name')}, email={result.get('email')}, phone={result.get('phone')}")
        return result
    except requests.exceptions.RequestException as e:
        print(f"[PARSE] API request failed (network issue): {e}")
        print("[PARSE] Falling back to regex extraction...")
        return _regex_fallback(text)
    except Exception as e:
        print(f"[PARSE] API parsing failed: {type(e).__name__}: {e}")
        print("[PARSE] Falling back to regex extraction...")
        # Fallback to regex extraction
        return _regex_fallback(text)


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path or not os.path.exists(path):
        print("Usage: python -m utils.resume_parser <path-to-resume.(pdf|docx|txt)>")
        sys.exit(2)
    res = parse_resume(path)
    print(json.dumps(res, indent=2, ensure_ascii=False))
