import pickle
import os
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Tuple
import logging
from domain_keywords import get_keywords_for_selection, get_advanced_keywords, get_all_keywords
import json
try:
    # Prefer fuzzywuzzy if available (existing code expects this API)
    from fuzzywuzzy import fuzz  # type: ignore
except Exception:
    try:
        # rapidfuzz has a compatible API for ratio scoring
        from rapidfuzz import fuzz  # type: ignore
    except Exception:
        # Fallback: lightweight implementation using difflib (returns 0-100 int)
        import difflib

        class _SimpleFuzz:
            @staticmethod
            def ratio(a, b):
                try:
                    if a is None or b is None:
                        return 0
                    a_s = str(a)
                    b_s = str(b)
                    return int(round(difflib.SequenceMatcher(None, a_s, b_s).ratio() * 100))
                except Exception:
                    return 0

        fuzz = _SimpleFuzz()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# SCORING CONFIGURATION
# ============================================================================
"""
Placement Score Calculation Weights (Total: 100%)

The final placement score is calculated using a weighted combination of
multiple components. Each component is normalized to 0-100 scale before
applying the weight.

Component Breakdown:
- Academic Performance (20%): CGPA, 10th & 12th grades
- Technical Skills (32%): Form-selected + resume-parsed skills
- Projects (25%): Quality, complexity, and impact (10% + 10% + 5% for top 3)
- DSA & Problem Solving (10%): Competitive programming skills
- Experience (8%): Internships, hackathons, and work experience
- Achievements & Certifications (10%): Awards, certifications, and accomplishments

The ML model score is calculated separately and used for informational purposes,
not directly weighted into the final score.
"""

SCORING_WEIGHTS = {
    'academics': 0.20,                      # 20% - Academic performance
    'skills': 0.32,                         # 32% - Technical & domain skills
    'projects': 0.25,                       # 25% - Project quality & complexity (10% + 10% + 5% for 3 projects)
    'dsa': 0.10,                            # 10% - DSA & Problem Solving
    'experience': 0.08,                     # 8% - Internships, hackathons, work experience
    'achievements_certifications': 0.10     # 10% - Certifications, awards, achievements
}

# Score normalization ranges
SCORE_RANGES = {
    'academics': (0, 100),          # CGPA * 10, 10th%, 12th% averaged
    'skills': (0, 100),             # Skill match percentage
    'projects': (0, 100),           # Project quality score
    'dsa': (0, 100),                # DSA & Problem Solving score
    'experience': (0, 10),          # Raw experience score (converted to 0-100 for calculation)
    'certifications': (0, 100),     # Certification score
    'achievements': (0, 100)        # Achievement score
}

# Eligibility threshold
PLACEMENT_ELIGIBILITY_THRESHOLD = 50  # Minimum score for placement eligibility

# ============================================================================
# FUZZY MATCHING CONFIGURATION
# ============================================================================

# Fuzzy matching threshold (0-100, higher = stricter matching)
FUZZY_MATCH_THRESHOLD = 80  # 80% similarity required for fuzzy match

# Comprehensive skill synonyms and variations
SKILL_SYNONYMS = {
    # Programming Languages
    'javascript': ['js', 'ecmascript', 'es6', 'es2015', 'node.js', 'nodejs'],
    'typescript': ['ts'],
    'python': ['py', 'python3', 'python2'],
    'java': ['jdk', 'jre'],
    'csharp': ['c#', '.net', 'dotnet'],
    'cplusplus': ['c++', 'cpp'],
    'c': ['clang'],
    'ruby': ['rb'],
    'php': ['php7', 'php8'],
    'swift': ['swiftui'],
    'kotlin': ['kt'],
    'go': ['golang'],
    'rust': ['rs'],
    'scala': ['sc'],
    'r': ['rstudio'],
    
    # Frontend Frameworks
    'react': ['reactjs', 'react.js', 'react native', 'react-native'],
    'angular': ['angularjs', 'angular.js', 'angular2', 'ng'],
    'vue': ['vuejs', 'vue.js', 'vue3'],
    'svelte': ['sveltejs', 'svelte.js'],
    'next': ['nextjs', 'next.js'],
    'nuxt': ['nuxtjs', 'nuxt.js'],
    'gatsby': ['gatsbyjs'],
    'jquery': ['jq'],
    
    # Backend Frameworks
    'express': ['expressjs', 'express.js'],
    'django': ['djangorestframework', 'drf'],
    'flask': ['flask-restful'],
    'fastapi': ['fast api'],
    'spring': ['spring boot', 'springboot', 'spring framework'],
    'laravel': ['lumen'],
    'rails': ['ruby on rails', 'ror'],
    'asp.net': ['aspnet', 'asp'],
    'nest': ['nestjs', 'nest.js'],
    
    # Databases
    'mongodb': ['mongo', 'mongodb atlas', 'nosql'],
    'postgresql': ['postgres', 'psql'],
    'mysql': ['mariadb'],
    'redis': ['redis cache'],
    'cassandra': ['apache cassandra'],
    'dynamodb': ['dynamo db', 'dynamo'],
    'elasticsearch': ['elastic', 'elk'],
    'firebase': ['firestore', 'firebase realtime database'],
    'sqlite': ['sqlite3'],
    'oracle': ['oracle db'],
    'mssql': ['sql server', 'microsoft sql server'],
    
    # Cloud & DevOps
    'aws': ['amazon web services', 'ec2', 's3', 'lambda', 'cloudformation'],
    'azure': ['microsoft azure', 'azure cloud'],
    'gcp': ['google cloud', 'google cloud platform'],
    'docker': ['containerization', 'containers'],
    'kubernetes': ['k8s', 'k8'],
    'jenkins': ['ci/cd'],
    'terraform': ['tf', 'iac', 'infrastructure as code'],
    'ansible': ['automation'],
    'gitlab': ['gitlab ci', 'gitlab-ci'],
    'github': ['github actions'],
    'circleci': ['circle ci'],
    
    # AI/ML
    'machinelearning': ['ml', 'machine learning'],
    'artificialintelligence': ['ai', 'artificial intelligence'],
    'deeplearning': ['dl', 'deep learning'],
    'tensorflow': ['tf'],
    'pytorch': ['torch'],
    'keras': ['keras api'],
    'scikitlearn': ['sklearn', 'scikit-learn', 'scikit learn'],
    'opencv': ['cv2', 'computer vision'],
    'nlp': ['natural language processing', 'naturallanguageprocessing'],
    'pandas': ['pd'],
    'numpy': ['np'],
    'matplotlib': ['pyplot'],
    
    # Mobile Development
    'android': ['android studio', 'kotlin android'],
    'ios': ['swift ios', 'objective-c'],
    'flutter': ['dart flutter'],
    'reactnative': ['react native', 'react-native', 'rn'],
    'ionic': ['ionicframework'],
    
    # Version Control
    'git': ['github', 'gitlab', 'bitbucket', 'version control'],
    'svn': ['subversion'],
    
    # Testing
    'jest': ['jestjs'],
    'mocha': ['mochajs'],
    'pytest': ['py.test'],
    'junit': ['junit5', 'junit4'],
    'selenium': ['webdriver'],
    'cypress': ['cypressio'],
    
    # Others
    'graphql': ['gql'],
    'rest': ['restful', 'rest api', 'restful api'],
    'grpc': ['grpc api'],
    'websocket': ['ws', 'websockets'],
    'microservices': ['micro services'],
    'agile': ['scrum', 'kanban'],
    'problemsolving': ['problem solving', 'problem-solving'],
    'communication': ['verbal communication', 'written communication'],
    'teamwork': ['collaboration', 'team player'],
    'leadership': ['team lead', 'leading'],
}

# Reverse mapping for quick lookup (synonym -> canonical form)
SYNONYM_TO_CANONICAL = {}
for canonical, synonyms in SKILL_SYNONYMS.items():
    SYNONYM_TO_CANONICAL[canonical] = canonical
    for synonym in synonyms:
        SYNONYM_TO_CANONICAL[synonym.lower()] = canonical

# ============================================================================

