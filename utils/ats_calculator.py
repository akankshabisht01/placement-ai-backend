import re
from typing import Dict, List, Tuple
import json
import difflib
from data.domain_data import get_all_skills

# Try to import grammar checker with fallback
try:
    from utils.grammar_checker import check_resume_grammar_spelling
    GRAMMAR_CHECKER_AVAILABLE = True
except ImportError:
    GRAMMAR_CHECKER_AVAILABLE = False
    def check_resume_grammar_spelling(resume_data):
        """Fallback when grammar checker is unavailable"""
        return {
            'total_errors': 0,
            'spelling_errors': [],
            'grammar_errors': [],
            'professional_errors': []
        }

class ATSCalculator:
    """
    ATS (Applicant Tracking System) Score Calculator
    Evaluates resume based on various ATS-friendly criteria
    """
    
    def __init__(self):
        # Keywords that ATS systems typically look for
        self.ats_keywords = {
            'technical_skills': [
                'python', 'java', 'javascript', 'react', 'angular', 'vue', 'node.js',
                'sql', 'mysql', 'postgresql', 'mongodb', 'aws', 'azure', 'docker',
                'kubernetes', 'git', 'github', 'agile', 'scrum', 'machine learning',
                'artificial intelligence', 'data science', 'analytics', 'tableau',
                'power bi', 'excel', 'powerpoint', 'word', 'linux', 'windows',
                'html', 'css', 'bootstrap', 'jquery', 'php', 'ruby', 'go', 'rust',
                'c++', 'c#', '.net', 'spring', 'django', 'flask', 'express',
                'tensorflow', 'pytorch', 'pandas', 'numpy', 'scikit-learn'
            ],
            'soft_skills': [
                'leadership', 'teamwork', 'communication', 'problem solving',
                'critical thinking', 'time management', 'project management',
                'collaboration', 'adaptability', 'creativity', 'analytical',
                'detail oriented', 'self motivated', 'initiative', 'mentoring'
            ],
            'education_keywords': [
                'bachelor', 'master', 'degree', 'diploma', 'certification',
                'course', 'training', 'university', 'college', 'institute',
                'cgpa', 'gpa', 'percentage', 'grade', 'honors', 'distinction'
            ],
            'experience_keywords': [
                'experience', 'internship', 'project', 'work', 'employment',
                'position', 'role', 'responsibility', 'achievement', 'accomplishment',
                'developed', 'created', 'implemented', 'managed', 'led', 'coordinated',
                'designed', 'built', 'improved', 'optimized', 'delivered'
            ]
        }
        
        # ATS-friendly format requirements
        self.format_requirements = {
            'contact_info': ['email', 'phone', 'address'],
            'sections': ['education', 'experience', 'skills', 'projects'],
            'file_formats': ['.pdf', '.docx', '.doc'],
            'keywords_density': 0.02,  # 2% keyword density
            'length_optimal': (1, 2),  # 1-2 pages
            'font_size': (10, 12),     # 10-12pt font
            'margins': (0.5, 1.0)      # 0.5-1 inch margins
        }
    
    def _normalize_parsed_resume(self, resume_data: Dict) -> Dict:
        """Normalize parsed resume dict to legacy-friendly keys.

        Ensures the following keys exist and are populated when possible:
          - name, email, phone
          - degree, university, cgpa
          - tenthPercentage, twelfthPercentage
          - skills, projects, internships, achievements
        """
        data: Dict = dict(resume_data or {})

        # Degree/university/cgpa: prefer new explicit bachelor* fields
        degree = data.get('degree') or data.get('bachelorDegree') or ''
        university = data.get('university') or data.get('bachelorUniversity') or ''
        # Use bachelorCGPA if present, else fall back to generic cgpa/collegeCGPA
        cgpa_val = (
            data.get('bachelorCGPA') if data.get('bachelorCGPA') is not None else data.get('cgpa')
        )
        if cgpa_val is None:
            cgpa_val = data.get('collegeCGPA')

        # Coerce cgpa to float defensively
        try:
            cgpa = float(cgpa_val) if cgpa_val is not None else 0.0
        except Exception:
            cgpa = 0.0

        # Percentages
        def _to_float(v, default=0.0):
            try:
                return float(v)
            except Exception:
                return float(default)

        tenth = _to_float(data.get('tenthPercentage'), 0.0)
        twelfth = _to_float(data.get('twelfthPercentage'), 0.0)

        # List-like fields: accept string or list, normalize to list[str]
        def _as_list(v):
            if v is None:
                return []
            if isinstance(v, list):
                return [str(x) for x in v if str(x).strip()]
            if isinstance(v, str):
                parts = re.split(r",|\n|•|\u2022|;|\|", v)
                return [p.strip() for p in parts if p and p.strip()]
            return []

        normalized = {
            'name': data.get('name') or '',
            'email': data.get('email') or '',
            'phone': data.get('phone') or data.get('mobile') or '',
            'degree': degree,
            'university': university,
            'cgpa': cgpa,
            'tenthPercentage': tenth,
            'twelfthPercentage': twelfth,
            'skills': _as_list(data.get('skills')),
            'projects': _as_list(data.get('projects')),
            'internships': _as_list(data.get('internships')),
            'achievements': _as_list(data.get('achievements')),
            # Keep original fields as well for any downstream logic that might use them
            'bachelorDegree': data.get('bachelorDegree') or '',
            'bachelorUniversity': data.get('bachelorUniversity') or '',
            'bachelorCGPA': _to_float(data.get('bachelorCGPA'), cgpa),
            'mastersDegree': data.get('mastersDegree') or '',
            'mastersUniversity': data.get('mastersUniversity') or '',
            'mastersCGPA': _to_float(data.get('mastersCGPA'), 0.0),
        }

        return normalized

    def _build_allowed_skill_set(self) -> set:
        """Construct a set of allowed/recognized skills/keywords.

        Combines curated technical/soft skills with the system's domain skills.
        Matching will be done in a case-insensitive, token-normalized manner.
        """
        curated = set([
            # Technical
            'python','java','javascript','typescript','react','angular','vue','node.js','node','express','django','flask',
            'spring','spring boot','c','c++','c#','.net','php','ruby','go','rust','kotlin','swift',
            'sql','mysql','postgresql','postgres','mongodb','redis','graphql','rest','api',
            'docker','kubernetes','aws','azure','gcp','git','github','gitlab','linux','windows','bash','powershell',
            'html','css','sass','tailwind','bootstrap','jquery',
            'pandas','numpy','scikit-learn','sklearn','tensorflow','pytorch','nlp','opencv','computer vision',
            'power bi','tableau','excel',
            # Soft/general
            'leadership','teamwork','communication','problem solving','critical thinking','time management',
            'project management','collaboration','adaptability','creativity','analytical'
        ])

        # Include skills from domain dataset
        try:
            domain_skills = {s.lower() for s in get_all_skills()}
        except Exception:
            domain_skills = set()

        allowed = curated | domain_skills

        # Normalization: unify common aliases
        normalized_allowed = set()
        alias_map = {
            'node.js': 'node',
            'postgresql': 'postgres',
            'scikit-learn': 'sklearn',
        }
        for s in allowed:
            s_clean = s.strip().lower()
            s_clean = alias_map.get(s_clean, s_clean)
            normalized_allowed.add(s_clean)
        return normalized_allowed

    def _normalize_skill_text(self, text: str) -> str:
        t = (text or '').strip().lower()
        t = re.sub(r"[()\[\]{}]|\+|\.|,|;|:|/", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
        # Common aliases
        alias_map = {
            'node.js': 'node',
            'node js': 'node',
            'c sharp': 'c#',
            'c plus plus': 'c++',
            'scikit learn': 'sklearn',
            'ms excel': 'excel',
            'powerbi': 'power bi'
        }
        return alias_map.get(t, t)

    def calculate_ats_score(self, resume_data: Dict) -> Dict:
        """
        Calculate ATS score based on resume data
        Returns score (0-100) and detailed feedback
        """
        # Normalize input for compatibility with new parser schema
        resume_data = self._normalize_parsed_resume(resume_data)
        # Build allowed skills once per calculation
        allowed_skills = self._build_allowed_skill_set()

        score_breakdown = {
            'contact_info': 0,
            'education': 0,
            'experience': 0,
            'skills': 0,
            'keywords': 0,
            'format': 0,
            'projects': 0,
            'achievements': 0,
            'spelling_grammar': 0
        }

        # Per-category maximum points (used to clamp returned values)
        # Optimized distribution: Skills (25%) is now primary factor, matching real ATS systems
        category_max = {
            'contact_info': 5,       # Reduced from 15 - basic info shouldn't dominate score
            'education': 15,         # Unchanged - appropriate weight for academics
            'experience': 20,        # Unchanged - appropriate weight for work history
            'skills': 25,            # Increased from 15 - most critical ATS matching criterion
            'keywords': 5,           # Reduced from 15 - avoids overlap with skills
            'format': 5,             # Unchanged - appropriate for readability
            'projects': 15,          # Increased from 10 - demonstrates practical skills
            'achievements': 5,       # Unchanged - appropriate for extras
            'spelling_grammar': 5    # Reduced from 10 - quality check, not main driver
        }
        
        tips = []
        flagged_issues = {
            'critical': [],  # Issues that severely impact ATS compatibility
            'major': [],     # Significant issues that need attention
            'minor': []      # Minor issues for optimization
        }
        total_score = 0
        
        # 1. Contact Information (15 points)
        contact_score, contact_tips, contact_issues = self._evaluate_contact_info(resume_data)
        # Clamp contact score to [0, max]
        contact_score = max(0, min(category_max['contact_info'], int(contact_score)))
        score_breakdown['contact_info'] = contact_score
        tips.extend(contact_tips)
        self._categorize_issues(contact_issues, flagged_issues)
        
        # 2. Education Section (15 points)
        education_score, education_tips, education_issues = self._evaluate_education(resume_data)
        # Clamp education score to [0, max]
        education_score = max(0, min(category_max['education'], int(education_score)))
        score_breakdown['education'] = education_score
        tips.extend(education_tips)
        self._categorize_issues(education_issues, flagged_issues)
        
        # 3. Experience Section (20 points)
        experience_score, experience_tips, experience_issues = self._evaluate_experience(resume_data)
        experience_score = max(0, min(category_max['experience'], int(experience_score)))
        score_breakdown['experience'] = experience_score
        tips.extend(experience_tips)
        self._categorize_issues(experience_issues, flagged_issues)
        
        # 4. Skills Section (15 points)
        skills_score, skills_tips, skills_issues = self._evaluate_skills(resume_data)
        skills_score = max(0, min(category_max['skills'], int(skills_score)))
        score_breakdown['skills'] = skills_score
        tips.extend(skills_tips)
        self._categorize_issues(skills_issues, flagged_issues)
        
        # 5. Keywords Optimization (15 points)
        keywords_score, keywords_tips, keywords_issues = self._evaluate_keywords(resume_data)
        keywords_score = max(0, min(category_max['keywords'], int(keywords_score)))
        score_breakdown['keywords'] = keywords_score
        tips.extend(keywords_tips)
        self._categorize_issues(keywords_issues, flagged_issues)
        
        # 6. Projects Section (10 points)
        projects_score, projects_tips, projects_issues = self._evaluate_projects(resume_data)
        projects_score = max(0, min(category_max['projects'], int(projects_score)))
        score_breakdown['projects'] = projects_score
        tips.extend(projects_tips)
        self._categorize_issues(projects_issues, flagged_issues)
        
        # 7. Achievements Section (5 points)
        achievements_score, achievements_tips, achievements_issues = self._evaluate_achievements(resume_data)
        achievements_score = max(0, min(category_max['achievements'], int(achievements_score)))
        score_breakdown['achievements'] = achievements_score
        tips.extend(achievements_tips)
        self._categorize_issues(achievements_issues, flagged_issues)
        
        # 8. Format & Structure (5 points)
        format_score, format_tips, format_issues = self._evaluate_format(resume_data)
        format_score = max(0, min(category_max['format'], int(format_score)))
        score_breakdown['format'] = format_score
        tips.extend(format_tips)
        self._categorize_issues(format_issues, flagged_issues)
        
        # 9. Spelling & Grammar (5 points) - Enhanced with comprehensive checker
        spelling_score, spelling_tips, spelling_issues, grammar_details = self._evaluate_spelling_grammar_enhanced(resume_data)
        spelling_score = max(0, min(category_max['spelling_grammar'], int(spelling_score)))
        score_breakdown['spelling_grammar'] = spelling_score
        tips.extend(spelling_tips)
        self._categorize_issues(spelling_issues, flagged_issues)
        
        # Aggregate raw score (use clamped category values)
        total_score = sum(score_breakdown.values())

        # Penalties and boosts to better separate weak vs strong resumes
        penalties = 0
        boosts = 0

        # Content length heuristic (too short => weak; too long dense => mild penalty)
        all_text_fields = []
        all_text_fields.append(resume_data.get('name', ''))
        all_text_fields.append(resume_data.get('degree', ''))
        all_text_fields.append(resume_data.get('university', ''))
        all_text_fields.extend(resume_data.get('skills', []))
        all_text_fields.extend(resume_data.get('projects', []))
        all_text_fields.extend(resume_data.get('internships', []))
        all_text_fields.extend(resume_data.get('achievements', []))
        concat_text = ' '.join([str(x) for x in all_text_fields]).strip()
        word_count = len(re.findall(r"[A-Za-z0-9#\+\.]+", concat_text))
        if word_count < 80:
            penalties += 10  # Very thin resume
        elif word_count < 150:
            penalties += 5
        elif word_count > 1000:
            penalties += 3  # Too verbose may be unfocused

        # Empty section penalties
        empty_sections = 0
        for key in ['skills','projects','internships','achievements']:
            val = resume_data.get(key, [])
            if not val:
                empty_sections += 1
        penalties += empty_sections * 3

        # Keyword stuffing detection: too many repeated tokens vs unique (softened for technical resumes)
        tokens = [t for t in re.split(r"[^a-z0-9+#.]+", concat_text.lower()) if t]
        unique_tokens = len(set(tokens))
        repeated_tokens = len(tokens) - unique_tokens
        # Raised threshold from 1.5 to 2.5 to avoid penalizing legitimate technical content
        # Technical resumes naturally repeat framework/tech names across projects
        if len(tokens) >= 50 and repeated_tokens / max(unique_tokens, 1) > 2.5:
            penalties += 5  # Reduced from 8 to 5
            tips.append("💡 Consider reducing keyword repetition for better readability")

        # Unrecognized skills inflation: many skills but few recognized by allowlist
        user_skills = [self._normalize_skill_text(str(s)) for s in resume_data.get('skills', [])]
        recognized = [s for s in user_skills if s in allowed_skills]
        if len(user_skills) >= 8 and len(recognized) <= 0.25 * len(user_skills):
            penalties += 7

        # Slight boost for presence of both bachelor and projects
        if (resume_data.get('degree') or resume_data.get('bachelorDegree')) and resume_data.get('projects'):
            boosts += 3

        total_score = max(0, min(100, total_score - penalties + boosts))
        
        # Determine overall rating with tighter bands
        if total_score >= 88:
            rating = "Excellent"
            rating_color = "green"
        elif total_score >= 72:
            rating = "Good"
            rating_color = "blue"
        elif total_score >= 55:
            rating = "Fair"
            rating_color = "yellow"
        else:
            rating = "Needs Improvement"
            rating_color = "red"
        
        # Generate job description analysis if provided
        job_match_analysis = self._analyze_job_description_match(resume_data)
        
        return {
            'total_score': total_score,
            'rating': rating,
            'rating_color': rating_color,
            'score_breakdown': score_breakdown,
            'tips': tips,
            'flagged_issues': flagged_issues,
            'strengths': self._identify_strengths(score_breakdown),
            'improvements': self._identify_improvements(score_breakdown),
            'corrections': self._generate_corrections(resume_data, score_breakdown),
            'grammar_details': grammar_details,
            'job_match': job_match_analysis  # NEW: Job description matching analysis
        }
    
    def _analyze_job_description_match(self, resume_data: Dict) -> Dict:
        """Analyze how well the resume matches the job description if provided."""
        job_description = resume_data.get('job_description', '')
        
        if not job_description or len(job_description.strip()) < 50:
            return None  # No job description provided or too short
        
        job_text = job_description.lower()
        
        # Extract keywords from job description
        allowed = self._build_allowed_skill_set()
        words = [w for w in re.split(r"[^a-z0-9+#.]+", job_text) if w]
        
        # Create bigrams for multi-word skills
        tokens = set(words)
        for i in range(len(words) - 1):
            tokens.add((words[i] + ' ' + words[i + 1]).strip())
        
        # Normalize and find matching skills from allowlist
        job_keywords = set()
        for t in tokens:
            norm = self._normalize_skill_text(t)
            if norm in allowed:
                job_keywords.add(norm)
        
        # Get user's skills
        user_skills_raw = resume_data.get('skills', [])
        user_skills = {self._normalize_skill_text(str(s)) for s in user_skills_raw if self._normalize_skill_text(str(s)) in allowed}
        
        # Get skills from projects and experience
        all_resume_text = ' '.join([str(p) for p in resume_data.get('projects', [])])
        all_resume_text += ' ' + ' '.join([str(e) for e in resume_data.get('experience', [])])
        all_resume_text += ' ' + ' '.join([str(i) for i in resume_data.get('internships', [])])
        all_resume_text = all_resume_text.lower()
        
        resume_words = [w for w in re.split(r"[^a-z0-9+#.]+", all_resume_text) if w]
        resume_tokens = set(resume_words)
        for i in range(len(resume_words) - 1):
            resume_tokens.add((resume_words[i] + ' ' + resume_words[i + 1]).strip())
        
        resume_keywords = set()
        for t in resume_tokens:
            norm = self._normalize_skill_text(t)
            if norm in allowed:
                resume_keywords.add(norm)
        
        # Combine user skills and resume keywords
        all_user_keywords = user_skills | resume_keywords
        
        # Calculate match metrics
        matched_keywords = job_keywords & all_user_keywords
        missing_from_resume = job_keywords - all_user_keywords
        
        # Calculate match percentage
        match_percentage = (len(matched_keywords) / len(job_keywords) * 100) if job_keywords else 0
        
        # Determine match rating
        if match_percentage >= 80:
            match_rating = "Excellent Match"
            match_color = "green"
            match_emoji = "🎯"
        elif match_percentage >= 60:
            match_rating = "Good Match"
            match_color = "blue"
            match_emoji = "👍"
        elif match_percentage >= 40:
            match_rating = "Fair Match"
            match_color = "yellow"
            match_emoji = "⚠️"
        else:
            match_rating = "Needs Work"
            match_color = "red"
            match_emoji = "📈"
        
        return {
            'has_job_description': True,
            'match_percentage': round(match_percentage, 1),
            'match_rating': match_rating,
            'match_color': match_color,
            'match_emoji': match_emoji,
            'job_keywords_count': len(job_keywords),
            'matched_keywords': sorted(list(matched_keywords))[:15],  # Top 15
            'missing_keywords': sorted(list(missing_from_resume))[:10],  # Top 10 missing
            'recommendation': self._get_job_match_recommendation(match_percentage, list(missing_from_resume)[:5])
        }
    
    def _get_job_match_recommendation(self, match_percentage: float, missing_keywords: List[str]) -> str:
        """Generate recommendation based on job match analysis."""
        if match_percentage >= 80:
            return "Your resume is well-aligned with this job. Focus on highlighting your relevant experience during interviews."
        elif match_percentage >= 60:
            if missing_keywords:
                return f"Good match! Consider adding these keywords to strengthen your application: {', '.join(missing_keywords)}"
            return "Good match! Review the job description for any specific requirements you can emphasize."
        elif match_percentage >= 40:
            if missing_keywords:
                return f"Moderate match. Add these missing skills if you have them: {', '.join(missing_keywords)}. Consider tailoring your resume for this role."
            return "Moderate match. Consider customizing your resume to better highlight relevant experience."
        else:
            if missing_keywords:
                return f"Low match. This role requires skills you may not have listed: {', '.join(missing_keywords)}. Consider acquiring these skills or targeting roles that better match your profile."
            return "Low match. This role may require different skills than what's on your resume. Consider roles that better match your current expertise."

    def _generate_corrections(self, resume_data: Dict, score_breakdown: Dict) -> Dict:
        """Generate targeted corrections: better keywords, action verbs, structure fixes, and skill-project gap analysis."""
        corrections: Dict = {}

        allowed = self._build_allowed_skill_set()
        user_skills_raw = resume_data.get('skills', [])
        user_skills = [self._normalize_skill_text(str(s)) for s in user_skills_raw]
        recognized = [s for s in user_skills if s in allowed]
        missing = sorted(list((allowed - set(recognized)) - {''}))

        # ========================================
        # IMPROVED DOMAIN DETECTION
        # ========================================
        # Expanded domain buckets with weighted keywords (core skills have higher weight)
        domain_config = {
            'frontend': {
                'core': {'react', 'angular', 'vue', 'svelte', 'nextjs', 'next.js', 'nuxt', 'gatsby'},  # weight: 3
                'secondary': {'html', 'css', 'javascript', 'typescript', 'sass', 'scss', 'less', 'tailwind', 'bootstrap', 'material ui', 'chakra', 'styled-components'},  # weight: 2
                'related': {'webpack', 'vite', 'babel', 'eslint', 'prettier', 'storybook', 'jest', 'cypress', 'playwright', 'redux', 'zustand', 'mobx', 'graphql', 'apollo', 'responsive', 'accessibility', 'a11y', 'pwa'}  # weight: 1
            },
            'backend': {
                'core': {'node', 'express', 'django', 'flask', 'fastapi', 'spring', 'spring boot', 'rails', 'laravel', 'asp.net', '.net', 'nestjs'},
                'secondary': {'rest', 'api', 'graphql', 'grpc', 'microservices', 'websocket', 'socket.io'},
                'related': {'jwt', 'oauth', 'authentication', 'authorization', 'middleware', 'orm', 'sequelize', 'prisma', 'typeorm', 'celery', 'rabbitmq', 'kafka'}
            },
            'fullstack': {
                'core': {'mern', 'mean', 'lamp', 'full stack', 'fullstack'},
                'secondary': set(),  # Detected by having both frontend + backend
                'related': set()
            },
            'data_science': {
                'core': {'pandas', 'numpy', 'scikit-learn', 'sklearn', 'jupyter', 'data analysis', 'data science'},
                'secondary': {'matplotlib', 'seaborn', 'plotly', 'scipy', 'statsmodels', 'statistics', 'regression', 'classification'},
                'related': {'excel', 'tableau', 'power bi', 'looker', 'data visualization', 'eda', 'feature engineering', 'a/b testing', 'hypothesis testing'}
            },
            'machine_learning': {
                'core': {'tensorflow', 'pytorch', 'keras', 'machine learning', 'ml', 'deep learning', 'neural network'},
                'secondary': {'cnn', 'rnn', 'lstm', 'transformer', 'bert', 'gpt', 'llm', 'nlp', 'computer vision', 'opencv'},
                'related': {'model training', 'hyperparameter', 'cross-validation', 'mlops', 'mlflow', 'wandb', 'huggingface', 'langchain', 'rag', 'fine-tuning', 'embedding'}
            },
            'data_engineering': {
                'core': {'spark', 'hadoop', 'airflow', 'data pipeline', 'etl', 'data engineering'},
                'secondary': {'kafka', 'flink', 'beam', 'dbt', 'snowflake', 'databricks', 'redshift', 'bigquery'},
                'related': {'data warehouse', 'data lake', 'batch processing', 'stream processing', 'parquet', 'avro'}
            },
            'devops': {
                'core': {'docker', 'kubernetes', 'k8s', 'jenkins', 'ci/cd', 'devops', 'terraform', 'ansible'},
                'secondary': {'helm', 'argocd', 'gitlab ci', 'github actions', 'circleci', 'prometheus', 'grafana', 'elk', 'datadog'},
                'related': {'infrastructure as code', 'iac', 'monitoring', 'logging', 'alerting', 'site reliability', 'sre', 'bash', 'shell', 'linux'}
            },
            'cloud': {
                'core': {'aws', 'azure', 'gcp', 'google cloud', 'cloud computing'},
                'secondary': {'ec2', 's3', 'lambda', 'ecs', 'eks', 'rds', 'dynamodb', 'cloudformation', 'azure functions', 'cloud functions', 'firebase'},
                'related': {'serverless', 'iaas', 'paas', 'saas', 'cloud native', 'multi-cloud', 'hybrid cloud', 'cost optimization'}
            },
            'database': {
                'core': {'sql', 'mysql', 'postgresql', 'postgres', 'mongodb', 'oracle', 'sql server'},
                'secondary': {'redis', 'elasticsearch', 'cassandra', 'dynamodb', 'neo4j', 'mariadb', 'sqlite', 'supabase'},
                'related': {'database design', 'normalization', 'indexing', 'query optimization', 'transactions', 'acid', 'replication', 'sharding', 'nosql'}
            },
            'mobile': {
                'core': {'android', 'ios', 'react native', 'flutter', 'swift', 'kotlin', 'mobile development'},
                'secondary': {'swiftui', 'jetpack compose', 'xamarin', 'ionic', 'cordova', 'expo'},
                'related': {'mobile ui', 'push notifications', 'app store', 'play store', 'mobile testing', 'responsive design'}
            },
            'security': {
                'core': {'cybersecurity', 'penetration testing', 'ethical hacking', 'security', 'infosec'},
                'secondary': {'owasp', 'vulnerability', 'encryption', 'ssl', 'tls', 'firewall', 'ids', 'ips', 'siem'},
                'related': {'authentication', 'authorization', 'oauth', 'jwt', 'xss', 'sql injection', 'csrf', 'security audit', 'compliance'}
            },
            'blockchain': {
                'core': {'blockchain', 'solidity', 'ethereum', 'web3', 'smart contract'},
                'secondary': {'defi', 'nft', 'dapp', 'hardhat', 'truffle', 'metamask', 'ipfs'},
                'related': {'cryptocurrency', 'bitcoin', 'consensus', 'distributed ledger'}
            },
            'game_dev': {
                'core': {'unity', 'unreal', 'game development', 'godot', 'game engine'},
                'secondary': {'c#', 'c++', 'opengl', 'directx', 'vulkan', 'shader'},
                'related': {'game design', '3d modeling', 'blender', 'animation', 'physics engine'}
            },
            'embedded': {
                'core': {'embedded', 'arduino', 'raspberry pi', 'iot', 'microcontroller', 'firmware'},
                'secondary': {'c', 'c++', 'rtos', 'arm', 'fpga', 'verilog', 'vhdl'},
                'related': {'hardware', 'sensor', 'actuator', 'serial communication', 'i2c', 'spi', 'uart'}
            },
            'qa_testing': {
                'core': {'selenium', 'testing', 'qa', 'quality assurance', 'test automation'},
                'secondary': {'cypress', 'playwright', 'jest', 'mocha', 'pytest', 'junit', 'testng'},
                'related': {'unit testing', 'integration testing', 'e2e testing', 'tdd', 'bdd', 'postman', 'api testing', 'load testing', 'jmeter'}
            }
        }

        # Calculate domain scores with weights
        domain_scores = {}
        recognized_set = set(recognized)
        
        # Also analyze project text for better domain detection
        project_text = ' '.join(str(p).lower() for p in resume_data.get('projects', []))
        internship_text = ' '.join(str(i).lower() for i in resume_data.get('internships', []))
        context_text = project_text + ' ' + internship_text
        
        for domain, config in domain_config.items():
            score = 0
            # Core skills (weight 3)
            core_matches = recognized_set & config['core']
            score += len(core_matches) * 3
            
            # Secondary skills (weight 2)
            secondary_matches = recognized_set & config['secondary']
            score += len(secondary_matches) * 2
            
            # Related skills (weight 1)
            related_matches = recognized_set & config['related']
            score += len(related_matches) * 1
            
            # Bonus: Check if domain keywords appear in projects/internships
            domain_keywords_in_context = sum(1 for kw in (config['core'] | config['secondary']) if kw in context_text)
            score += domain_keywords_in_context * 0.5
            
            if score > 0:
                domain_scores[domain] = score
        
        # Special case: Detect fullstack if both frontend and backend are strong
        if domain_scores.get('frontend', 0) >= 4 and domain_scores.get('backend', 0) >= 4:
            domain_scores['fullstack'] = domain_scores.get('fullstack', 0) + 5
        
        # Sort domains by score and get active ones (score > 2)
        sorted_domains = sorted(domain_scores.items(), key=lambda x: x[1], reverse=True)
        active_domains = [d[0] for d in sorted_domains if d[1] > 2]
        primary_domain = sorted_domains[0][0] if sorted_domains else None
        
        # Legacy bucket mapping for backward compatibility
        buckets = {
            'web': domain_config['frontend']['core'] | domain_config['frontend']['secondary'] | domain_config['backend']['core'],
            'data_ml': domain_config['data_science']['core'] | domain_config['machine_learning']['core'] | domain_config['data_engineering']['core'],
            'devops_cloud': domain_config['devops']['core'] | domain_config['cloud']['core'],
            'db': domain_config['database']['core'] | domain_config['database']['secondary'],
            'mobile': domain_config['mobile']['core'] | domain_config['mobile']['secondary']
        }
        active_buckets = {name for name, keys in buckets.items() if recognized_set & keys}

        # Adjacent keyword suggestions per domain (more specific)
        adjacent = {
            'frontend': ['typescript', 'nextjs', 'testing library', 'cypress', 'storybook', 'accessibility', 'performance optimization', 'pwa'],
            'backend': ['graphql', 'microservices', 'message queue', 'caching', 'rate limiting', 'api documentation', 'swagger'],
            'fullstack': ['system design', 'scalability', 'load balancing', 'caching strategies', 'api design'],
            'data_science': ['feature engineering', 'statistical analysis', 'a/b testing', 'data storytelling', 'business intelligence'],
            'machine_learning': ['mlops', 'model deployment', 'hyperparameter tuning', 'experiment tracking', 'model monitoring'],
            'data_engineering': ['data modeling', 'data governance', 'data quality', 'orchestration', 'real-time processing'],
            'devops': ['gitops', 'service mesh', 'chaos engineering', 'observability', 'incident management'],
            'cloud': ['cost optimization', 'security best practices', 'high availability', 'disaster recovery', 'multi-region'],
            'database': ['query optimization', 'database migration', 'data modeling', 'backup strategies', 'performance tuning'],
            'mobile': ['state management', 'offline support', 'push notifications', 'app performance', 'deep linking'],
            'security': ['threat modeling', 'security audit', 'vulnerability assessment', 'incident response', 'compliance'],
            'blockchain': ['smart contract security', 'gas optimization', 'token standards', 'defi protocols'],
            'game_dev': ['game physics', 'ai pathfinding', 'multiplayer networking', 'optimization'],
            'embedded': ['real-time systems', 'power management', 'communication protocols', 'debugging'],
            'qa_testing': ['test strategy', 'test coverage', 'ci integration', 'performance testing', 'security testing'],
            # Legacy buckets
            'web': ['typescript', 'unit testing', 'jest', 'oauth', 'jwt', 'caching', 'performance', 'accessibility'],
            'data_ml': ['feature engineering', 'cross-validation', 'model evaluation', 'pipeline', 'mlops', 'data preprocessing'],
            'devops_cloud': ['ci/cd', 'terraform', 'monitoring', 'autoscaling', 'cost optimization', 'logging'],
            'db': ['indexing', 'query optimization', 'normalization', 'transactions', 'replication'],
        }

        # High-value skills per domain
        high_value = {
            'frontend': ['react', 'typescript', 'nextjs', 'vue', 'tailwind', 'graphql'],
            'backend': ['node', 'python', 'graphql', 'microservices', 'redis', 'kafka'],
            'fullstack': ['typescript', 'graphql', 'docker', 'aws', 'system design'],
            'data_science': ['python', 'sql', 'pandas', 'tableau', 'power bi', 'statistics'],
            'machine_learning': ['python', 'tensorflow', 'pytorch', 'mlops', 'llm', 'nlp'],
            'data_engineering': ['spark', 'airflow', 'kafka', 'snowflake', 'dbt'],
            'devops': ['kubernetes', 'terraform', 'aws', 'ci/cd', 'prometheus'],
            'cloud': ['aws', 'azure', 'gcp', 'serverless', 'kubernetes'],
            'database': ['postgresql', 'mongodb', 'redis', 'elasticsearch'],
            'mobile': ['react native', 'flutter', 'kotlin', 'swift'],
            'security': ['penetration testing', 'owasp', 'encryption', 'siem'],
            'blockchain': ['solidity', 'web3', 'smart contract', 'defi'],
            'game_dev': ['unity', 'unreal', 'c++', 'shader'],
            'embedded': ['c', 'c++', 'rtos', 'arduino'],
            'qa_testing': ['selenium', 'cypress', 'jest', 'api testing'],
            # Legacy buckets
            'web': ['react', 'node', 'typescript', 'graphql', 'rest'],
            'data_ml': ['python', 'sql', 'pandas', 'numpy', 'sklearn', 'tensorflow', 'power bi', 'tableau'],
            'devops_cloud': ['aws', 'docker', 'kubernetes', 'ci/cd'],
            'db': ['postgres', 'mongodb', 'redis'],
        }

        # Build recommendations relevant to candidate's domains and not already present
        bucket_recs: List[str] = []
        
        # Prioritize primary domain suggestions
        if primary_domain:
            for kw in high_value.get(primary_domain, []):
                if kw in missing:
                    bucket_recs.append(kw)
            for kw in adjacent.get(primary_domain, []):
                kw_norm = self._normalize_skill_text(kw)
                if kw_norm in missing or kw_norm not in recognized_set:
                    bucket_recs.append(kw_norm)
        
        # Then add from other active domains
        for domain in active_domains[1:4]:  # Next 3 domains
            for kw in high_value.get(domain, [])[:3]:  # Top 3 from each
                if kw in missing and kw not in bucket_recs:
                    bucket_recs.append(kw)
        
        # Legacy bucket support
        for b in active_buckets:
            for kw in high_value.get(b, []):
                if kw in missing and kw not in bucket_recs:
                    bucket_recs.append(kw)
            for kw in adjacent.get(b, []):
                kw_norm = self._normalize_skill_text(kw)
                if kw_norm in missing and kw_norm not in bucket_recs:
                    bucket_recs.append(kw_norm)

        # Fallback: if no buckets detected, suggest a small neutral set
        if not bucket_recs:
            neutral = ['sql', 'git', 'python', 'javascript', 'docker']
            bucket_recs = [kw for kw in neutral if kw in missing]

        # De-duplicate and cap
        seen = set()
        recommended_keywords: List[str] = []
        for kw in bucket_recs:
            if kw not in seen:
                seen.add(kw)
                recommended_keywords.append(kw)
            if len(recommended_keywords) >= 12:
                break

        # Action verbs
        action_verbs = [
            'Designed','Developed','Implemented','Optimized','Automated','Refactored','Led','Collaborated','Deployed',
            'Architected','Integrated','Scaled','Reduced','Improved','Achieved','Delivered','Analyzed','Validated'
        ]

        # Structure fixes
        structure_tips = []
        # Ensure bullet format: Action verb + task + tech + outcome/metric
        structure_tips.append(
            'Use bullet format: Action verb + what you built + technologies + measurable outcome (%, time, cost).'
        )
        # Check for metrics in projects
        has_metric_proj = False
        for proj in resume_data.get('projects', []):
            if re.search(r"\b(\d+%|\d+ (?:ms|s|min|hrs|hours|days)|\d+\s*(?:users|requests|records|MB|GB))\b", str(proj)):
                has_metric_proj = True
                break
        if not has_metric_proj and resume_data.get('projects'):
            structure_tips.append('Add metrics to project bullets (e.g., reduced latency by 30%, handled 50k users).')

        # Sample bullet rewrites (heuristic)
        sample_rewrites = []
        if resume_data.get('projects'):
            first = str(resume_data['projects'][0])
            # Extract a technology from recognized skills if possible
            tech = (recognized[0] if recognized else 'React')
            sample_rewrites.append(
                f"Before: {first}\nAfter: Developed a {('web app' if 'web' in first.lower() else 'system')} using {tech}, "
                f"improving performance by 25% and reducing errors by 15%."
            )

        # ========================================
        # SKILL-PROJECT GAP ANALYSIS (NEW)
        # ========================================
        skill_project_gaps = []
        actionable_suggestions = []
        
        projects = resume_data.get('projects', [])
        if recognized and projects:
            # Analyze which skills are mentioned but never demonstrated in projects
            skills_in_projects = set()
            
            for proj in projects:
                text = str(proj).lower()
                words = [w for w in re.split(r"[^a-z0-9+#.]+", text) if w]
                
                # Create bigrams for multi-word skills
                for i in range(len(words) - 1):
                    words.append((words[i] + ' ' + words[i + 1]).strip())
                
                # Normalize and check against recognized skills
                norm_tokens = {self._normalize_skill_text(t) for t in words}
                skills_in_projects.update(norm_tokens & set(recognized))
            
            # Find skills that are listed but never used in projects
            unused_skills = [s for s in recognized if s not in skills_in_projects]
            
            # Categorize unused skills by domain for better suggestions
            unused_by_domain = {}
            for skill in unused_skills:
                for domain, domain_skills in buckets.items():
                    if skill in domain_skills:
                        if domain not in unused_by_domain:
                            unused_by_domain[domain] = []
                        unused_by_domain[domain].append(skill)
                        break
            
            # Generate personalized project suggestions
            domain_project_examples = {
                'web': [
                    'Build a full-stack web application with user authentication',
                    'Create a REST API with database integration',
                    'Develop a responsive e-commerce platform',
                    'Build a real-time chat application with WebSockets'
                ],
                'data_ml': [
                    'Create a machine learning model for predictive analytics',
                    'Build a data visualization dashboard',
                    'Develop an ETL pipeline for data processing',
                    'Implement a recommendation system'
                ],
                'devops_cloud': [
                    'Set up CI/CD pipeline with automated testing',
                    'Deploy containerized application to cloud platform',
                    'Implement infrastructure as code with monitoring',
                    'Create automated backup and disaster recovery system'
                ],
                'db': [
                    'Design and optimize a database schema for scalability',
                    'Build a data migration tool with performance optimization',
                    'Create a database monitoring and query optimization system',
                    'Implement database replication and caching strategy'
                ],
                'mobile': [
                    'Build a cross-platform mobile app with native features',
                    'Create a mobile app with offline-first architecture',
                    'Develop a location-based service mobile application',
                    'Build a mobile app with push notifications and real-time updates'
                ]
            }
            
            # Generate suggestions for each domain with unused skills
            for domain, skills_list in unused_by_domain.items():
                if len(skills_list) >= 2:  # Multiple unused skills in one domain
                    skill_project_gaps.append({
                        'type': 'missing_demonstration',
                        'skills': skills_list[:5],  # Cap at 5 skills
                        'domain': domain,
                        'severity': 'high',
                        'message': f"You listed {', '.join(skills_list[:3])} in your skills but no projects demonstrate them"
                    })
                    
                    # Pick a relevant project example
                    example = domain_project_examples.get(domain, ['Build a relevant project'])[0]
                    actionable_suggestions.append({
                        'category': 'Add Missing Project',
                        'priority': 'high',
                        'suggestion': f"Create a project using {', '.join(skills_list[:3])} to validate your expertise",
                        'example': f"Example: {example} using {', '.join(skills_list[:2])}",
                        'impact': 'Adding this project could increase your ATS score by 3-5 points'
                    })
                elif len(skills_list) == 1:
                    skill_project_gaps.append({
                        'type': 'missing_demonstration',
                        'skills': skills_list,
                        'domain': domain,
                        'severity': 'medium',
                        'message': f"Skill '{skills_list[0]}' is listed but not demonstrated in projects"
                    })
        
        # ========================================
        # CATEGORY-SPECIFIC ACTIONABLE TIPS (NEW)
        # ========================================
        
        # Analyze score breakdown to provide targeted tips
        # score_breakdown is now passed as a parameter from calculate_ats_score
        
        # Projects-specific tips
        projects_score = score_breakdown.get('projects', 0)
        if projects_score < 10:  # Out of 15
            if not any(re.search(r'\d+%|\d+x|\d+\s*(?:users|ms|GB)', str(p)) for p in projects):
                actionable_suggestions.append({
                    'category': 'Add Quantifiable Metrics',
                    'priority': 'high',
                    'suggestion': 'Include specific numbers to demonstrate project impact',
                    'example': 'Instead of "improved performance", write "reduced load time by 35%" or "handled 10K+ concurrent users"',
                    'impact': 'Adding metrics could increase your projects score by 2-3 points'
                })
            
            # Check for action verbs
            action_verb_pattern = r'\b(developed|designed|implemented|built|created|led|optimized|architected)\b'
            weak_verbs = sum(1 for p in projects if not re.search(action_verb_pattern, str(p).lower()))
            if weak_verbs > len(projects) / 2:
                actionable_suggestions.append({
                    'category': 'Use Action Verbs',
                    'priority': 'medium',
                    'suggestion': 'Start each project description with a strong action verb',
                    'example': 'Begin with: Developed, Architected, Implemented, Optimized, Led, Designed, Built, Engineered',
                    'impact': 'Using professional action verbs adds credibility and can improve score by 1 point'
                })
            
            # Check for skill keywords
            if recognized:
                projects_with_skills = sum(1 for p in projects if any(skill in str(p).lower() for skill in recognized[:10]))
                if projects_with_skills < len(projects) * 0.5:
                    top_skills = ', '.join(recognized[:5])
                    actionable_suggestions.append({
                        'category': 'Improve Keyword Alignment',
                        'priority': 'high',
                        'suggestion': 'Explicitly mention your technical skills in project descriptions',
                        'example': f'Include keywords like: {top_skills}',
                        'impact': 'Better keyword alignment could boost your score by 3-4 points'
                    })
        
        # Skills section tips
        skills_score = score_breakdown.get('skills', 0)
        if skills_score < 20:  # Out of 25
            if len(recognized) < 8:
                actionable_suggestions.append({
                    'category': 'Expand Skills Section',
                    'priority': 'medium',
                    'suggestion': f'Add {8 - len(recognized)} more relevant technical skills to reach optimal range',
                    'example': f'Consider adding: {", ".join(recommended_keywords[:5])}',
                    'impact': 'A well-rounded skills section (8-15 skills) maximizes this category score'
                })
        
        # Experience tips
        experience_score = score_breakdown.get('experience', 0)
        if experience_score < 15:  # Out of 20
            experience_items = resume_data.get('experience', [])
            if len(experience_items) < 2:
                actionable_suggestions.append({
                    'category': 'Add Experience',
                    'priority': 'high',
                    'suggestion': 'Include internships, part-time work, or relevant volunteer experience',
                    'example': 'Add: Internship roles, freelance projects, teaching assistant positions, or open-source contributions',
                    'impact': 'Additional experience entries significantly boost ATS credibility'
                })
        
        # Format/structure tips
        format_score = score_breakdown.get('format', 0)
        if format_score < 4:
            actionable_suggestions.append({
                'category': 'Improve Resume Structure',
                'priority': 'medium',
                'suggestion': 'Ensure all standard sections are present and well-organized',
                'example': 'Include: Contact Info, Education, Skills, Experience, Projects, Achievements (in this order)',
                'impact': 'Proper structure helps ATS parse your resume correctly'
            })
        
        # Achievement tips
        achievements = resume_data.get('achievements', [])
        if not achievements or len(achievements) == 0:
            actionable_suggestions.append({
                'category': 'Add Achievements',
                'priority': 'low',
                'suggestion': 'Include certifications, awards, hackathon wins, or academic honors',
                'example': 'Examples: "AWS Certified Developer", "Won 1st place in University Hackathon", "Dean\'s List 2023"',
                'impact': 'Achievements section adds 5 bonus points and differentiates your profile'
            })
        
        # Sort suggestions by priority
        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        actionable_suggestions.sort(key=lambda x: priority_order.get(x.get('priority', 'low'), 2))

        # Tailored keyword suggestions by coarse domain inference from present skills
        corrections['recommendedKeywords'] = recommended_keywords
        corrections['actionVerbs'] = action_verbs[:10]
        corrections['structureTips'] = structure_tips
        corrections['sampleBulletRewrites'] = sample_rewrites
        corrections['skillProjectGaps'] = skill_project_gaps  # NEW
        corrections['actionableSuggestions'] = actionable_suggestions[:8]  # NEW - Cap at 8 most important
        return corrections
    
    def _categorize_issues(self, issues: List[Dict], flagged_issues: Dict):
        """Categorize issues by severity level"""
        for issue in issues:
            severity = issue.get('severity', 'minor')
            flagged_issues[severity].append(issue)
    
    def _evaluate_contact_info(self, resume_data: Dict) -> Tuple[int, List[str], List[Dict]]:
        """Evaluate contact information completeness"""
        score = 0
        tips = []
        issues = []
        
        # Check for email
        email = str(resume_data.get('email') or '')
        if email:
            score += 5
            # Basic quality checks: common disposable domains or malformed
            domain_match = re.search(r"@([A-Za-z0-9.-]+)$", email)
            if not domain_match or len(email) < 6 or '..' in email:
                tips.append("💡 Verify your email format")
                issues.append({
                    'type': 'formatting_errors',
                    'category': 'Contact Information',
                    'issue': 'Suspicious email format',
                    'severity': 'minor',
                    'description': 'Ensure your email is correctly formatted and professional',
                    'fix': 'Use a professional email (e.g., firstname.lastname@domain.com)'
                })
        else:
            tips.append("❌ Add a professional email address")
            issues.append({
                'type': 'missing_section',
                'category': 'Contact Information',
                'issue': 'Missing email address',
                'severity': 'critical',
                'description': 'Email address is required for ATS systems to contact you',
                'fix': 'Add a professional email address in the contact section'
            })
        
        # Check for phone
        phone = str(resume_data.get('phone') or '')
        if phone:
            score += 5
            # Basic validation: at least 10 digits
            digits = re.sub(r"\D", "", phone)
            if len(digits) < 10:
                tips.append("💡 Provide a valid phone number with country/area code")
                issues.append({
                    'type': 'formatting_errors',
                    'category': 'Contact Information',
                    'issue': 'Phone number appears too short',
                    'severity': 'minor',
                    'description': 'Short phone numbers may prevent recruiters from contacting you',
                    'fix': 'Include full phone number with country/area code'
                })
        else:
            tips.append("❌ Include your phone number")
            issues.append({
                'type': 'missing_section',
                'category': 'Contact Information',
                'issue': 'Missing phone number',
                'severity': 'major',
                'description': 'Phone number helps recruiters contact you directly',
                'fix': 'Include your phone number in the contact section'
            })
        
        # Check for name
        if resume_data.get('name'):
            score += 5
        else:
            tips.append("❌ Ensure your full name is clearly visible")
            issues.append({
                'type': 'missing_section',
                'category': 'Contact Information',
                'issue': 'Missing full name',
                'severity': 'critical',
                'description': 'Full name is essential for resume identification',
                'fix': 'Add your full name prominently at the top of the resume'
            })
        
        return score, tips, issues
    
    def _evaluate_education(self, resume_data: Dict) -> Tuple[int, List[str], List[Dict]]:
        """Evaluate education section"""
        score = 0
        tips = []
        issues = []
        
        # Check for degree information
        degree = resume_data.get('degree') or resume_data.get('bachelorDegree') or resume_data.get('mastersDegree')
        if degree:
            score += 5
        else:
            tips.append("❌ Include your degree information")
            issues.append({
                'type': 'missing_section',
                'category': 'Education',
                'issue': 'Missing degree information',
                'severity': 'critical',
                'description': 'Degree information is essential for ATS systems to understand your qualifications',
                'fix': 'Add your degree (e.g., B.Tech, B.Sc, M.Tech) in the education section'
            })
        
        # Check for university
        if resume_data.get('university') or resume_data.get('bachelorUniversity') or resume_data.get('mastersUniversity'):
            score += 5
        else:
            tips.append("❌ Add your university/college name")
            issues.append({
                'type': 'missing_section',
                'category': 'Education',
                'issue': 'Missing university/college name',
                'severity': 'major',
                'description': 'University name helps establish credibility and educational background',
                'fix': 'Include your university or college name in the education section'
            })
        
        # Check for CGPA
        cg = resume_data.get('cgpa', 0) or resume_data.get('bachelorCGPA', 0) or resume_data.get('mastersCGPA', 0)
        try:
            cg_float = float(cg)
        except Exception:
            cg_float = 0.0
        if cg_float > 0:
            score += 5
        else:
            tips.append("❌ Include your CGPA/GPA if available")
            issues.append({
                'type': 'missing_section',
                'category': 'Education',
                'issue': 'Missing CGPA/GPA',
                'severity': 'minor',
                'description': 'Academic performance metrics help differentiate candidates',
                'fix': 'Include your CGPA or GPA if it is 7.0 or above'
            })

        # Academic quality penalties/bonuses
        if cg_float >= 8.5:
            score += 2
            tips.append("✅ Strong academics (CGPA ≥ 8.5)")
        elif cg_float < 6.0 and cg_float > 0:
            score -= 3
            tips.append("❌ Low academic performance; consider improving CGPA")
        
        return score, tips, issues
    
    def _evaluate_experience(self, resume_data: Dict) -> Tuple[int, List[str], List[Dict]]:
        """Evaluate work experience and internships"""
        score = 0
        tips = []
        issues = []
        
        # Check for internships
        internships = resume_data.get('internships', [])
        if internships:
            score += 10
            if len(internships) > 1:
                score += 5
                tips.append("✅ Great! Multiple internships show diverse experience")
            else:
                tips.append("✅ Good internship experience")
        else:
            tips.append("❌ Consider adding internship experience")
            issues.append({
                'type': 'missing_section',
                'category': 'Experience',
                'issue': 'No internship or work experience',
                'severity': 'major',
                'description': 'Work experience is crucial for most job applications',
                'fix': 'Add internships, part-time jobs, or relevant projects to show practical experience'
            })
        
        # Check for work experience keywords
        experience_text = ' '.join(internships).lower()
        experience_keywords_found = sum(1 for keyword in self.ats_keywords['experience_keywords'] 
                                      if keyword in experience_text)
        
        if experience_keywords_found >= 3:
            score += 5
            tips.append("✅ Good use of action verbs and experience keywords")
        elif experience_keywords_found > 0:
            score += 2
            tips.append("💡 Add more action verbs like 'developed', 'implemented', 'managed'")
            issues.append({
                'type': 'weak_keywords',
                'category': 'Experience',
                'issue': 'Limited action verbs in experience descriptions',
                'severity': 'minor',
                'description': 'Action verbs make your experience more impactful and ATS-friendly',
                'fix': 'Use strong action verbs like developed, implemented, managed, led, created, designed'
            })
        else:
            tips.append("❌ Use action verbs to describe your experience")
            issues.append({
                'type': 'weak_keywords',
                'category': 'Experience',
                'issue': 'Missing action verbs in experience descriptions',
                'severity': 'major',
                'description': 'Action verbs are essential for ATS systems to understand your contributions',
                'fix': 'Start each experience bullet point with a strong action verb'
            })
        
        return score, tips, issues
    
    def _evaluate_skills(self, resume_data: Dict) -> Tuple[int, List[str], List[Dict]]:
        """Evaluate technical and soft skills (max 25 points)"""
        score = 0
        tips = []
        issues = []
        
        skills = resume_data.get('skills', [])
        if not skills:
            tips.append("❌ Add a dedicated skills section")
            issues.append({
                'type': 'missing_section',
                'category': 'Skills',
                'issue': 'Missing skills section',
                'severity': 'critical',
                'description': 'Skills section is essential for ATS systems to match your qualifications',
                'fix': 'Add a dedicated skills section with relevant technical and soft skills'
            })
            return score, tips, issues
        
        # Count technical skills using allowlist matching with fuzzy fallback
        # Normalize skills and count those in allowed set or close matches
        allowed = self._build_allowed_skill_set()
        normalized_user_skills = []
        categories = {
            'programming': {'python','java','javascript','typescript','c','c++','c#','go','rust','kotlin','swift','php','ruby'},
            'data_ml': {'pandas','numpy','sklearn','scikit-learn','tensorflow','pytorch','nlp','opencv'},
            'web': {'react','angular','vue','node','express','django','flask','graphql','rest','api','html','css','sass','tailwind','bootstrap'},
            'devops_cloud': {'docker','kubernetes','aws','azure','gcp','linux','git'},
            'db': {'sql','mysql','postgres','mongodb','redis'},
        }
        category_hits = {k: 0 for k in categories}
        
        for s in skills:
            s_norm = self._normalize_skill_text(str(s))
            matched = False
            
            # Exact match first
            if s_norm in allowed:
                normalized_user_skills.append(s_norm)
                matched = True
            else:
                # Fuzzy match for close variations (e.g., "reactjs" -> "react", "postgresql" -> "postgres")
                close_matches = difflib.get_close_matches(s_norm, allowed, n=1, cutoff=0.85)
                if close_matches:
                    normalized_user_skills.append(close_matches[0])
                    matched = True
            
            # Category assignment (check both original and matched skill)
            if matched:
                check_skill = normalized_user_skills[-1] if normalized_user_skills else s_norm
                for cat, items in categories.items():
                    if check_skill in items:
                        category_hits[cat] += 1
        
        # Technical skills scoring (0-15 points based on quantity and quality)
        if len(normalized_user_skills) >= 12:
            score += 15
            tips.append("✅ Excellent variety of recognized technical skills")
        elif len(normalized_user_skills) >= 8:
            score += 13
            tips.append("✅ Strong set of recognized technical skills")
        elif len(normalized_user_skills) >= 5:
            score += 10
            tips.append("✅ Good recognized technical skills")
        elif len(normalized_user_skills) >= 3:
            score += 7
            tips.append("💡 Add more relevant, industry-recognized skills")
        elif len(normalized_user_skills) > 0:
            score += 4
            tips.append("💡 Add more relevant, industry-recognized skills")
            issues.append({
                'type': 'weak_keywords',
                'category': 'Skills',
                'issue': 'Limited technical skills',
                'severity': 'minor',
                'description': 'More recognized technical skills help match job requirements better',
                'fix': 'Add more role-relevant and verified skills (e.g., React, SQL, Python)'
            })
        else:
            tips.append("❌ Include relevant technical skills for your field")
            issues.append({
                'type': 'weak_keywords',
                'category': 'Skills',
                'issue': 'No technical skills found',
                'severity': 'major',
                'description': 'Technical skills are crucial for most technical roles',
                'fix': 'Add relevant technical skills like programming languages, tools, frameworks'
            })

        # Diversity bonus: more distinct categories → boost (0-5 points)
        distinct_categories = sum(1 for v in category_hits.values() if v > 0)
        if distinct_categories >= 5:
            score += 5
            tips.append("✅ Exceptional breadth across all skill categories")
        elif distinct_categories >= 4:
            score += 4
            tips.append("✅ Strong breadth across multiple skill categories")
        elif distinct_categories == 3:
            score += 3
            tips.append("✅ Good breadth across several skill categories")
        elif distinct_categories == 2:
            score += 2
        
        # Check for soft skills (0-5 points)
        soft_skills = []
        for skill in skills:
            if any(soft_skill in skill.lower() for soft_skill in self.ats_keywords['soft_skills']):
                soft_skills.append(skill)
        
        if len(soft_skills) >= 3:
            score += 5
            tips.append("✅ Excellent balance of technical and soft skills")
        elif len(soft_skills) >= 2:
            score += 4
            tips.append("✅ Good balance of technical and soft skills")
        elif len(soft_skills) > 0:
            score += 2
            tips.append("💡 Consider adding more soft skills")
            issues.append({
                'type': 'weak_keywords',
                'category': 'Skills',
                'issue': 'Limited soft skills',
                'severity': 'minor',
                'description': 'Soft skills are important for team collaboration and leadership roles',
                'fix': 'Add soft skills like leadership, communication, teamwork, problem-solving'
            })
        else:
            tips.append("💡 Include soft skills like leadership, communication, teamwork")
            issues.append({
                'type': 'weak_keywords',
                'category': 'Skills',
                'issue': 'No soft skills found',
                'severity': 'minor',
                'description': 'Soft skills demonstrate your interpersonal abilities',
                'fix': 'Include soft skills like leadership, communication, teamwork, adaptability'
            })
        
        return score, tips, issues
    
    def _evaluate_keywords(self, resume_data: Dict) -> Tuple[int, List[str], List[Dict]]:
        """Evaluate keyword optimization"""
        score = 0
        tips = []
        issues = []
        
        # Combine all text content
        all_text = []
        all_text.append(resume_data.get('name', ''))
        all_text.append(resume_data.get('degree', ''))
        all_text.append(resume_data.get('university', ''))
        all_text.extend(resume_data.get('skills', []))
        all_text.extend(resume_data.get('projects', []))
        all_text.extend(resume_data.get('internships', []))
        all_text.extend(resume_data.get('achievements', []))
        
        combined_text = ' '.join(all_text).lower()
        
        # Count relevant keywords strictly from allowlist
        allowed = self._build_allowed_skill_set()
        keyword_count = 0
        # Tokenize combined text and join common multi-words
        tokens = set()
        # Collect unigrams and frequent bigrams
        words = [w for w in re.split(r"[^a-z0-9+#.]+", combined_text) if w]
        for i, w in enumerate(words):
            tokens.add(w)
            if i + 1 < len(words):
                bigram = (w + ' ' + words[i + 1]).strip()
                tokens.add(bigram)
        # Normalize tokens via _normalize_skill_text and count intersection with allowed
        norm_tokens = {self._normalize_skill_text(t) for t in tokens}
        keyword_count = len(norm_tokens & allowed)
        
        # Calculate keyword density
        total_words = len(combined_text.split())
        keyword_density = keyword_count / max(total_words, 1)
        
        if keyword_count >= 20 or keyword_density >= 0.03:  # robust threshold with count floor
            score += 15
            tips.append("✅ Excellent keyword optimization")
        elif keyword_count >= 12 or keyword_density >= 0.02:  # 2% or higher
            score += 10
            tips.append("✅ Good keyword usage")
        elif keyword_count >= 6 or keyword_density >= 0.01:  # 1% or higher
            score += 5
            tips.append("💡 Add more industry-relevant keywords")
            issues.append({
                'type': 'weak_keywords',
                'category': 'Keywords',
                'issue': 'Low keyword density',
                'severity': 'minor',
                'description': 'Higher keyword density helps ATS systems match your resume to job postings',
                'fix': 'Include more industry-specific keywords from job descriptions'
            })
        else:
            tips.append("❌ Include more industry-specific keywords")
            issues.append({
                'type': 'weak_keywords',
                'category': 'Keywords',
                'issue': 'Very low keyword density',
                'severity': 'major',
                'description': 'ATS systems rely heavily on keywords to match candidates to jobs',
                'fix': 'Add relevant industry keywords, technical terms, and job-specific terminology'
            })
        
        return score, tips, issues
    
    def _evaluate_projects(self, resume_data: Dict) -> Tuple[int, List[str], List[Dict]]:
        """
        Evaluate project section with enhanced keyword matching and impact assessment.
        
        Scoring breakdown (15 points max):
        - Project count: 0-6 points
        - Keyword/skill alignment: 0-5 points
        - Quantifiable impact: 0-3 points
        - Action verbs: 0-1 point
        """
        score = 0
        tips = []
        issues = []
        
        projects = resume_data.get('projects', [])
        if not projects:
            tips.append("❌ Add a projects section to showcase your work")
            issues.append({
                'type': 'missing_section',
                'category': 'Projects',
                'issue': 'Missing projects section',
                'severity': 'critical',
                'description': 'Projects demonstrate practical skills and problem-solving abilities, essential for ATS scoring',
                'fix': 'Add a projects section with 2-3 relevant projects showing your technical skills and measurable impact'
            })
            return score, tips, issues
        
        # 1. PROJECT COUNT SCORING (0-6 points)
        project_count_score = 0
        if len(projects) >= 3:
            project_count_score = 6
            tips.append("✅ Excellent project portfolio with 3+ projects")
        elif len(projects) >= 2:
            project_count_score = 4
            tips.append("✅ Good project experience with 2 projects")
        elif len(projects) >= 1:
            project_count_score = 2
            tips.append("💡 Add 1-2 more projects to strengthen portfolio")
            issues.append({
                'type': 'missing_content',
                'category': 'Projects',
                'issue': 'Limited project portfolio',
                'severity': 'minor',
                'description': 'Having 3+ projects demonstrates diverse skills and sustained technical engagement',
                'fix': 'Add 1-2 more relevant projects with detailed descriptions and measurable outcomes'
            })
        
        score += project_count_score
        
        # 2. KEYWORD MATCHING & RELEVANCE (0-5 points) - THE BIGGEST FACTOR
        # Uses NLP-style matching for hard skills, technologies, and methodologies
        keyword_score = 0
        keyword_tips = []
        
        try:
            allowed = self._build_allowed_skill_set()
            user_skills_norm = []
            for s in resume_data.get('skills', []):
                s_norm = self._normalize_skill_text(str(s))
                if s_norm in allowed:
                    user_skills_norm.append(s_norm)
            
            # Enhanced action verbs list (professional jargon)
            action_verbs = {
                'developed', 'designed', 'implemented', 'architected', 'built', 'created',
                'led', 'managed', 'coordinated', 'spearheaded', 'directed', 'supervised',
                'analyzed', 'evaluated', 'assessed', 'investigated', 'researched',
                'optimized', 'improved', 'enhanced', 'streamlined', 'automated',
                'integrated', 'deployed', 'configured', 'maintained', 'migrated',
                'collaborated', 'facilitated', 'executed', 'delivered', 'achieved',
                'reduced', 'increased', 'accelerated', 'minimized', 'maximized'
            }
            
            # Track project quality metrics
            projects_with_skills = 0
            projects_with_action_verbs = 0
            projects_with_metrics = 0
            total_skill_matches = 0
            
            for proj in projects:
                text = str(proj).lower()
                words = [w for w in re.split(r"[^a-z0-9+#.]+", text) if w]
                tokens = set(words)
                
                # Create bigrams for multi-word skills (e.g., "machine learning")
                for i in range(len(words) - 1):
                    tokens.add((words[i] + ' ' + words[i + 1]).strip())
                
                norm_tokens = {self._normalize_skill_text(t) for t in tokens}
                
                # Check for hard skills/technologies match (exact term matching)
                allowed_hits = norm_tokens & allowed
                user_hits = norm_tokens & set(user_skills_norm)
                
                if user_hits:
                    projects_with_skills += 1
                    total_skill_matches += len(user_hits)
                
                # Check for action verbs (professional jargon)
                verb_hits = set(words) & action_verbs
                if verb_hits:
                    projects_with_action_verbs += 1
                
                # Check for quantifiable metrics (numbers indicating impact)
                # Patterns: percentages, numbers with units, time savings, scale metrics
                has_metrics = bool(re.search(
                    r'\d+%|'  # Percentages: 35%, 50%
                    r'\d+x|'  # Multipliers: 2x, 10x
                    r'\d+\s*(?:ms|seconds?|minutes?|hours?|days?|weeks?|months?|users?|requests?|records?|rows?|GB|MB|TB)|'  # Time/scale
                    r'(?:reduced|increased|improved|optimized|decreased|enhanced|accelerated|minimized|maximized)\s+.*?\s+by\s+\d+|'  # Action + by number
                    r'(?:from|to)\s+\d+',  # Ranges
                    text, re.IGNORECASE
                ))
                
                if has_metrics:
                    projects_with_metrics += 1
            
            num_projects = len(projects)
            
            # Calculate keyword alignment score (0-5 points)
            if num_projects > 0:
                skill_ratio = projects_with_skills / num_projects
                avg_matches = total_skill_matches / num_projects if num_projects > 0 else 0
                
                # Strong alignment: 80%+ projects have skills, avg 2+ skill matches per project
                if skill_ratio >= 0.8 and avg_matches >= 2:
                    keyword_score = 5
                    keyword_tips.append("✅ Excellent keyword alignment - projects strongly demonstrate your listed skills")
                # Good alignment: 60%+ projects, avg 1.5+ matches
                elif skill_ratio >= 0.6 and avg_matches >= 1.5:
                    keyword_score = 4
                    keyword_tips.append("✅ Good keyword matching - projects align well with your skills")
                # Moderate: 40%+ projects, avg 1+ match
                elif skill_ratio >= 0.4 and avg_matches >= 1:
                    keyword_score = 3
                    keyword_tips.append("💡 Moderate alignment - strengthen keyword usage in project descriptions")
                # Weak: Some matches but not consistent
                elif skill_ratio > 0 or avg_matches > 0:
                    keyword_score = 1
                    keyword_tips.append("⚠️ Weak keyword alignment - projects don't clearly reflect your skills")
                    issues.append({
                        'type': 'mismatch',
                        'category': 'Projects',
                        'issue': 'Poor skill-project alignment',
                        'severity': 'major',
                        'description': 'ATS uses NLP to match project keywords with your listed skills. Projects should explicitly mention the technologies you claim',
                        'fix': 'Revise project descriptions to include exact skill keywords (e.g., "Python", "React", "AWS") and technical methodologies'
                    })
                # Very weak or no matches
                else:
                    keyword_score = 0
                    keyword_tips.append("❌ No keyword alignment - projects must use your listed technical skills")
                    issues.append({
                        'type': 'mismatch',
                        'category': 'Projects',
                        'issue': 'No skill-project alignment',
                        'severity': 'critical',
                        'description': 'Projects fail to demonstrate any listed skills. ATS cannot validate your technical expertise',
                        'fix': 'Rewrite project descriptions using exact skill names from your skills section. Example: "Developed REST API using Python and Django"'
                    })
            
            score += keyword_score
            tips.extend(keyword_tips)
            
            # 3. QUANTIFIABLE IMPACT (0-3 points) - Demonstrating Value
            impact_score = 0
            if num_projects > 0:
                metric_ratio = projects_with_metrics / num_projects
                
                if metric_ratio >= 0.67:  # 2/3 or more projects have metrics
                    impact_score = 3
                    tips.append("✅ Excellent quantifiable impact - projects show measurable results with metrics")
                elif metric_ratio >= 0.5:  # Half have metrics
                    impact_score = 2
                    tips.append("✅ Good impact demonstration - some projects show quantifiable results")
                elif metric_ratio > 0:  # At least one has metrics
                    impact_score = 1
                    tips.append("💡 Add more quantifiable metrics to demonstrate project impact")
                    issues.append({
                        'type': 'missing_content',
                        'category': 'Projects',
                        'issue': 'Limited quantifiable impact',
                        'severity': 'minor',
                        'description': 'Recruiters and ATS look for measurable achievements. Use numbers, percentages, and scale metrics',
                        'fix': 'Add metrics like "reduced load time by 35%", "handled 10K+ daily users", or "improved efficiency by 2x"'
                    })
                else:
                    tips.append("⚠️ No quantifiable metrics - add numbers to demonstrate project value")
                    issues.append({
                        'type': 'missing_content',
                        'category': 'Projects',
                        'issue': 'No quantifiable impact',
                        'severity': 'major',
                        'description': 'Without metrics, ATS cannot assess the value of your contributions. Numbers validate achievement',
                        'fix': 'Add specific metrics: percentages (35% faster), scale (5000 users), time savings (reduced by 2 hours), or volume (processed 1M records)'
                    })
            
            score += impact_score
            
            # 4. ACTION VERBS (0-1 point) - Professional Jargon
            verb_score = 0
            if num_projects > 0:
                verb_ratio = projects_with_action_verbs / num_projects
                
                if verb_ratio >= 0.8:  # Most projects use action verbs
                    verb_score = 1
                    tips.append("✅ Strong use of action verbs - projects demonstrate active contributions")
                elif verb_ratio >= 0.5:
                    verb_score = 0
                    tips.append("💡 Good verb usage - consider using more action verbs (Developed, Architected, Optimized)")
                else:
                    tips.append("💡 Use strong action verbs to start project descriptions (Implemented, Designed, Led, Analyzed)")
                    issues.append({
                        'type': 'formatting_errors',
                        'category': 'Projects',
                        'issue': 'Weak action verbs',
                        'severity': 'minor',
                        'description': 'ATS recognizes professional jargon. Start descriptions with strong action verbs to validate experience',
                        'fix': 'Begin each project with verbs like: Developed, Architected, Implemented, Optimized, Led, Managed, Analyzed, Designed'
                    })
            
            score += verb_score
            
        except Exception as e:
            # If analysis fails, give base score
            print(f"Project analysis error: {e}")
            tips.append("⚠️ Could not fully analyze project relevance")
        
        # Additional tips based on project descriptions
        detailed_projects = [p for p in projects if len(str(p).split()) > 10]
        if len(detailed_projects) < len(projects):
            tips.append("💡 Expand project descriptions - include technologies, your role, methodology, and measurable outcomes")
            issues.append({
                'type': 'formatting_errors',
                'category': 'Projects',
                'issue': 'Insufficient project descriptions',
                'severity': 'minor',
                'description': 'Detailed descriptions (10+ words) help ATS extract relevant keywords and context',
                'fix': 'For each project, include: (1) technologies used, (2) action verbs, (3) your specific role, (4) quantifiable results'
            })
        
        return score, tips, issues
    
    def _evaluate_achievements(self, resume_data: Dict) -> Tuple[int, List[str], List[Dict]]:
        """Evaluate achievements and awards"""
        score = 0
        tips = []
        issues = []
        
        achievements = resume_data.get('achievements', [])
        if achievements:
            score += 5
            tips.append("✅ Great achievements section")
        else:
            tips.append("💡 Consider adding achievements, awards, or certifications")
            issues.append({
                'type': 'missing_section',
                'category': 'Achievements',
                'issue': 'Missing achievements section',
                'severity': 'minor',
                'description': 'Achievements help differentiate you from other candidates',
                'fix': 'Add awards, certifications, hackathon wins, or academic honors'
            })
        
        return score, tips, issues
    
    def _evaluate_format(self, resume_data: Dict) -> Tuple[int, List[str], List[Dict]]:
        """Evaluate resume format and structure"""
        score = 5  # Default score for having parsed data
        tips = []
        issues = []
        
        # Check if all major sections are present
        sections_present = 0
        if resume_data.get('name'): sections_present += 1
        if resume_data.get('email'): sections_present += 1
        if resume_data.get('degree'): sections_present += 1
        if resume_data.get('skills'): sections_present += 1
        if resume_data.get('projects'): sections_present += 1
        
        if sections_present >= 4:
            tips.append("✅ Well-structured resume with all major sections")
        else:
            tips.append("💡 Ensure all major sections are present and well-organized")
            issues.append({
                'type': 'formatting_errors',
                'category': 'Format & Structure',
                'issue': 'Incomplete resume structure',
                'severity': 'major',
                'description': 'ATS systems expect standard resume sections for proper parsing',
                'fix': 'Ensure all major sections (Contact, Education, Skills, Experience, Projects) are present'
            })

        # Penalize if skills list is extremely long without matching projects (suspected padding)
        skills = resume_data.get('skills', [])
        projects = resume_data.get('projects', [])
        if len(skills) >= 20 and len(projects) <= 1:
            score -= 2
            tips.append("💡 Skills list is very long; ensure depth with projects/experience")
        
        return score, tips, issues
    
    def _evaluate_spelling_grammar(self, resume_data: Dict) -> Tuple[int, List[str], List[Dict]]:
        """Evaluate spelling and grammar in resume content"""
        score = 10  # Start with full score, deduct for issues
        tips = []
        issues = []
        
        # Common spelling mistakes and their corrections
        common_spelling_mistakes = {
            'recieve': 'receive',
            'seperate': 'separate',
            'definately': 'definitely',
            'occured': 'occurred',
            'accomodate': 'accommodate',
            'acheive': 'achieve',
            'begining': 'beginning',
            'calender': 'calendar',
            'comming': 'coming',
            'differnt': 'different',
            'experiance': 'experience',
            'futher': 'further',
            'goverment': 'government',
            'independant': 'independent',
            'knowlege': 'knowledge',
            'managment': 'management',
            'neccessary': 'necessary',
            'occassion': 'occasion',
            'priviledge': 'privilege',
            'responsability': 'responsibility',
            'seperate': 'separate',
            'succesful': 'successful',
            'teh': 'the',
            'thier': 'their',
            'untill': 'until',
            'usefull': 'useful',
            'writting': 'writing',
            'acheived': 'achieved',
            'developement': 'development',
            'enviroment': 'environment',
            'excellant': 'excellent',
            'funtional': 'functional',
            'immediatly': 'immediately',
            'improvment': 'improvement',
            'inital': 'initial',
            'intrested': 'interested',
            'maintainance': 'maintenance',
            'oppurtunity': 'opportunity',
            'performence': 'performance',
            'persistant': 'persistent',
            'prefered': 'preferred',
            'proffesional': 'professional',
            'recomend': 'recommend',
            'relevent': 'relevant',
            'requirment': 'requirement',
            'resposible': 'responsible',
            'seperate': 'separate',
            'succesfully': 'successfully',
            'techincal': 'technical',
            'togather': 'together',
            'univeristy': 'university',
            'usefull': 'useful',
            'writen': 'written'
        }
        
        # Common grammar issues patterns - ONLY definite errors
        # Removed homophone patterns (there/their, to/too, your/youre) as they cause too many false positives
        grammar_patterns = [
            # Article repetition (definite error)
            (r'\b(a|an|the)\s+\1\b', 'article repetition'),
            # Verb repetition (definite error)
            (r'\b(is|are|was|were|be|been)\s+\1\b', 'verb repetition'),
            # Conjunction repetition (definite error)
            (r'\b(and|or|but)\s+\1\b', 'conjunction repetition'),
            # Missing apostrophes in contractions (definite error)
            (r'\b(dont|wont|cant|shouldnt|wouldnt|couldnt|havent|hasnt|hadnt|isnt|arent|wasnt|werent|didnt|doesnt)\b', 'missing apostrophe')
        ]
        
        # Extended list of technical terms to exclude from grammar checking
        technical_exclusions = {
            'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm',
            'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z',
            'c++', 'c#', 'f#', 'go', 'js', 'ts', 'py', 'rb',
            'btech', 'b.tech', 'mtech', 'm.tech', 'bsc', 'b.sc', 'msc', 'm.sc',
            'bca', 'mca', 'ba', 'ma', 'be', 'me', 'bba', 'mba', 'phd',
            'aws', 'gcp', 'azure', 'api', 'rest', 'graphql',
            'html', 'css', 'sql', 'nosql', 'xml', 'json',
            'ai', 'ml', 'dl', 'nlp', 'cv', 'ui', 'ux',
            'git', 'npm', 'cli', 'sdk', 'ide', 'ci', 'cd',
            'tcp', 'udp', 'http', 'https', 'ssh', 'ftp', 'dns', 'vpn',
            'os', 'cpu', 'gpu', 'ram', 'ssd', 'iot', 'ar', 'vr'
        }
        
        # Collect all text content for analysis
        all_text_content = []
        text_sources = {
            'name': resume_data.get('name', ''),
            'degree': resume_data.get('degree', ''),
            'university': resume_data.get('university', ''),
            'skills': ' '.join(resume_data.get('skills', [])),
            'projects': ' '.join([str(p) for p in resume_data.get('projects', [])]),
            'internships': ' '.join([str(i) for i in resume_data.get('internships', [])]),
            'achievements': ' '.join([str(a) for a in resume_data.get('achievements', [])])
        }
        
        spelling_errors = []
        grammar_errors = []
        
        # Check spelling (skip technical terms)
        for source, text in text_sources.items():
            if not text:
                continue
                
            words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
            for word in words:
                # Skip technical terms
                if word.lower() in technical_exclusions:
                    continue
                if word in common_spelling_mistakes:
                    spelling_errors.append({
                        'word': word,
                        'correction': common_spelling_mistakes[word],
                        'source': source,
                        'context': text
                    })
        
        # Check grammar patterns (skip matches that are technical terms)
        for source, text in text_sources.items():
            if not text:
                continue
                
            for pattern, issue_type in grammar_patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    matched_text = match.group().strip().lower()
                    # Skip if it's a technical term
                    if matched_text in technical_exclusions:
                        continue
                    grammar_errors.append({
                        'text': match.group(),
                        'issue': issue_type,
                        'source': source,
                        'context': text,
                        'position': match.start()
                    })
        
        # Deduct points based on errors found
        total_errors = len(spelling_errors) + len(grammar_errors)
        
        if total_errors == 0:
            tips.append("✅ No spelling or grammar errors detected")
        elif total_errors <= 2:
            score -= 2
            tips.append("💡 Minor spelling/grammar issues found")
            issues.append({
                'type': 'formatting_errors',
                'category': 'Spelling & Grammar',
                'issue': f'{total_errors} minor spelling/grammar issues',
                'severity': 'minor',
                'description': 'Minor spelling or grammar errors can impact professional impression',
                'fix': 'Review and correct the identified spelling and grammar issues'
            })
        elif total_errors <= 5:
            score -= 5
            tips.append("⚠️ Several spelling/grammar issues found")
            issues.append({
                'type': 'formatting_errors',
                'category': 'Spelling & Grammar',
                'issue': f'{total_errors} spelling/grammar issues',
                'severity': 'major',
                'description': 'Multiple spelling and grammar errors can significantly impact ATS compatibility',
                'fix': 'Carefully proofread and correct all spelling and grammar errors'
            })
        else:
            score -= 10
            tips.append("❌ Many spelling/grammar issues found")
            issues.append({
                'type': 'formatting_errors',
                'category': 'Spelling & Grammar',
                'issue': f'{total_errors} spelling/grammar issues',
                'severity': 'critical',
                'description': 'Numerous spelling and grammar errors severely impact resume quality and ATS compatibility',
                'fix': 'Use spell-check tools and proofread thoroughly to fix all errors'
            })
        
        # Add specific error details to issues
        if spelling_errors:
            error_details = []
            for error in spelling_errors[:5]:  # Show first 5 errors
                error_details.append(f"'{error['word']}' should be '{error['correction']}'")
            
            if len(spelling_errors) > 5:
                error_details.append(f"... and {len(spelling_errors) - 5} more")
            
            issues.append({
                'type': 'formatting_errors',
                'category': 'Spelling & Grammar',
                'issue': 'Spelling errors detected',
                'severity': 'major' if len(spelling_errors) > 3 else 'minor',
                'description': f'Found {len(spelling_errors)} spelling errors: {", ".join(error_details)}',
                'fix': 'Use spell-check and proofread carefully to correct all spelling errors'
            })
        
        if grammar_errors:
            error_details = []
            for error in grammar_errors[:3]:  # Show first 3 errors
                error_details.append(f"'{error['text']}' ({error['issue']})")
            
            if len(grammar_errors) > 3:
                error_details.append(f"... and {len(grammar_errors) - 3} more")
            
            issues.append({
                'type': 'formatting_errors',
                'category': 'Spelling & Grammar',
                'issue': 'Grammar issues detected',
                'severity': 'major' if len(grammar_errors) > 2 else 'minor',
                'description': f'Found {len(grammar_errors)} grammar issues: {", ".join(error_details)}',
                'fix': 'Review grammar rules and proofread to correct all grammar issues'
            })
        
        return score, tips, issues
    
    def _evaluate_spelling_grammar_enhanced(self, resume_data: Dict) -> Tuple[int, List[str], List[Dict], Dict]:
        """Enhanced spelling and grammar evaluation using comprehensive checker"""
        score = 5  # Start with full score (updated to 5 points max)
        tips = []
        issues = []
        
        # Use the comprehensive grammar checker (with safe fallback)
        try:
            grammar_result = check_resume_grammar_spelling(resume_data)
        except Exception as e:
            # Fallback to safe empty result if grammar checker fails
            grammar_result = {
                'total_errors': 0,
                'spelling_errors': [],
                'grammar_errors': [],
                'professional_errors': []
            }
            tips.append("⚠️ Grammar check unavailable, basic validation only")
        
        # Calculate score based on errors found
        total_errors = grammar_result['total_errors']
        spelling_errors = len(grammar_result['spelling_errors'])
        grammar_errors = len(grammar_result['grammar_errors'])
        professional_errors = len(grammar_result['professional_errors'])
        
        # Deduct points based on error severity (adjusted for 5-point scale)
        if total_errors == 0:
            tips.append("✅ No spelling or grammar errors detected")
        elif total_errors <= 2:
            score -= 1  # Minor deduction for 1-2 errors
            tips.append("💡 Minor spelling/grammar issues found")
            issues.append({
                'type': 'formatting_errors',
                'category': 'Spelling & Grammar',
                'issue': f'{total_errors} minor spelling/grammar issues',
                'severity': 'minor',
                'description': 'Minor spelling or grammar errors can impact professional impression',
                'fix': 'Review and correct the identified spelling and grammar issues',
                'details': grammar_result
            })
        elif total_errors <= 5:
            score -= 3  # Moderate deduction for 3-5 errors
            tips.append("⚠️ Several spelling/grammar issues found")
            issues.append({
                'type': 'formatting_errors',
                'category': 'Spelling & Grammar',
                'issue': f'{total_errors} spelling/grammar issues',
                'severity': 'major',
                'description': 'Multiple spelling and grammar errors can significantly impact ATS compatibility',
                'fix': 'Carefully proofread and correct all spelling and grammar errors',
                'details': grammar_result
            })
        else:
            score -= 5  # Full deduction for 6+ errors
            tips.append("❌ Many spelling/grammar issues found")
            issues.append({
                'type': 'formatting_errors',
                'category': 'Spelling & Grammar',
                'issue': f'{total_errors} spelling/grammar issues',
                'severity': 'critical',
                'description': 'Numerous spelling and grammar errors severely impact resume quality and ATS compatibility',
                'fix': 'Use spell-check tools and proofread thoroughly to fix all errors',
                'details': grammar_result
            })
        
        # Add specific error details
        if spelling_errors > 0:
            error_details = []
            for error in grammar_result['spelling_errors'][:5]:  # Show first 5 errors
                error_details.append(f"'{error['word']}' should be '{error['correction']}'")
            
            if len(grammar_result['spelling_errors']) > 5:
                error_details.append(f"... and {len(grammar_result['spelling_errors']) - 5} more")
            
            issues.append({
                'type': 'formatting_errors',
                'category': 'Spelling & Grammar',
                'issue': 'Spelling errors detected',
                'severity': 'major' if spelling_errors > 3 else 'minor',
                'description': f'Found {spelling_errors} spelling errors: {", ".join(error_details)}',
                'fix': 'Use spell-check and proofread carefully to correct all spelling errors',
                'details': grammar_result['spelling_errors']
            })
        
        if grammar_errors > 0:
            error_details = []
            for error in grammar_result['grammar_errors'][:3]:  # Show first 3 errors
                error_details.append(f"'{error['text']}' ({error['issue']})")
            
            if len(grammar_result['grammar_errors']) > 3:
                error_details.append(f"... and {len(grammar_result['grammar_errors']) - 3} more")
            
            issues.append({
                'type': 'formatting_errors',
                'category': 'Spelling & Grammar',
                'issue': 'Grammar issues detected',
                'severity': 'major' if grammar_errors > 2 else 'minor',
                'description': f'Found {grammar_errors} grammar issues: {", ".join(error_details)}',
                'fix': 'Review grammar rules and proofread to correct all grammar issues',
                'details': grammar_result['grammar_errors']
            })
        
        if professional_errors > 0:
            error_details = []
            for error in grammar_result['professional_errors'][:3]:  # Show first 3 errors
                error_details.append(f"'{error['term']}' should be '{error['correction']}'")
            
            if len(grammar_result['professional_errors']) > 3:
                error_details.append(f"... and {len(grammar_result['professional_errors']) - 3} more")
            
            issues.append({
                'type': 'formatting_errors',
                'category': 'Spelling & Grammar',
                'issue': 'Professional terminology issues detected',
                'severity': 'minor',
                'description': f'Found {professional_errors} professional terminology issues: {", ".join(error_details)}',
                'fix': 'Use proper professional terminology and formatting',
                'details': grammar_result['professional_errors']
            })
        
        return score, tips, issues, grammar_result
    
    def _identify_strengths(self, score_breakdown: Dict) -> List[str]:
        """Identify resume strengths"""
        strengths = []
        for category, score in score_breakdown.items():
            if score >= 10:
                strengths.append(f"Strong {category.replace('_', ' ')} section")
        return strengths
    
    def _identify_improvements(self, score_breakdown: Dict) -> List[str]:
        """Identify areas for improvement"""
        improvements = []
        for category, score in score_breakdown.items():
            if score < 5:
                improvements.append(f"Improve {category.replace('_', ' ')} section")
        return improvements


def calculate_ats_score(resume_data: Dict) -> Dict:
    """
    Main function to calculate ATS score
    """
    calculator = ATSCalculator()
    return calculator.calculate_ats_score(resume_data)


if __name__ == "__main__":
    # Test with sample data
    sample_resume = {
        "name": "John Doe",
        "email": "john.doe@example.com",
        "phone": "+1234567890",
        "university": "Tech University",
        "degree": "B.Tech Computer Science",
        "cgpa": 8.5,
        "tenthPercentage": 85.0,
        "twelfthPercentage": 78.0,
        "skills": ["Python", "JavaScript", "React", "SQL", "AWS", "Leadership", "Communication"],
        "projects": ["E-commerce Website", "Mobile App", "Data Analysis Tool"],
        "internships": ["Software Developer Intern at TechCorp", "Data Science Intern at DataCorp"],
        "achievements": ["Hackathon Winner", "Dean's List", "Best Project Award"]
    }
    
    result = calculate_ats_score(sample_resume)
    print(json.dumps(result, indent=2))
