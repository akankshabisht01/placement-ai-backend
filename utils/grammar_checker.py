import re
from typing import Dict, List, Tuple, Optional
import difflib
from collections import defaultdict

class GrammarSpellingChecker:
    """
    Comprehensive grammar and spelling checker for resume content
    """
    
    def __init__(self):
        # Extended spelling mistakes dictionary
        self.spelling_mistakes = {
            # Common misspellings
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
            'succesfully': 'successfully',
            'techincal': 'technical',
            'togather': 'together',
            'univeristy': 'university',
            'writen': 'written',
            'acheivement': 'achievement',
            'adress': 'address',
            'advertisment': 'advertisement',
            'begining': 'beginning',
            'beleive': 'believe',
            'buisness': 'business',
            'carrer': 'career',
            'compleate': 'complete',
            'conect': 'connect',
            'dependance': 'dependence',
            'differance': 'difference',
            'dificult': 'difficult',
            'disapear': 'disappear',
            'embarass': 'embarrass',
            'enviroment': 'environment',
            'existance': 'existence',
            'familar': 'familiar',
            'favourate': 'favorite',
            'foward': 'forward',
            'freind': 'friend',
            'garentee': 'guarantee',
            'happend': 'happened',
            'harrassment': 'harassment',
            'immediatly': 'immediately',
            'independant': 'independent',
            'intresting': 'interesting',
            'judgement': 'judgment',
            'lenght': 'length',
            'librery': 'library',
            'lisence': 'license',
            'maintanance': 'maintenance',
            'neccessary': 'necessary',
            'occured': 'occurred',
            'oppurtunity': 'opportunity',
            'publically': 'publicly',
            'recieve': 'receive',
            'recomend': 'recommend',
            'relevent': 'relevant',
            'resposibility': 'responsibility',
            'seperate': 'separate',
            'succesful': 'successful',
            'succesfully': 'successfully',
            'techincal': 'technical',
            'temperture': 'temperature',
            'thier': 'their',
            'tommorow': 'tomorrow',
            'truely': 'truly',
            'univeristy': 'university',
            'usefull': 'useful',
            'writting': 'writing',
            'writen': 'written'
        }
        
        # Grammar patterns and their corrections - ONLY definite errors, no homophones
        self.grammar_patterns = [
            # Capitalization of standalone "i" (not in acronyms/tech terms)
            (r'(?<![a-zA-Z])\bi\b(?![a-zA-Z])', 'I', 'Capitalize "i" when referring to yourself'),
            
            # Day names (only when clearly not capitalized in context)
            (r'(?<![A-Za-z])(monday|tuesday|wednesday|thursday|friday|saturday|sunday)(?![A-Za-z])', 
             lambda m: m.group().capitalize(), 'Capitalize day names'),
            
            # Month names  
            (r'(?<![A-Za-z])(january|february|march|april|june|july|august|september|october|november|december)(?![A-Za-z])',
             lambda m: m.group().capitalize(), 'Capitalize month names'),
            
            # Article repetition (definite error)
            (r'\b(a|an|the)\s+\1\b', 'article repetition', 'Remove duplicate articles'),
            
            # Verb repetition (definite error)
            (r'\b(is|are|was|were|be|been)\s+\1\b', 'verb repetition', 'Remove duplicate verbs'),
            
            # Conjunction repetition (definite error)
            (r'\b(and|or|but)\s+\1\b', 'conjunction repetition', 'Remove duplicate conjunctions'),
            
            # Missing apostrophes in contractions (definite error)
            (r'\b(dont|wont|cant|shouldnt|wouldnt|couldnt|havent|hasnt|hadnt|isnt|arent|wasnt|werent|didnt|doesnt)\b',
             lambda m: m.group()[:-2] + "n't", 'Add missing apostrophe in contraction')
        ]
        
        # Professional terminology corrections - ONLY for clear misspellings, not style preferences
        # Removed: js→JavaScript, backend→back-end, frontend→front-end (these are style choices, not errors)
        self.professional_terms = {
            'resumee': 'résumé',
            'phd': 'PhD',
            'mba': 'MBA',
            'btech': 'B.Tech',
            'mtech': 'M.Tech'
            # Note: Removed most items as they were flagging valid technical terms as "errors"
            # Terms like 'js', 'api', 'html', 'sql', 'aws', 'backend', 'frontend' are perfectly acceptable
        }
    
    def check_text(self, text: str, source: str = 'unknown') -> Dict:
        """
        Check text for spelling and grammar errors
        
        Args:
            text: Text to check
            source: Source of the text (e.g., 'projects', 'skills')
            
        Returns:
            Dictionary with errors, corrections, and suggestions
        """
        if not text or not text.strip():
            return {
                'spelling_errors': [],
                'grammar_errors': [],
                'professional_errors': [],
                'total_errors': 0,
                'corrections': [],
                'suggestions': []
            }
        
        spelling_errors = []
        grammar_errors = []
        professional_errors = []
        corrections = []
        suggestions = []
        
        # Technical abbreviations and terms to exclude from grammar checking
        # Includes: single letters (programming), degrees, tech acronyms, etc.
        technical_exclusions = {
            # Single letters (programming languages, variables, grades)
            'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 
            'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z',
            
            # Programming languages (single/short names)
            'c', 'c++', 'c#', 'r', 'go', 'f#', 'js', 'ts', 'py', 'rb', 'pl', 'sh',
            
            # Educational degrees and certifications
            'btech', 'b.tech', 'mtech', 'm.tech', 'bsc', 'b.sc', 'msc', 'm.sc',
            'bca', 'mca', 'ba', 'ma', 'be', 'me', 'bba', 'mba', 'phd', 'ph.d',
            'bcom', 'b.com', 'mcom', 'm.com', 'llb', 'llm', 'md', 'mbbs',
            'barch', 'b.arch', 'bdes', 'mdes', 'bfa', 'mfa',
            
            # Cloud & DevOps
            'aws', 'gcp', 'azure', 'ec2', 's3', 'ecs', 'eks', 'rds', 'vpc', 'iam',
            'ci', 'cd', 'ci/cd', 'devops', 'sre', 'k8s', 'docker', 'helm',
            
            # Web & API
            'api', 'apis', 'rest', 'restful', 'graphql', 'grpc', 'soap', 'jwt', 'oauth',
            'http', 'https', 'html', 'css', 'scss', 'sass', 'less', 'xml', 'json', 'yaml',
            'dom', 'ajax', 'spa', 'pwa', 'ssr', 'ssg', 'cdn', 'dns', 'ssl', 'tls',
            
            # Databases
            'sql', 'nosql', 'mysql', 'postgresql', 'mongodb', 'redis', 'sqlite',
            'dynamodb', 'cassandra', 'neo4j', 'elasticsearch', 'kafka',
            
            # AI/ML
            'ai', 'ml', 'dl', 'nlp', 'cv', 'cnn', 'rnn', 'lstm', 'gan', 'bert', 'gpt',
            'llm', 'llms', 'rag', 'mlops', 'aiops',
            
            # Tools & Frameworks
            'git', 'svn', 'npm', 'yarn', 'pip', 'maven', 'gradle', 'cmake',
            'cli', 'sdk', 'ide', 'vscode', 'vim', 'emacs',
            'ui', 'ux', 'ui/ux', 'cms', 'crm', 'erp', 'sap',
            
            # Networking
            'tcp', 'udp', 'ip', 'ftp', 'sftp', 'ssh', 'vpn', 'lan', 'wan', 'wifi',
            'dns', 'dhcp', 'nat', 'ssl', 'tls', 'https',
            
            # Hardware & Systems
            'os', 'pc', 'cpu', 'gpu', 'tpu', 'ram', 'rom', 'ssd', 'hdd', 'nvme',
            'usb', 'io', 'iot', 'ar', 'vr', 'xr', 'hpc',
            
            # Business & General
            'hr', 'it', 'qa', 'qc', 'pm', 'ba', 'cto', 'ceo', 'cfo', 'coo',
            'b2b', 'b2c', 'saas', 'paas', 'iaas', 'roi', 'kpi', 'okr',
            
            # Misc tech terms
            'agile', 'scrum', 'kanban', 'jira', 'asana', 'figma', 'xd',
            'regex', 'xpath', 'linq', 'orm', 'mvc', 'mvvm', 'mvp',
            'poc', 'mvp', 'eta', 'eod', 'wip', 'pr', 'mr', 'cr'
        }
        
        # Check spelling
        words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
        for word in words:
            # Skip technical exclusions
            if word.lower() in technical_exclusions:
                continue
            
            if word in self.spelling_mistakes:
                correction = self.spelling_mistakes[word]
                spelling_errors.append({
                    'word': word,
                    'correction': correction,
                    'context': text,
                    'source': source,
                    'severity': 'high' if len(word) > 6 else 'medium'
                })
                corrections.append({
                    'original': word,
                    'corrected': correction,
                    'type': 'spelling'
                })
        
        # Check grammar patterns (avoid flagging after abbreviations)
        for pattern, replacement, issue_type in self.grammar_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                matched_text = match.group().strip()
                
                # Skip if it's a single letter or technical term
                if len(matched_text) <= 2 and matched_text.lower() in technical_exclusions:
                    continue
                
                # Skip if preceded by common abbreviation pattern (B.Tech, M.Sc, etc.)
                before_pos = max(0, match.start() - 10)
                context_before = text[before_pos:match.start()]
                if re.search(r'\b[A-Z]\.\s*$', context_before):
                    continue
                
                grammar_errors.append({
                    'text': matched_text,
                    'issue': issue_type,
                    'context': text,
                    'source': source,
                    'position': match.start(),
                    'severity': 'medium'
                })
                suggestions.append({
                    'issue': issue_type,
                    'suggestion': f'Review usage of "{matched_text}"'
                })
        
        # Check professional terminology (only for standalone terms, not parts of compound words)
        for term, correction in self.professional_terms.items():
            # Skip terms that are part of common compound words
            if term in ['js', 'ui', 'ux', 'cv', 'ai', 'ml', 'dl', 'it', 'hr', 'qa']:
                # Only flag if it's a standalone word or at the start
                pattern = r'(?<![a-zA-Z.-])' + re.escape(term) + r'(?![a-zA-Z.-])'
            else:
                pattern = r'\b' + re.escape(term) + r'\b'
            
            if re.search(pattern, text, re.IGNORECASE):
                if term.lower() != correction.lower():
                    professional_errors.append({
                        'term': term,
                        'correction': correction,
                        'context': text,
                        'source': source,
                        'severity': 'low'
                    })
                    corrections.append({
                        'original': term,
                        'corrected': correction,
                        'type': 'professional'
                    })
        
        total_errors = len(spelling_errors) + len(grammar_errors) + len(professional_errors)
        
        return {
            'spelling_errors': spelling_errors,
            'grammar_errors': grammar_errors,
            'professional_errors': professional_errors,
            'total_errors': total_errors,
            'corrections': corrections,
            'suggestions': suggestions
        }
    
    def check_resume(self, resume_data: Dict) -> Dict:
        """
        Check entire resume for spelling and grammar errors
        
        Args:
            resume_data: Parsed resume data
            
        Returns:
            Comprehensive error report with corrections
        """
        all_errors = {
            'spelling_errors': [],
            'grammar_errors': [],
            'professional_errors': [],
            'total_errors': 0,
            'corrections': [],
            'suggestions': [],
            'by_section': {},
            'summary': {}
        }
        
        # Define text sources to check
        text_sources = {
            'name': resume_data.get('name', ''),
            'degree': resume_data.get('degree', ''),
            'university': resume_data.get('university', ''),
            'skills': ' '.join(resume_data.get('skills', [])),
            'projects': ' '.join([str(p) for p in resume_data.get('projects', [])]),
            'internships': ' '.join([str(i) for i in resume_data.get('internships', [])]),
            'achievements': ' '.join([str(a) for a in resume_data.get('achievements', [])])
        }
        
        # Check each section
        for source, text in text_sources.items():
            if text and text.strip():
                section_errors = self.check_text(text, source)
                all_errors['by_section'][source] = section_errors
                
                # Aggregate errors
                all_errors['spelling_errors'].extend(section_errors['spelling_errors'])
                all_errors['grammar_errors'].extend(section_errors['grammar_errors'])
                all_errors['professional_errors'].extend(section_errors['professional_errors'])
                all_errors['corrections'].extend(section_errors['corrections'])
                all_errors['suggestions'].extend(section_errors['suggestions'])
        
        all_errors['total_errors'] = len(all_errors['spelling_errors']) + len(all_errors['grammar_errors']) + len(all_errors['professional_errors'])
        
        # Generate summary
        all_errors['summary'] = {
            'total_errors': all_errors['total_errors'],
            'spelling_count': len(all_errors['spelling_errors']),
            'grammar_count': len(all_errors['grammar_errors']),
            'professional_count': len(all_errors['professional_errors']),
            'sections_with_errors': len([s for s in all_errors['by_section'].values() if s['total_errors'] > 0]),
            'severity_breakdown': self._get_severity_breakdown(all_errors)
        }
        
        return all_errors
    
    def _get_severity_breakdown(self, errors: Dict) -> Dict:
        """Get breakdown of errors by severity"""
        severity_counts = {'high': 0, 'medium': 0, 'low': 0}
        
        for error_list in [errors['spelling_errors'], errors['grammar_errors'], errors['professional_errors']]:
            for error in error_list:
                severity = error.get('severity', 'medium')
                severity_counts[severity] += 1
        
        return severity_counts
    
    def get_correction_suggestions(self, errors: Dict) -> List[Dict]:
        """
        Generate specific correction suggestions for the user
        
        Args:
            errors: Error dictionary from check_resume
            
        Returns:
            List of correction suggestions with before/after examples
        """
        suggestions = []
        
        # Spelling corrections
        for error in errors['spelling_errors']:
            suggestions.append({
                'type': 'spelling',
                'section': error['source'],
                'original': error['word'],
                'correction': error['correction'],
                'context': error['context'],
                'severity': error['severity'],
                'suggestion': f"Change '{error['word']}' to '{error['correction']}'"
            })
        
        # Professional terminology corrections
        for error in errors['professional_errors']:
            suggestions.append({
                'type': 'professional',
                'section': error['source'],
                'original': error['term'],
                'correction': error['correction'],
                'context': error['context'],
                'severity': error['severity'],
                'suggestion': f"Use '{error['correction']}' instead of '{error['term']}'"
            })
        
        # Grammar suggestions
        for error in errors['grammar_errors']:
            suggestions.append({
                'type': 'grammar',
                'section': error['source'],
                'original': error['text'],
                'correction': 'Review grammar',
                'context': error['context'],
                'severity': error['severity'],
                'suggestion': f"Review: {error['issue']}"
            })
        
        return suggestions
    
    def apply_corrections(self, text: str, corrections: List[Dict]) -> str:
        """
        Apply corrections to text
        
        Args:
            text: Original text
            corrections: List of corrections to apply
            
        Returns:
            Corrected text
        """
        corrected_text = text
        
        for correction in corrections:
            if correction['type'] == 'spelling':
                # Use word boundaries to avoid partial matches
                pattern = r'\b' + re.escape(correction['original']) + r'\b'
                corrected_text = re.sub(pattern, correction['corrected'], corrected_text, flags=re.IGNORECASE)
            elif correction['type'] == 'professional':
                pattern = r'\b' + re.escape(correction['original']) + r'\b'
                corrected_text = re.sub(pattern, correction['corrected'], corrected_text, flags=re.IGNORECASE)
        
        return corrected_text


def check_resume_grammar_spelling(resume_data: Dict) -> Dict:
    """
    Main function to check resume for grammar and spelling errors
    
    Args:
        resume_data: Parsed resume data
        
    Returns:
        Comprehensive grammar and spelling check results
    """
    checker = GrammarSpellingChecker()
    return checker.check_resume(resume_data)


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
        "projects": ["E-commerce Website using React and Node.js", "Data Analysis Tool with Python"],
        "internships": ["Software Developer Intern at TechCorp", "Data Science Intern at DataCorp"],
        "achievements": ["Hackathon Winner", "Dean's List", "Best Project Award"]
    }
    
    result = check_resume_grammar_spelling(sample_resume)
    print("Grammar and Spelling Check Results:")
    print(f"Total Errors: {result['total_errors']}")
    print(f"Spelling Errors: {len(result['spelling_errors'])}")
    print(f"Grammar Errors: {len(result['grammar_errors'])}")
    print(f"Professional Errors: {len(result['professional_errors'])}")