class MLPlacementPredictor:
    def __init__(self, model_path='placement_model.pkl', scaler_path='scaler.pkl'):
        """Initialize the ML-based placement predictor"""
        self.model_path = model_path
        self.scaler_path = scaler_path
        self.model = None
        self.scaler = None
        self.feature_columns = ['10th_%', '12th_%', 'Aggregate_%']
        self.is_loaded = False
        
        # Try to load the model and scaler
        self.load_model()
    
    def load_model(self):
        """Load the trained ML model and scaler with validation"""
        try:
            # Check if both files exist
            if not os.path.exists(self.model_path):
                logger.warning(f"Model file not found at: {self.model_path}")
                logger.info("Please ensure placement_model.pkl exists in the backend directory")
                return False
            
            if not os.path.exists(self.scaler_path):
                logger.warning(f"Scaler file not found at: {self.scaler_path}")
                logger.info("Please ensure scaler.pkl exists in the backend directory")
                return False
            
            # Load the model
            with open(self.model_path, 'rb') as f:
                self.model = pickle.load(f)
            
            # Load the scaler
            with open(self.scaler_path, 'rb') as f:
                self.scaler = pickle.load(f)
            
            # Validate model integrity
            if not self._validate_model_integrity():
                logger.error("Model validation failed - model may be corrupted")
                self.is_loaded = False
                return False
            
            self.is_loaded = True
            logger.info("✅ ML model and scaler loaded and validated successfully!")
            logger.info(f"Model type: {type(self.model).__name__}")
            logger.info(f"Features: {self.feature_columns}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error loading model: {str(e)}")
            self.is_loaded = False
            return False
    
    def _validate_model_integrity(self):
        """Validate that the model can make predictions correctly"""
        try:
            # Test with sample academic data
            test_samples = [
                {'10th %': 75.0, '12th %': 80.0, 'Aggregate % till now in Graduation/Diploma': 85.0},
                {'10th %': 60.0, '12th %': 65.0, 'Aggregate % till now in Graduation/Diploma': 70.0},
                {'10th %': 90.0, '12th %': 92.0, 'Aggregate % till now in Graduation/Diploma': 95.0}
            ]
            
            for sample in test_samples:
                test_df = pd.DataFrame([sample])
                test_scaled = self.scaler.transform(test_df)
                
                # Check if model has predict_proba method
                if hasattr(self.model, 'predict_proba'):
                    prediction = self.model.predict_proba(test_scaled)[0]
                    # Validate probability is in valid range [0, 1]
                    if not (0 <= prediction[1] <= 1):
                        logger.error(f"Invalid prediction probability: {prediction[1]}")
                        return False
                else:
                    # Fallback to predict if no predict_proba
                    prediction = self.model.predict(test_scaled)[0]
                    if prediction < 0:
                        logger.error(f"Invalid prediction value: {prediction}")
                        return False
            
            logger.info("✅ Model integrity validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Model validation error: {str(e)}")
            return False
    
    def _get_domain_keywords(self, selected_id):
        """Get domain/category-specific keywords for targeted skill matching"""
        try:
            # Get keywords specific to the selected domain or category
            domain_keywords = get_keywords_for_selection(selected_id)
            
            logger.info(f"Using {len(domain_keywords)} keywords for selection: {selected_id}")
            
            # Return domain-specific keywords for more targeted matching
            return domain_keywords
            
        except Exception as e:
            logger.error(f"Error getting domain keywords for {selected_id}: {str(e)}")
            # Fallback to advanced keywords
            return get_advanced_keywords()
    
    def predict(self, student_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Predict placement probability using the trained ML model
        
        Args:
            student_data: Dictionary containing student information with keys:
                - tenthPercentage: 10th standard percentage (0-100)
                - twelfthPercentage: 12th standard percentage (0-100)
                - collegeCGPA: Graduation CGPA (0-10)
            
        Returns:
            Dictionary with ML prediction results
        """
        try:
            if not self.is_loaded:
                logger.error("ML model not loaded. Cannot make predictions.")
                return self._fallback_prediction(student_data)
            
            # Extract and validate required features
            tenth_percent = float(student_data.get('tenthPercentage', 0))
            twelfth_percent = float(student_data.get('twelfthPercentage', 0))
            cgpa = float(student_data.get('collegeCGPA', 0))
            
            # Validate input ranges
            if not (0 <= tenth_percent <= 100):
                logger.warning(f"Invalid 10th percentage: {tenth_percent}. Using 0.")
                tenth_percent = 0
            
            if not (0 <= twelfth_percent <= 100):
                logger.warning(f"Invalid 12th percentage: {twelfth_percent}. Using 0.")
                twelfth_percent = 0
            
            if not (0 <= cgpa <= 10):
                logger.warning(f"Invalid CGPA: {cgpa}. Using 0.")
                cgpa = 0
            
            # Convert CGPA to percentage (assuming 10-point scale)
            cgpa_percent = cgpa * 10
            
            # Extract unselected skills (skills to develop)
            unselected_skills = student_data.get('unselectedSkills', [])
            
            # Create input data matching the training format
            # The model expects: ['10th %', '12th %', 'Aggregate % till now in Graduation/Diploma']
            input_data = {
                '10th %': tenth_percent,
                '12th %': twelfth_percent,
                'Aggregate % till now in Graduation/Diploma': cgpa_percent
            }
            
            # Create DataFrame with the exact column names expected by the model
            input_df = pd.DataFrame([input_data])
            
            # Scale the features using the loaded scaler
            input_scaled = self.scaler.transform(input_df)
            
            # Make prediction using the stacking classifier
            if hasattr(self.model, 'predict_proba'):
                # Get probability of positive class (placed)
                prediction_proba = self.model.predict_proba(input_scaled)[0]
                # The model predicts probability of placement (0-1), convert to percentage (0-100)
                predicted_score = prediction_proba[1] * 100
            else:
                # Fallback to direct prediction if no predict_proba method
                prediction = self.model.predict(input_scaled)[0]
                predicted_score = prediction * 100 if prediction <= 1 else prediction
            
            # Ensure score is between 0-100
            predicted_score = max(0, min(100, predicted_score))
            
            # Round to 2 decimal places and convert to native Python type
            predicted_score = float(round(predicted_score, 2))
            
            # Extended profile-based components
            domain = student_data.get('selectedDomainId', '')
            print(f"🔍 DEBUG - Backend received domain ID: '{domain}'")
            print(f"🔍 DEBUG - Selected Role ID: '{student_data.get('selectedRoleId', 'N/A')}'")
            form_skills = student_data.get('selectedSkills', [])
            resume_skills = student_data.get('skills', [])  # Skills extracted from resume parser
            projects = student_data.get('projects', []) or []
            certifications = student_data.get('certifications', '')
            achievements_text = student_data.get('achievements', '') or ''
            available_role_skills = student_data.get('availableRoleSkills', None)  # Total skills available for selected role

            # Calculate sub-scores using domain/category-specific keywords
            # Combine form skills and resume skills for comprehensive scoring
            skill_score, deduplicated_skills, skill_match_details = self._calculate_skill_score(
                domain, form_skills, resume_skills, available_role_skills
            )
            exp_score = self._calculate_experience_score(student_data)
            project_score, project_depth, strong_projects = self._calculate_project_score(projects, domain)
            certification_score = self._calculate_certification_score(certifications)
            achievement_score, extracted_achievements = self._calculate_achievement_score(achievements_text)
            dsa_score = self._calculate_dsa_score(student_data)

            # Composite blended score (academics + ML + profile)
            composite, category_breakdown = self._blend_scores(
                ml_score=predicted_score,
                academic_percent=cgpa_percent,
                skill_score=skill_score,
                experience_score=exp_score,
                project_score=project_score,
                certification_score=certification_score,
                achievement_score=achievement_score,
                dsa_score=dsa_score
            )

            # Generate recommendations using blended context
            # Use deduplicated skills for recommendations
            recommendations = self._generate_recommendations(composite, {
                '10th_%': tenth_percent,
                '12th_%': twelfth_percent,
                'Aggregate_%': cgpa_percent
            }, deduplicated_skills, domain)

            result = {
                'placementScore': float(round(composite, 2)),
                'mlModelScore': predicted_score,
                'mlPrediction': f"{predicted_score}%",
                'predictionConfidence': float(self._get_confidence_score(predicted_score)),
                'academicScore': float(round(cgpa_percent, 2)),
                'skillScore': float(round(skill_score, 2)),
                'experienceScore': float(round(exp_score, 2)),
                'projectScore': float(round(project_score, 2)),
                'certificationScore': float(round(certification_score, 2)),
                'achievementScore': float(round(achievement_score, 2)),
                'dsaScore': float(round(dsa_score, 2)),
                'projectDepth': project_depth,
                'strongProjects': strong_projects,
                'extractedAchievements': extracted_achievements,
                'recommendations': recommendations,
                'isEligible': bool(composite >= PLACEMENT_ELIGIBILITY_THRESHOLD),
                'eligibilityThreshold': PLACEMENT_ELIGIBILITY_THRESHOLD,
                'modelUsed': 'ML Model (Stacking Classifier + Profile Composite)',
                'features': {
                    '10th_%': float(tenth_percent),
                    '12th_%': float(twelfth_percent),
                    'Aggregate_%': float(cgpa_percent)
                },
                'inputData': {
                    'tenthPercentage': float(tenth_percent),
                    'twelfthPercentage': float(twelfth_percent),
                    'collegeCGPA': float(cgpa),
                    'selectedSkills': form_skills,
                    'skills': resume_skills,
                    'unselectedSkills': unselected_skills,
                    'numFormSkills': len(form_skills),
                    'numResumeSkills': len(resume_skills),
                    'numTotalSkills': len(deduplicated_skills),
                    'numProjects': len(projects),
                    'dsaEasy': student_data.get('dsaEasy', 0),
                    'dsaMedium': student_data.get('dsaMedium', 0),
                    'dsaHard': student_data.get('dsaHard', 0)
                },
                'scoreBreakdown': category_breakdown
            }
            
            logger.info(f"ML prediction completed. Score: {predicted_score}%")
            return result
            
        except Exception as e:
            logger.error(f"Error in ML prediction: {str(e)}")
            logger.info("Falling back to rule-based prediction")
            return self._fallback_prediction(student_data)
    
    def _get_confidence_score(self, predicted_score):
        """Calculate confidence score based on predicted score"""
        try:
            # Higher confidence for extreme scores, lower for middle scores
            if predicted_score >= 80 or predicted_score <= 20:
                return 95.0
            elif predicted_score >= 60 or predicted_score <= 40:
                return 85.0
            else:
                return 75.0
        except:
            return 75.0
    
    def _calculate_skill_score(self, domain, form_skills, resume_skills, available_role_skills=None, projects=None, certifications=None):
        """
        Enhanced skill scoring with depth assessment and quality validation
        Maximum: 100 points
        
        Components:
        - Base Coverage (0-50): How many relevant skills you have
        - Skill Diversity (0-20): Skills across multiple categories
        - Skill Depth (0-20): Quality indicators (projects 10, certs 10)
        - Form Verification (0-10): Form skills backed by resume/projects
        
        Features:
        - Stricter fuzzy matching (85% threshold)
        - Skill categorization (Programming, Web, Data/ML, DevOps, Soft)
        - Evidence-based verification
        - No artificial bonus caps
        - SPECIAL: If all available role skills are selected, score = 100%
        
        Args:
            domain: The selected domain
            form_skills: Skills selected from the form
            resume_skills: Skills extracted from resume
            available_role_skills: Total number of skills available for the selected role
            projects: List of project objects (optional)
            certifications: Certifications string (optional)
        
        Returns:
            tuple: (skill_score, deduplicated_skills, match_details)
        """
        try:
            # ================================================================
            # SPECIAL CASE: All available role skills selected = 100% score
            # ================================================================
            if available_role_skills and len(form_skills) >= available_role_skills:
                logger.info("🎯 ALL AVAILABLE ROLE SKILLS SELECTED!")
                logger.info(f"  Available skills for role: {available_role_skills}")
                logger.info(f"  Form skills selected: {len(form_skills)}")
                logger.info(f"  ✅ GUARANTEED 100% SKILL SCORE")
                return 100.0, form_skills, []
            
            # Use domain-specific keywords from domainData.js
            relevant_keywords = self._get_domain_keywords(domain)
            
            # Fallback to basic skills if no keywords available
            if not relevant_keywords:
                relevant_keywords = ['python', 'java', 'sql', 'communication', 'problem solving']
            
            # Normalize keywords to lowercase for matching
            relevant_keywords_lower = [kw.lower().strip() for kw in relevant_keywords]
            
            # ================================================================
            # STEP 1: DEDUPLICATE, NORMALIZE AND CATEGORIZE SKILLS
            # ================================================================
            all_skills = []
            seen_skills_canonical = set()  # Track canonical forms
            skill_sources = []  # Track if skill is from form or resume
            skill_categories = set()  # Track skill categories for diversity
            
            # Process form skills first (higher priority)
            for skill in form_skills:
                skill_clean = skill.strip()
                if not skill_clean:
                    continue
                
                # Get canonical form (handle synonyms)
                canonical = self._get_canonical_skill(skill_clean)
                
                if canonical not in seen_skills_canonical:
                    all_skills.append(skill_clean)
                    seen_skills_canonical.add(canonical)
                    skill_sources.append('form')
                    skill_categories.add(self._get_skill_category(skill_clean))
            
            # Process resume skills (if not already present)
            for skill in resume_skills:
                skill_clean = skill.strip()
                if not skill_clean:
                    continue
                
                # Get canonical form
                canonical = self._get_canonical_skill(skill_clean)
                
                if canonical not in seen_skills_canonical:
                    all_skills.append(skill_clean)
                    seen_skills_canonical.add(canonical)
                    skill_sources.append('resume')
                    skill_categories.add(self._get_skill_category(skill_clean))
            
            # ================================================================
            # STEP 2: MATCH SKILLS WITH STRICTER FUZZY LOGIC
            # ================================================================
            matching_skills = 0
            matched_skill_details = []
            form_verified = 0  # Form skills verified by resume/projects
            
            for i, skill in enumerate(all_skills):
                skill_lower = skill.lower().strip()
                is_form_skill = skill_sources[i] == 'form'
                
                # Try to find a match using stricter matching (85% threshold)
                match_result = self._find_skill_match_strict(skill_lower, relevant_keywords_lower)
                
                if match_result['matched']:
                    matching_skills += 1
                    
                    # Check if form skill is verified by resume or projects
                    verified = False
                    if is_form_skill:
                        verified = self._verify_skill_in_content(skill_lower, resume_skills, projects)
                        if verified:
                            form_verified += 1
                    else:
                        verified = True  # Resume skills are already verified
                    
                    matched_skill_details.append({
                        'skill': skill,
                        'source': skill_sources[i],
                        'verified': verified,
                        'match_type': match_result['match_type'],
                        'matched_keyword': match_result['matched_keyword'],
                        'confidence': match_result['confidence']
                    })
            
            # ================================================================
            # STEP 3: CALCULATE MULTI-COMPONENT SCORE
            # ================================================================
            if len(all_skills) == 0:
                return 0.0, [], []
            
            # A) BASE COVERAGE (0-50 points): Percentage of relevant skills matched
            coverage_ratio = matching_skills / len(all_skills)
            base_coverage = coverage_ratio * 50
            
            # B) SKILL DIVERSITY (0-20 points): Skills across different categories
            # Categories: Programming, Web, Data/ML, DevOps, Soft Skills
            num_categories = len(skill_categories)
            diversity_score = min(20, (num_categories / 5) * 20)
            
            # C) SKILL DEPTH (0-20 points): Quality indicators
            depth_score = 0
            
            # Projects demonstrating skills (0-10 points)
            if projects and len(projects) > 0:
                project_skill_count = self._count_skills_in_projects(all_skills, projects)
                project_depth = min(10, (project_skill_count / len(all_skills)) * 10)
                depth_score += project_depth
            
            # Certifications validating skills (0-10 points)
            if certifications:
                cert_skill_count = self._count_skills_in_certifications(all_skills, certifications)
                cert_depth = min(10, (cert_skill_count / len(all_skills)) * 10)
                depth_score += cert_depth
            
            # D) FORM VERIFICATION (0-10 points): Form skills backed by evidence
            verification_score = 0
            if len(form_skills) > 0:
                verification_ratio = form_verified / len(form_skills)
                verification_score = verification_ratio * 10
            
            # Calculate final score (sum of all components)
            skill_score = base_coverage + diversity_score + depth_score + verification_score
            
            # Ensure score is within valid range
            skill_score = min(100, max(0, skill_score))
            
            # ================================================================
            # STEP 4: LOGGING FOR DEBUGGING
            # ================================================================
            logger.info(f"🎯 Enhanced Skill Scoring for domain '{domain}':")
            logger.info(f"  📋 Form skills: {len(form_skills)} (verified: {form_verified})")
            logger.info(f"  📄 Resume skills: {len(resume_skills)}")
            logger.info(f"  ✅ Total unique skills: {len(all_skills)} (matched: {matching_skills})")
            logger.info(f"  📊 Base Coverage (0-50): {base_coverage:.2f}")
            logger.info(f"  🎨 Diversity (0-20): {diversity_score:.2f} ({num_categories}/5 categories)")
            logger.info(f"  📚 Depth (0-20): {depth_score:.2f}")
            logger.info(f"  ✅ Form Verification (0-10): {verification_score:.2f}")
            logger.info(f"  🏆 Final Skill Score: {skill_score:.2f}%")
            
            # Log match details for top matches
            if matched_skill_details:
                logger.info(f"  🔍 Top matches:")
                for detail in matched_skill_details[:5]:
                    logger.info(f"    • {detail['skill']} → {detail['matched_keyword']} "
                              f"({detail['match_type']}, {detail['confidence']}% confidence)")
            
            return skill_score, all_skills, matched_skill_details
            
        except Exception as e:
            logger.error(f"❌ Error in skill score calculation: {str(e)}")
            import traceback
            traceback.print_exc()
            return 0.0, [], []
    
    def _get_canonical_skill(self, skill: str) -> str:
        """
        Get canonical form of a skill (handles synonyms)
        
        Args:
            skill: The skill to normalize
            
        Returns:
            str: Canonical form of the skill
        """
        skill_lower = skill.lower().strip()
        
        # Remove common punctuation and normalize
        skill_normalized = skill_lower.replace('.', '').replace('-', '').replace('_', '').replace(' ', '')
        
        # Check if it's a known synonym
        if skill_normalized in SYNONYM_TO_CANONICAL:
            return SYNONYM_TO_CANONICAL[skill_normalized]
        
        # Also check original (with spaces)
        if skill_lower in SYNONYM_TO_CANONICAL:
            return SYNONYM_TO_CANONICAL[skill_lower]
        
        # Return normalized form if not found
        return skill_normalized
    
    def _get_skill_category(self, skill: str) -> str:
        """Categorize skill into one of 5 main categories"""
        skill_lower = skill.lower()
        
        # Category 1: Programming Languages
        programming = ['python', 'java', 'javascript', 'c++', 'c#', 'go', 'rust', 'kotlin', 'swift', 'typescript', 'ruby', 'php', 'scala']
        if any(lang in skill_lower for lang in programming):
            return 'programming'
        
        # Category 2: Web Development
        web = ['react', 'angular', 'vue', 'node', 'express', 'django', 'flask', 'spring', 'html', 'css', 'bootstrap', 'tailwind', 'nextjs', 'svelte']
        if any(tech in skill_lower for tech in web):
            return 'web'
        
        # Category 3: Data Science & ML
        data_ml = ['tensorflow', 'pytorch', 'pandas', 'numpy', 'scikit', 'ml', 'ai', 'data', 'analytics', 'tableau', 'power bi', 'spark', 'hadoop']
        if any(tech in skill_lower for tech in data_ml):
            return 'data'
        
        # Category 4: DevOps & Cloud
        devops = ['docker', 'kubernetes', 'aws', 'azure', 'gcp', 'jenkins', 'ci/cd', 'git', 'terraform', 'ansible', 'linux', 'nginx']
        if any(tech in skill_lower for tech in devops):
            return 'devops'
        
        # Category 5: Soft Skills
        soft = ['communication', 'leadership', 'teamwork', 'problem solving', 'agile', 'scrum', 'management', 'presentation']
        if any(skill in skill_lower for skill in soft):
            return 'soft'
        
        return 'other'
    
    def _verify_skill_in_content(self, skill: str, resume_skills: list, projects: list) -> bool:
        """Verify if a form skill is mentioned in resume or projects"""
        skill_lower = skill.lower()
        
        # Check resume skills
        if resume_skills:
            for rs in resume_skills:
                if skill_lower in str(rs).lower():
                    return True
        
        # Check project descriptions and technologies
        if projects:
            for project in projects:
                if isinstance(project, dict):
                    desc = str(project.get('description', '')).lower()
                    tech = str(project.get('technologies', '')).lower()
                    title = str(project.get('title', '')).lower()
                    
                    if skill_lower in desc or skill_lower in tech or skill_lower in title:
                        return True
        
        return False
    
    def _count_skills_in_projects(self, skills: list, projects: list) -> int:
        """Count how many skills are demonstrated in projects"""
        if not projects:
            return 0
        
        count = 0
        for skill in skills:
            skill_lower = skill.lower()
            for project in projects:
                if isinstance(project, dict):
                    desc = str(project.get('description', '')).lower()
                    tech = str(project.get('technologies', '')).lower()
                    title = str(project.get('title', '')).lower()
                    
                    if skill_lower in desc or skill_lower in tech or skill_lower in title:
                        count += 1
                        break  # Count each skill only once
        
        return count
    
    def _count_skills_in_certifications(self, skills: list, certifications: str) -> int:
        """Count how many skills are mentioned in certifications"""
        if not certifications:
            return 0
        
        cert_lower = str(certifications).lower()
        count = 0
        
        for skill in skills:
            if skill.lower() in cert_lower:
                count += 1
        
        return count
    
    def _find_skill_match_strict(self, skill_lower: str, relevant_keywords_lower: List[str]) -> Dict[str, Any]:
        """
        Find a match for a skill using stricter fuzzy logic (85% threshold)
        
        Matching Strategies (in order of priority):
        1. Exact match (100% confidence)
        2. Synonym match (95% confidence)
        3. Substring match with validation (90% confidence)
        4. Fuzzy match >= 85% (confidence = match score)
        
        Args:
            skill_lower: Lowercase skill to match
            relevant_keywords_lower: List of lowercase domain keywords
            
        Returns:
            dict: Match result with matched status, type, keyword, and confidence
        """
        from difflib import SequenceMatcher
        
        skill_normalized = skill_lower.replace('.', '').replace('-', '').replace('_', '').replace(' ', '')
        
        for keyword in relevant_keywords_lower:
            keyword_normalized = keyword.replace('.', '').replace('-', '').replace('_', '').replace(' ', '')
            
            # Strategy 1: Exact match
            if skill_lower == keyword or skill_normalized == keyword_normalized:
                return {
                    'matched': True,
                    'match_type': 'exact',
                    'matched_keyword': keyword,
                    'confidence': 100
                }
            
            # Strategy 2: Synonym match
            skill_canonical = self._get_canonical_skill(skill_lower)
            keyword_canonical = self._get_canonical_skill(keyword)
            
            if skill_canonical == keyword_canonical:
                return {
                    'matched': True,
                    'match_type': 'synonym',
                    'matched_keyword': keyword,
                    'confidence': 95
                }
            
            # Strategy 3: Substring match - with validation to prevent false positives
            # Only match if keyword is substantial (>=4 chars) and skill length is reasonable
            if len(keyword_normalized) >= 4 and keyword_normalized in skill_normalized:
                if len(skill_normalized) <= len(keyword_normalized) * 1.5:
                    return {
                        'matched': True,
                        'match_type': 'substring',
                        'matched_keyword': keyword,
                        'confidence': 90
                    }
            
            if len(skill_normalized) >= 4 and skill_normalized in keyword_normalized:
                if len(keyword_normalized) <= len(skill_normalized) * 1.5:
                    return {
                        'matched': True,
                        'match_type': 'substring',
                        'matched_keyword': keyword,
                        'confidence': 90
                    }
        
        # Strategy 4: Fuzzy match with STRICTER threshold (85% instead of 80%)
        best_ratio = 0
        best_keyword = None
        
        for keyword in relevant_keywords_lower:
            ratio = SequenceMatcher(None, skill_lower, keyword).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_keyword = keyword
        
        if best_ratio >= 0.85:  # Stricter threshold
            return {
                'matched': True,
                'match_type': 'fuzzy',
                'matched_keyword': best_keyword,
                'confidence': int(best_ratio * 100)
            }
        
        # No match found
        return {
            'matched': False,
            'match_type': 'none',
            'matched_keyword': None,
            'confidence': 0
        }
    
    def _find_skill_match(self, skill_lower: str, relevant_keywords_lower: List[str]) -> Dict[str, Any]:
        """
        Find a match for a skill using multiple strategies with fuzzy logic
        
        Matching Strategies (in order of priority):
        1. Exact match (100% confidence)
        2. Synonym match (95% confidence)
        3. Substring match (90% confidence)
        4. Fuzzy match >= 80% (fuzzy score as confidence)
        
        Args:
            skill_lower: Lowercase skill to match
            relevant_keywords_lower: List of lowercase domain keywords
            
        Returns:
            dict: Match result with matched status, type, keyword, and confidence
        """
        skill_normalized = skill_lower.replace('.', '').replace('-', '').replace('_', '').replace(' ', '')
        
        for keyword in relevant_keywords_lower:
            keyword_normalized = keyword.replace('.', '').replace('-', '').replace('_', '').replace(' ', '')
            
            # ============================================================
            # STRATEGY 1: EXACT MATCH
            # ============================================================
            if skill_lower == keyword or skill_normalized == keyword_normalized:
                return {
                    'matched': True,
                    'match_type': 'exact',
                    'matched_keyword': keyword,
                    'confidence': 100
                }
            
            # ============================================================
            # STRATEGY 2: SYNONYM MATCH
            # ============================================================
            skill_canonical = self._get_canonical_skill(skill_lower)
            keyword_canonical = self._get_canonical_skill(keyword)
            
            if skill_canonical == keyword_canonical:
                return {
                    'matched': True,
                    'match_type': 'synonym',
                    'matched_keyword': keyword,
                    'confidence': 95
                }
            
            # ============================================================
            # STRATEGY 3: SUBSTRING MATCH
            # ============================================================
            # Skill contains keyword
            if keyword_normalized in skill_normalized and len(keyword_normalized) >= 2:
                return {
                    'matched': True,
                    'match_type': 'substring',
                    'matched_keyword': keyword,
                    'confidence': 90
                }
            
            # Keyword contains skill
            if skill_normalized in keyword_normalized and len(skill_normalized) >= 2:
                return {
                    'matched': True,
                    'match_type': 'substring',
                    'matched_keyword': keyword,
                    'confidence': 90
                }
        
        # ============================================================
        # STRATEGY 4: FUZZY MATCH (using fuzzywuzzy)
        # ============================================================
        best_fuzzy_score = 0
        best_fuzzy_keyword = None
        
        for keyword in relevant_keywords_lower:
            # Use token_sort_ratio for better handling of word order differences
            fuzzy_score = fuzz.token_sort_ratio(skill_lower, keyword)
            
            if fuzzy_score > best_fuzzy_score:
                best_fuzzy_score = fuzzy_score
                best_fuzzy_keyword = keyword
        
        # Accept fuzzy matches >= threshold
        if best_fuzzy_score >= FUZZY_MATCH_THRESHOLD:
            return {
                'matched': True,
                'match_type': 'fuzzy',
                'matched_keyword': best_fuzzy_keyword,
                'confidence': best_fuzzy_score
            }
        
        # ============================================================
        # NO MATCH FOUND
        # ============================================================
        return {
            'matched': False,
            'match_type': 'none',
            'matched_keyword': None,
            'confidence': 0
        }
    
    def _calculate_experience_score(self, student_data):
        """
        Calculate experience score based on ACTUAL practical experience
        Maximum 10 points
        
        Focus: Internships (0-7) + Hackathons (0-5) = Max 10 points
        Note: Projects are NOT counted here (they have separate 0-100 scoring to prevent double-counting)
        
        Internship Scoring (Max 7 points):
        - Industrial/Company Internships: 6 points each (max 7 total)
          - 2+ industrial = 7 points (capped)
          - 1 industrial = 6 points
        - Virtual/Training Internships: 1 point each
        - Combined score capped at 7 points maximum
        
        Hackathon Scoring:
        - Participation: 0.5 points each (max 2 points for 4+ hackathons)
        - Winner Bonus: +3 points (winning major hackathons is significant)
        - Max total from hackathons: 5 points
        """
        try:
            score = 0
            
            # 1. INTERNSHIPS - Most Important for Placement (Max 7 points)
            if student_data.get('internshipsCompleted', False):
                industrial_internships = int(student_data.get('industrialInternships', 0))
                virtual_internships = int(student_data.get('virtualInternships', 0))
                
                # Industrial/Company internships: 6 points each, max 7
                industrial_score = min(industrial_internships * 6, 7)
                
                # Virtual/Training internships: 1 point each
                virtual_score = virtual_internships * 1
                
                # Combine and cap at 7 points total
                internship_score = min(industrial_score + virtual_score, 7)
                score += internship_score
                
                logger.info(f"✅ Internships Breakdown:")
                logger.info(f"   Industrial: {industrial_internships} × 6 = {industrial_score} points")
                logger.info(f"   Virtual: {virtual_internships} × 1 = {virtual_score} points")
                logger.info(f"   Total Internship Score: {internship_score}/7 points")
            else:
                logger.info("⚠️ No internships completed = 0 points")
            
            # 2. HACKATHONS - Competitive Programming Experience (Max 5 points)
            if student_data.get('hackathonsParticipated', False):
                num_hackathons = int(student_data.get('numHackathons', 0))
                
                # Base participation points (0.5 per hackathon, max 2)
                participation_points = min(num_hackathons * 0.5, 2)
                
                # Winner bonus - winning hackathons is a BIG differentiator
                winner_bonus = 0
                if student_data.get('hackathonWinner', '').lower() == 'yes':
                    winner_bonus = 3  # Significant bonus for winning
                    logger.info(f"🏆 Hackathon Winner! +{winner_bonus} bonus points")
                
                hackathon_total = min(participation_points + winner_bonus, 5)
                score += hackathon_total
                logger.info(f"✅ Hackathons: {num_hackathons} participated, winner={winner_bonus > 0} = {hackathon_total} points")
            else:
                logger.info("⚠️ No hackathon participation = 0 points")
            
            # Projects are NOT counted here - they have separate comprehensive scoring (0-100)
            # This prevents double-counting and keeps experience focused on actual work/competition
            
            final_score = min(score, 10)  # Cap at 10 points maximum
            logger.info(f"📊 Final Experience Score: {final_score}/10")
            
            return final_score
            
        except Exception as e:
            logger.error(f"Error calculating experience score: {str(e)}")
            return 3  # Lower default - most students have limited industry experience

    def _calculate_project_score(self, projects, selected_id=None):
        """
        Enhanced project scoring with weighted contribution for top 3 projects.
        
        Scoring Strategy:
        - Project 1 (First listed): 10% weight (40% of total 25% projects score)
        - Project 2 (Second listed): 10% weight (40% of total 25% projects score)
        - Project 3 (Third listed): 5% weight (20% of total 25% projects score)
        - Uses user's project order from resume (not sorted by score)
        - Each project evaluated on 0-100 scale
        - Final score = (P1 × 0.40) + (P2 × 0.40) + (P3 × 0.20)
        
        Returns:
            Tuple of (weighted_project_score, depth_level, strong_projects)
        """
        try:
            if not projects:
                logger.info("No projects provided - returning 0 score")
                return 0.0, 'none', []
            
            # Evaluate ALL projects (up to 5 for performance)
            projects_to_evaluate = projects[:5]
            logger.info(f"Evaluating {len(projects_to_evaluate)} projects in user's listed order...")
            
            all_project_scores = []
            strong_projects = []
            
            for idx, p in enumerate(projects_to_evaluate):
                # Get detailed evaluation for this project
                project_evaluation = self._evaluate_single_project_enhanced(p)
                score = project_evaluation['score']
                
                # Store project with its score (maintaining original order)
                project_info = {
                    'title': p.get('title') or f'Project {idx + 1}',
                    'score': score,
                    'details': project_evaluation['details'],
                    'quality_tier': project_evaluation['quality_tier'],
                    'original_index': idx  # Track original position
                }
                all_project_scores.append(project_info)
                
                # Track strong projects (score >= 60 out of 100)
                if score >= 60:
                    strong_projects.append(project_info['title'])
                    logger.info(f"✨ Strong project found: '{project_info['title']}' (Score: {score})")
                elif score >= 40:
                    logger.info(f"📝 Good project: '{project_info['title']}' (Score: {score})")
                else:
                    logger.info(f"📌 Basic project: '{project_info['title']}' (Score: {score})")
            
            # DO NOT SORT - Use user's original order
            # Calculate weighted score based on first 3 projects in user's order
            # Project 1 (First): 40% weight, Project 2 (Second): 40% weight, Project 3 (Third): 20% weight
            project1_score = all_project_scores[0]['score'] if len(all_project_scores) >= 1 else 0
            project2_score = all_project_scores[1]['score'] if len(all_project_scores) >= 2 else 0
            project3_score = all_project_scores[2]['score'] if len(all_project_scores) >= 3 else 0
            
            # Weighted final score (out of 100)
            weighted_score = (project1_score * 0.40) + (project2_score * 0.40) + (project3_score * 0.20)
            
            # Determine depth level based on weighted score
            if weighted_score >= 80:
                depth_level = 'expert'
            elif weighted_score >= 60:
                depth_level = 'advanced'
            elif weighted_score >= 40:
                depth_level = 'intermediate' 
            elif weighted_score >= 20:
                depth_level = 'basic'
            else:
                depth_level = 'minimal'
            
            # Log detailed scoring summary
            logger.info("=" * 60)
            logger.info("PROJECT SCORING SUMMARY (WEIGHTED BY USER ORDER)")
            logger.info("=" * 60)
            logger.info(f"Total projects evaluated: {len(all_project_scores)}")
            logger.info(f"📊 Weighted Scoring Breakdown (User's Order):")
            logger.info(f"   Project 1 (First): {project1_score}/100 × 40% = {project1_score * 0.40:.2f}")
            logger.info(f"   Project 2 (Second): {project2_score}/100 × 40% = {project2_score * 0.40:.2f}")
            logger.info(f"   Project 3 (Third): {project3_score}/100 × 20% = {project3_score * 0.20:.2f}")
            logger.info(f"   Final Weighted Score: {weighted_score:.2f}/100")
            logger.info(f"   Depth Level: {depth_level}")
            logger.info(f"Strong projects (60+): {len(strong_projects)}")
            
            # Show all project scores for transparency
            for idx, proj in enumerate(all_project_scores, 1):
                weight_label = ""
                if idx == 1:
                    weight_label = " (40% weight)"
                elif idx == 2:
                    weight_label = " (40% weight)"
                elif idx == 3:
                    weight_label = " (20% weight)"
                logger.info(f"  {idx}. {proj['title']}: {proj['score']}/100 ({proj['quality_tier']}){weight_label}")
            logger.info("=" * 60)
            
            # Return weighted score
            return weighted_score, depth_level, strong_projects
            
        except Exception as e:
            logger.error(f"Error scoring projects: {str(e)}")
            return 30.0, 'basic', []  # Reasonable fallback

    def _evaluate_single_project_enhanced(self, project):
        """
        Comprehensive evaluation of a single project with detailed scoring.
        
        Scoring Criteria (0-100 scale):
        - Base Score: 10 points (for having a project)
        - Title Quality: 0-15 points
        - Description Detail: 0-20 points
        - Technology Stack: 0-30 points
        - Implementation Complexity: 0-15 points
        - Practical Value: 0-10 points
        
        Returns:
            Dict with score, details, and quality tier
        """
        title = project.get('title', '').strip()
        description = project.get('description', '').strip()
        
        if not title and not description:
            return {
                'score': 5, 
                'details': ['No project content provided'],
                'quality_tier': 'empty'
            }
        
        score = 0
        details = []
        
        # 1. Base score for having a project (10 points)
        base_score = 10
        score += base_score
        details.append(f"✓ Base score: {base_score}")
        
        # 2. Title quality (0-15 points)
        title_score = self._evaluate_title(title)
        score += title_score
        details.append(f"✓ Title quality: {title_score}/15")
        
        # 3. Description length and detail (0-20 points) 
        desc_score = self._evaluate_description(description)
        score += desc_score
        details.append(f"✓ Description detail: {desc_score}/20")
        
        # 4. Technology stack depth (0-30 points) - INCREASED from 25
        tech_score = self._evaluate_technology_stack(title + " " + description)
        score += tech_score
        details.append(f"✓ Technology depth: {tech_score}/30")
        
        # 5. Implementation complexity (0-15 points)
        complexity_score = self._evaluate_complexity(description)
        score += complexity_score
        details.append(f"✓ Complexity: {complexity_score}/15")
        
        # 6. Real-world applicability (0-10 points)
        practical_score = self._evaluate_practical_value(title, description)
        score += practical_score
        details.append(f"✓ Practical value: {practical_score}/10")
        
        # Ensure score is capped at 100
        final_score = min(score, 100)
        
        # Determine quality tier
        if final_score >= 80:
            quality_tier = 'exceptional'
        elif final_score >= 60:
            quality_tier = 'strong'
        elif final_score >= 40:
            quality_tier = 'good'
        elif final_score >= 20:
            quality_tier = 'basic'
        else:
            quality_tier = 'weak'
        
        return {
            'score': final_score,
            'details': details,
            'quality_tier': quality_tier
        }
    
    def _evaluate_title(self, title):
        """Evaluate project title quality (5-15 points)"""
        if not title:
            return 5
        
        score = 5  # Base for having a title
        
        # Bonus for descriptive titles
        if len(title.split()) >= 3:
            score += 3
        
        # Bonus for domain-specific terms
        domain_terms = [
            'system', 'platform', 'application', 'tool', 'framework',
            'dashboard', 'portal', 'analyzer', 'predictor', 'classifier',
            'detector', 'generator', 'optimizer', 'manager', 'tracker'
        ]
        if any(term in title.lower() for term in domain_terms):
            score += 4
        
        # Bonus for technology mentions in title
        tech_terms = [
            'web', 'mobile', 'ai', 'ml', 'data', 'cloud', 'iot',
            'blockchain', 'android', 'react', 'python', 'java'
        ]
        if any(term in title.lower() for term in tech_terms):
            score += 3
        
        return min(score, 15)
    
    def _evaluate_description(self, description):
        """Evaluate description quality and detail (5-20 points)"""
        if not description:
            return 5
        
        score = 5  # Base for having description
        
        # Length-based scoring
        length = len(description)
        if length > 200:
            score += 8
        elif length > 100:
            score += 5
        elif length > 50:
            score += 3
        
        # Detail indicators
        detail_keywords = [
            'implemented', 'developed', 'built', 'created', 'designed',
            'integrated', 'deployed', 'optimized', 'features', 'functionality',
            'database', 'api', 'interface', 'algorithm', 'architecture'
        ]
        detail_count = sum(1 for kw in detail_keywords if kw in description.lower())
        score += min(detail_count * 1, 7)  # Up to 7 points for implementation details
        
        return min(score, 20)
    
    def _evaluate_technology_stack(self, text):
        """
        Evaluate technology stack diversity and depth (0-30 points)
        
        Scoring:
        - Base: 5 points
        - Category diversity: 2 points per category (up to 14 points for 7 categories)
        - Technology count: 1 point per tech (up to 11 points)
        
        Total: 5 + 14 + 11 = 30 points max
        """
        text_lower = text.lower()
        score = 5  # Base score
        
        # Technology categories with comprehensive tech lists
        tech_categories = {
            'frontend': ['react', 'vue', 'angular', 'html', 'css', 'javascript', 'typescript', 
                        'jquery', 'bootstrap', 'tailwind', 'sass', 'webpack', 'next.js', 'nuxt'],
            'backend': ['node.js', 'express', 'django', 'flask', 'spring', 'asp.net', 'php', 
                       'ruby', 'rails', 'fastapi', 'laravel', 'nest.js', 'koa'],
            'database': ['mysql', 'postgresql', 'mongodb', 'sqlite', 'redis', 'oracle', 
                        'nosql', 'cassandra', 'dynamodb', 'mariadb', 'firebase'],
            'cloud': ['aws', 'azure', 'gcp', 'docker', 'kubernetes', 'heroku', 'netlify',
                     'vercel', 'digitalocean', 'cloud', 'serverless', 'lambda'],
            'mobile': ['android', 'ios', 'react native', 'flutter', 'kotlin', 'swift',
                      'xamarin', 'ionic', 'cordova', 'mobile'],
            'ai_ml': ['python', 'tensorflow', 'pytorch', 'scikit-learn', 'pandas', 'numpy', 
                     'opencv', 'keras', 'machine learning', 'deep learning', 'nlp', 'cv'],
            'tools': ['git', 'jenkins', 'ci/cd', 'testing', 'apis', 'rest', 'graphql',
                     'postman', 'swagger', 'junit', 'jest', 'pytest', 'selenium']
        }
        
        categories_found = 0
        total_techs = 0
        found_techs = []
        
        for category, techs in tech_categories.items():
            found_in_category = 0
            for tech in techs:
                if tech in text_lower:
                    found_in_category += 1
                    total_techs += 1
                    found_techs.append(tech)
            
            if found_in_category > 0:
                categories_found += 1
        
        # Score based on diversity and depth
        category_points = categories_found * 2  # 2 points per category (max 14)
        tech_points = min(total_techs, 11)      # 1 point per tech, max 11
        
        score += category_points
        score += tech_points
        
        logger.debug(f"Tech Stack: {categories_found} categories, {total_techs} technologies = {score}/30")
        
        return min(score, 30)
    
    def _evaluate_complexity(self, description):
        """Evaluate implementation complexity (0-15 points)"""
        if not description:
            return 0
        
        score = 0
        text_lower = description.lower()
        
        # Complexity indicators
        complexity_terms = [
            'authentication', 'authorization', 'security', 'encryption',
            'real-time', 'websocket', 'microservice', 'distributed',
            'scalable', 'performance', 'optimization', 'load balancing',
            'caching', 'monitoring', 'logging', 'testing', 'deployment',
            'ci/cd', 'pipeline', 'architecture', 'design pattern'
        ]
        
        complexity_count = sum(1 for term in complexity_terms if term in text_lower)
        score += min(complexity_count * 2, 12)  # Up to 12 points for complexity
        
        # Bonus for advanced implementation details
        advanced_terms = ['algorithm', 'data structure', 'optimization', 'pattern']
        if any(term in text_lower for term in advanced_terms):
            score += 3
        
        return min(score, 15)
    
    def _evaluate_practical_value(self, title, description):
        """Evaluate real-world applicability (0-10 points)"""
        text = (title + " " + description).lower()
        score = 0
        
        # Real-world application indicators
        practical_terms = [
            'business', 'commercial', 'enterprise', 'production',
            'user', 'customer', 'client', 'industry', 'solution',
            'problem solving', 'automation', 'efficiency', 'productivity'
        ]
        
        if any(term in text for term in practical_terms):
            score += 5
        
        # Domain-specific applications
        domain_apps = [
            'healthcare', 'finance', 'education', 'e-commerce', 'social',
            'transportation', 'logistics', 'manufacturing', 'agriculture'
        ]
        
        if any(app in text for app in domain_apps):
            score += 5
        
        return min(score, 10)

    def _calculate_certification_score(self, certifications_str: str):
        try:
            if not certifications_str:
                return 0.0
            parts = [c.strip() for c in certifications_str.split(',') if c.strip()]
            if not parts:
                return 0.0
            weight_map = {'aws':15,'azure':15,'gcp':15,'oracle':12,'sap':12,'cisco':12,'redhat':10,'linux':8,'python':5,'java':5}
            score = 0
            for c in parts:
                key = c.lower()
                added = False
                for k,w in weight_map.items():
                    if k in key:
                        score += w
                        added = True
                        break
                if not added:
                    score += 4
            return min(score, 40)
        except Exception as e:
            logger.error(f"Error scoring certifications: {str(e)}")
            return 0.0

    def _calculate_dsa_score(self, student_data: dict):
        """
        Calculate DSA & Problem Solving score based on number of problems solved by difficulty.
        
        Scoring Logic:
        - Easy: 150+ problems = full score (100%)
        - Medium: 100+ problems = full score (100%)
        - Hard: 30+ problems = full score (100%)
        
        Bonus Rules:
        - If Medium >= 50: Easy automatically gets full score (100%)
        - If Hard >= 15: Both Easy and Medium get full score (100%)
        
        Final Score Formula:
        DSA Score = (Easy Score × 0.20) + (Medium Score × 0.35) + (Hard Score × 0.45)
        
        Args:
            student_data: Dictionary containing student information
            
        Returns:
            float: DSA score (0-100)
        """
        try:
            # Extract DSA problem counts
            easy_count = int(student_data.get('dsaEasy', 0) or 0)
            medium_count = int(student_data.get('dsaMedium', 0) or 0)
            hard_count = int(student_data.get('dsaHard', 0) or 0)
            
            logger.info(f"📊 DSA Problem Counts - Easy: {easy_count}, Medium: {medium_count}, Hard: {hard_count}")
            
            # Calculate individual difficulty scores (0-100 scale)
            # Easy: 150+ = 100%
            easy_score = min((easy_count / 150.0) * 100, 100)
            
            # Medium: 100+ = 100%
            medium_score = min((medium_count / 100.0) * 100, 100)
            
            # Hard: 30+ = 100%
            hard_score = min((hard_count / 30.0) * 100, 100)
            
            # Apply bonus rules
            # Bonus 1: If Medium >= 50, Easy gets full score
            if medium_count >= 50:
                easy_score = 100.0
                logger.info("🎯 Bonus Applied: Medium >= 50, Easy score set to 100%")
            
            # Bonus 2: If Hard >= 15, both Easy and Medium get full score
            if hard_count >= 15:
                easy_score = 100.0
                medium_score = 100.0
                logger.info("🎯 Bonus Applied: Hard >= 15, Easy and Medium scores set to 100%")
            
            # Calculate weighted final score
            # Formula: Easy × 0.20 + Medium × 0.35 + Hard × 0.45
            final_score = (easy_score * 0.20) + (medium_score * 0.35) + (hard_score * 0.45)
            
            logger.info(f"📈 DSA Score Breakdown:")
            logger.info(f"   Easy: {easy_score:.2f}% × 0.20 = {easy_score * 0.20:.2f}")
            logger.info(f"   Medium: {medium_score:.2f}% × 0.35 = {medium_score * 0.35:.2f}")
            logger.info(f"   Hard: {hard_score:.2f}% × 0.45 = {hard_score * 0.45:.2f}")
            logger.info(f"   Final DSA Score: {final_score:.2f}/100")
            
            return final_score
            
        except Exception as e:
            logger.error(f"Error calculating DSA score: {str(e)}")
            return 0.0

    def _calculate_achievement_score(self, achievements_text: str):
        try:
            if not achievements_text:
                return 0.0, []
            lines = [l.strip() for l in achievements_text.replace('\r','').split('\n') if l.strip()]
            extracted = []
            score = 0
            keywords = {'winner':18,'rank':10,'publication':15,'patent':12,'open source':10,'conference':12,'scholarship':15}
            for ln in lines:
                lower = ln.lower()
                matched = False
                for k,w in keywords.items():
                    if k in lower:
                        score += w
                        matched = True
                        break
                if not matched:
                    score += 3
                extracted.append(ln)
            return min(score, 100), extracted  # Cap at 100 to match 0-100 scale
        except Exception as e:
            logger.error(f"Error scoring achievements: {str(e)}")
            return 0.0, []

    def _blend_scores(self, ml_score, academic_percent, skill_score, experience_score, project_score, certification_score, achievement_score, dsa_score):
        """
        Blend all score components into final placement score using standardized weights.
        
        Args:
            ml_score: ML model prediction (0-100) - informational only
            academic_percent: Academic performance score (0-100)
            skill_score: Technical skills score (0-100)
            experience_score: Experience score (0-10 scale)
            project_score: Project quality score (0-100)
            certification_score: Certification score (0-100)
            achievement_score: Achievement score (0-100)
            dsa_score: DSA & Problem Solving score (0-100)
        
        Returns:
            Tuple of (composite_score, category_breakdown)
            - composite_score: Final weighted score (0-100)
            - category_breakdown: Dict with individual weighted contributions
        
        Scoring Formula:
            Final Score = Σ(normalized_component * weight)
            Where weights sum to 1.0 (100%)
        """
        try:
            # Normalize all inputs to their valid ranges
            academic_norm = self._normalize_score(academic_percent, *SCORE_RANGES['academics'])
            skills_norm = self._normalize_score(skill_score, *SCORE_RANGES['skills'])
            projects_norm = self._normalize_score(project_score, *SCORE_RANGES['projects'])
            dsa_norm = self._normalize_score(dsa_score, *SCORE_RANGES['dsa'])
            exp_norm = self._normalize_score(experience_score, *SCORE_RANGES['experience'])
            cert_norm = self._normalize_score(certification_score, *SCORE_RANGES['certifications'])
            achieve_norm = self._normalize_score(achievement_score, *SCORE_RANGES['achievements'])
            
            # Merge certifications + achievements into single bucket (average of both)
            ach_cert_bucket = (cert_norm + achieve_norm) / 2.0
            
            # Calculate weighted composite score using SCORING_WEIGHTS
            composite = (
                academic_norm * SCORING_WEIGHTS['academics'] +
                skills_norm * SCORING_WEIGHTS['skills'] +
                projects_norm * SCORING_WEIGHTS['projects'] +
                dsa_norm * SCORING_WEIGHTS['dsa'] +
                (exp_norm * 10) * SCORING_WEIGHTS['experience'] +  # Convert 0-10 to 0-100 scale
                ach_cert_bucket * SCORING_WEIGHTS['achievements_certifications']
            )
            
            # Calculate individual weighted contributions for transparency
            category_breakdown = {
                'academics': round(academic_norm * SCORING_WEIGHTS['academics'], 2),
                'skills': round(skills_norm * SCORING_WEIGHTS['skills'], 2),
                'projects': round(projects_norm * SCORING_WEIGHTS['projects'], 2),
                'dsa': round(dsa_norm * SCORING_WEIGHTS['dsa'], 2),
                'experience': round((exp_norm * 10) * SCORING_WEIGHTS['experience'], 2),
                'achievements_certifications': round(ach_cert_bucket * SCORING_WEIGHTS['achievements_certifications'], 2),
                'ml_model_informational': round(ml_score, 2)  # Not weighted but included for reference
            }
            
            # Log the scoring breakdown for debugging
            logger.debug(f"Score Breakdown:")
            logger.debug(f"  Academics: {academic_norm:.1f} * {SCORING_WEIGHTS['academics']} = {category_breakdown['academics']}")
            logger.debug(f"  Skills: {skills_norm:.1f} * {SCORING_WEIGHTS['skills']} = {category_breakdown['skills']}")
            logger.debug(f"  Projects: {projects_norm:.1f} * {SCORING_WEIGHTS['projects']} = {category_breakdown['projects']}")
            logger.debug(f"  DSA: {dsa_norm:.1f} * {SCORING_WEIGHTS['dsa']} = {category_breakdown['dsa']}")
            logger.debug(f"  Experience: {exp_norm:.1f} * {SCORING_WEIGHTS['experience']} = {category_breakdown['experience']}")
            logger.debug(f"  Achievements+Certs: {ach_cert_bucket:.1f} * {SCORING_WEIGHTS['achievements_certifications']} = {category_breakdown['achievements_certifications']}")
            logger.debug(f"  Final Composite: {composite:.2f}")
            
            # Ensure final score is within 0-100 range
            final_score = self._normalize_score(composite, 0, 100)
            
            return final_score, category_breakdown
            
        except Exception as e:
            logger.error(f"Error blending scores: {str(e)}")
            # Fallback to ML score if blending fails
            return self._normalize_score(ml_score, 0, 100), {
                'error': 'Score blending failed',
                'ml_model_informational': ml_score
            }
    
    def _normalize_score(self, value, min_val, max_val):
        """
        Normalize a score to be within the specified range.
        
        Args:
            value: Score to normalize
            min_val: Minimum valid value
            max_val: Maximum valid value
        
        Returns:
            Normalized score clamped to [min_val, max_val]
        """
        try:
            normalized = max(min_val, min(max_val, float(value)))
            return normalized
        except (ValueError, TypeError):
            logger.warning(f"Invalid value for normalization: {value}, using {min_val}")
            return min_val
    
    def _generate_recommendations(self, placement_score, features, skills, domain):
        """Generate personalized recommendations"""
        recommendations = []
        
        try:
            # Check if user has data science skills
            data_science_skills = {
                'python', 'pandas', 'numpy', 'scikit-learn', 'machine learning', 'sql', 
                'tableau', 'power bi', 'statistics', 'data analysis', 'tensorflow', 
                'pytorch', 'r', 'jupyter', 'matplotlib', 'seaborn'
            }
            user_skills_lower = [skill.lower() for skill in skills]
            ds_skill_count = sum(1 for skill in user_skills_lower 
                               for ds_skill in data_science_skills 
                               if ds_skill in skill)
            
            # Data Science specific recommendations
            if ds_skill_count >= 3 or 'data' in domain.lower():
                if ds_skill_count < 5:
                    recommendations.append("🔬 Complete the Data Science foundation: Learn Python, Pandas, SQL, and basic statistics.")
                    recommendations.append("📊 Build end-to-end data projects with real datasets (not just tutorials).")
                else:
                    recommendations.append("🚀 You have strong Data Science skills! Focus on specialized areas like NLP, Computer Vision, or MLOps.")
                    recommendations.append("🏭 Practice deploying ML models using Flask/FastAPI and cloud platforms.")
                
                recommendations.append("📈 Create a portfolio showcasing data visualization and machine learning projects.")
                
                if placement_score >= 75:
                    recommendations.append("🎯 Target Data Scientist, ML Engineer, or Data Analyst roles at tech companies.")
                elif placement_score >= 50:
                    recommendations.append("🎯 Consider Data Analyst or Junior Data Scientist positions to start your career.")
                else:
                    recommendations.append("🎯 Build more practical projects and improve your data science fundamentals.")
            
            # Academic recommendations
            if features['Aggregate_%'] < 70:
                recommendations.append("📚 Focus on improving your academic performance to increase placement chances.")
            
            if features['10th_%'] < 75:
                recommendations.append("📖 Consider strengthening your foundational knowledge from 10th standard.")
            
            if features['12th_%'] < 75:
                recommendations.append("📖 Work on improving your 12th standard performance as it's often considered by recruiters.")
            
            # Skill recommendations
            if len(skills) < 3:
                recommendations.append("🛠️ Develop more technical skills relevant to your domain.")
            
            # Score-based recommendations
            if placement_score < 50:
                recommendations.append("💼 Focus on building a strong portfolio with projects and internships.")
                recommendations.append("🏆 Participate in hackathons and coding competitions to showcase your skills.")
            elif placement_score < 75:
                recommendations.append("📈 Continue building your technical expertise and soft skills.")
                recommendations.append("🤝 Network with industry professionals and alumni.")
            else:
                recommendations.append("✅ You're well-positioned for placement! Focus on interview preparation.")
                recommendations.append("🎯 Research target companies and prepare company-specific strategies.")
            
            # Domain-specific recommendations
            if domain == 'btech_cse' or 'computer' in domain.lower():
                recommendations.append("💻 Stay updated with latest technologies like AI/ML, Cloud Computing, and DevOps.")
            elif domain == 'management' or 'bba' in domain.lower():
                recommendations.append("📊 Develop strong analytical and communication skills for business roles.")
            elif domain == 'pharmacy':
                recommendations.append("💊 Focus on clinical research and regulatory compliance knowledge.")
            elif 'data' in domain.lower() or 'analytics' in domain.lower():
                recommendations.append("📊 Master the data science pipeline: collection, cleaning, analysis, and visualization.")
                recommendations.append("🔍 Learn both Python and R for comprehensive data analysis capabilities.")
            
            # Limit to 6 recommendations
            return recommendations[:6]
            
        except Exception as e:
            logger.error(f"Error generating recommendations: {str(e)}")
            return ["🎯 Focus on improving your overall profile for better placement opportunities."]
    
    def _fallback_prediction(self, student_data):
        """Fallback to rule-based prediction if ML model fails"""
        try:
            logger.info("Using fallback rule-based prediction")
            
            # Extract basic data
            cgpa = float(student_data.get('collegeCGPA', 0))
            tenth_percent = float(student_data.get('tenthPercentage', 0))
            twelfth_percent = float(student_data.get('twelfthPercentage', 0))
            skills = student_data.get('selectedSkills', [])
            domain = student_data.get('selectedDomainId', '')
            
            # Academics raw percent approximation (normalize different components)
            academic_percent = (
                (tenth_percent / 100) * 0.3 +
                (twelfth_percent / 100) * 0.3 +
                ((cgpa * 10) / 100) * 0.4
            ) * 100  # scale back to 0-100

            # Skills relevance (simple cardinality based)
            skill_score = min(len(skills) * 8, 100)

            # Projects (if provided as list)
            projects = student_data.get('projects', []) or []
            project_score = min(len(projects) * 15, 100)  # crude: more projects increases score (cap ~7 for full)

            # Experience (hackathons + internships)
            exp_score = 0
            if student_data.get('hackathonsParticipated'):
                exp_score += min(int(student_data.get('numHackathons', 0)) * 10, 50)
            if student_data.get('internshipsCompleted'):
                exp_score += min(int(student_data.get('numInternships', 0)) * 25, 50)
            exp_score = min(exp_score, 100)

            # Achievements & certifications (text heuristics)
            certs = student_data.get('certifications', '') or ''
            achievements_text = student_data.get('achievements', '') or ''
            cert_units = len([c for c in certs.split(',') if c.strip()])
            ach_lines = len([l for l in achievements_text.split('\n') if l.strip()])
            ach_cert_score = min(cert_units * 10 + ach_lines * 8, 100)

            # Weight blending (30,20,20,15,15)
            placement_score = (
                academic_percent * 0.30 +
                skill_score * 0.20 +
                project_score * 0.20 +
                exp_score * 0.15 +
                ach_cert_score * 0.15
            )
            placement_score = max(0, min(100, round(placement_score, 2)))

            breakdown = {
                'academics': round(academic_percent * 0.30, 2),
                'skills': round(skill_score * 0.20, 2),
                'projects': round(project_score * 0.20, 2),
                'experience': round(exp_score * 0.15, 2),
                'achievements_certifications': round(ach_cert_score * 0.15, 2),
                'ml_model_informational': 0
            }
            
            return {
                'placementScore': int(placement_score),
                'mlPrediction': 'Fallback',
                'predictionConfidence': 60.0,
                'academicScore': float(round(academic_percent, 2)),
                'skillScore': float(round(skill_score, 2)),
                'experienceScore': float(round(exp_score, 2)),
                'projectScore': float(round(project_score, 2)),
                'achievementScore': float(round(ach_cert_score, 2)),
                'scoreBreakdown': breakdown,
                'recommendations': ["Using fallback prediction system. Please ensure ML model is properly trained."],
                'isEligible': bool(placement_score >= PLACEMENT_ELIGIBILITY_THRESHOLD),
                'eligibilityThreshold': PLACEMENT_ELIGIBILITY_THRESHOLD,
                'modelUsed': 'Fallback Rules',
                'features': {
                    '10th_%': float(tenth_percent),
                    '12th_%': float(twelfth_percent),
                    'Aggregate_%': float(cgpa * 10)
                },
                'inputData': {
                    'tenthPercentage': float(tenth_percent),
                    'twelfthPercentage': float(twelfth_percent),
                    'collegeCGPA': float(cgpa)
                }
            }
            
        except Exception as e:
            logger.error(f"Error in fallback prediction: {str(e)}")
            return {
                'placementScore': 50,
                'mlPrediction': 'Error',
                'predictionConfidence': 0.0,
                'academicScore': 0.0,
                'skillScore': 0.0,
                'experienceScore': 0.0,
                'recommendations': ["System error. Please try again later."],
                'isEligible': False,
                'modelUsed': 'Error',
                'features': {'10th_%': 0.0, '12th_%': 0.0, 'Aggregate_%': 0.0},
                'inputData': {'tenthPercentage': 0.0, 'twelfthPercentage': 0.0, 'collegeCGPA': 0.0}
            }
    
    def get_model_info(self):
        """Get information about the loaded model"""
        if not self.is_loaded:
            return {"status": "Model not loaded"}
        
        return {
            "status": "Model loaded successfully",
            "model_type": type(self.model).__name__,
            "features": self.feature_columns,
            "model_path": self.model_path,
            "scaler_path": self.scaler_path
        }
