import numpy as np
from typing import Dict, List, Any
import json

class PlacementPredictor:
    def __init__(self):
        """Initialize the placement predictor with domain data"""
        self.domain_skills = {
            'Information Technology': ['Java', 'Python', 'JavaScript', 'SQL', 'C++', 'React', 'Node.js'],
            'Finance': ['Excel', 'Financial Analysis', 'Accounting', 'Statistics', 'PowerBI', 'QuickBooks'],
            'Marketing': ['SEO', 'Content Creation', 'Social Media', 'Analytics', 'Google Ads'],
            'Engineering': ['CAD', 'Project Management', 'Matlab', 'Data Analysis', 'SolidWorks'],
            'Computer Science': ['Python', 'Java', 'JavaScript', 'SQL', 'React', 'Node.js', 'Machine Learning'],
            'Mechanical': ['AutoCAD', 'SolidWorks', 'MATLAB', 'Thermodynamics', 'FEA'],
            'Electrical': ['C/C++', 'VLSI', 'Microcontrollers', 'PCB Design', 'MATLAB'],
            'Pharmacy': ['Clinical Research', 'Pharmacology', 'Drug Development', 'GMP', 'Data Analysis'],
            'Management': ['Excel', 'Financial Analysis', 'Marketing', 'Business Development', 'Leadership'],
            'Agriculture': ['Soil Science', 'GIS Tools', 'Crop Management', 'Pest Management', 'R/Python']
        }
        
        self.related_jobs = {
            'Information Technology': [
                'Software Engineer', 'Full Stack Developer', 'Data Scientist', 'System Analyst'
            ],
            'Finance': [
                'Financial Analyst', 'Accountant', 'Investment Banker', 'Risk Manager'
            ],
            'Marketing': [
                'Social Media Manager', 'SEO Specialist', 'Content Strategist', 'Brand Manager'
            ],
            'Engineering': [
                'Mechanical Engineer', 'Civil Engineer', 'Project Engineer', 'Quality Engineer'
            ],
            'Computer Science': [
                'Software Developer', 'Data Scientist', 'ML Engineer', 'DevOps Engineer'
            ],
            'Mechanical': [
                'Design Engineer', 'Automotive Engineer', 'HVAC Engineer', 'Robotics Engineer'
            ],
            'Electrical': [
                'Embedded Systems Engineer', 'VLSI Design Engineer', 'IoT Developer', 'PCB Designer'
            ],
            'Pharmacy': [
                'Clinical Research Associate', 'Pharmacovigilance Specialist', 'Drug Safety Associate'
            ],
            'Management': [
                'Business Analyst', 'HR Executive', 'Marketing Specialist', 'Financial Analyst'
            ],
            'Agriculture': [
                'Agricultural Officer', 'Agronomist', 'Quality Assurance Officer', 'Farm Manager'
            ]
        }

    def predict(self, student_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Predict placement probability based on student data
        
        Args:
            student_data: Dictionary containing student information
            
        Returns:
            Dictionary with prediction results
        """
        try:
            # Extract data
            domain = student_data.get('selectedDomainId', '')
            cgpa = float(student_data.get('collegeCGPA', 0))
            skills = student_data.get('selectedSkills', [])
            
            # Calculate academic score (40% weight)
            academic_score = cgpa * 8  # CGPA is out of 10, convert to percentage scale
            
            # Calculate skills score (50% weight)
            domain_skills_list = self.domain_skills.get(domain, [])
            if not domain_skills_list:
                # Fallback to generic skills if domain not found
                domain_skills_list = ['Python', 'Java', 'SQL', 'Communication', 'Problem Solving']
            
            # Calculate skill match
            user_skills_lower = [skill.lower() for skill in skills]
            domain_skills_lower = [skill.lower() for skill in domain_skills_list]
            
            # Count matching skills
            matching_skills = 0
            for domain_skill in domain_skills_lower:
                for user_skill in user_skills_lower:
                    if domain_skill in user_skill or user_skill in domain_skill:
                        matching_skills += 1
                        break
            
            skill_match_percentage = min((matching_skills / len(domain_skills_list)) * 100, 100)
            skills_score = skill_match_percentage * 0.5
            
            # Calculate experience bonus (10% weight)
            experience_bonus = 0
            
            # Project scoring
            num_projects = int(student_data.get('numProjects', 0))
            project_titles = student_data.get('projectTitles', '').strip()
            
            # Each project adds 5 points (up to 25 points for 5+ projects)
            project_score = min(num_projects * 5, 25)
            experience_bonus += project_score
            
            # If project titles are provided, add bonus points for relevant projects
            if project_titles:
                # Simple relevance check - if project titles contain domain-related keywords
                domain_keywords = {
                    'Computer Science': ['web', 'app', 'mobile', 'ai', 'ml', 'data', 'software', 'system'],
                    'Mechanical': ['design', 'cad', 'solidworks', 'automotive', 'manufacturing'],
                    'Electrical': ['circuit', 'embedded', 'iot', 'microcontroller', 'pcb'],
                    'Management': ['business', 'marketing', 'finance', 'analysis', 'strategy'],
                    'Pharmacy': ['clinical', 'research', 'drug', 'pharmaceutical', 'medical'],
                    'Agriculture': ['crop', 'soil', 'farming', 'agricultural', 'irrigation']
                }
                
                relevant_keywords = domain_keywords.get(domain, [])
                project_titles_lower = project_titles.lower()
                relevant_projects = sum(1 for keyword in relevant_keywords if keyword in project_titles_lower)
                if relevant_projects > 0:
                    experience_bonus += min(relevant_projects * 2, 10)  # Up to 10 bonus points for relevant projects
            
            # Hackathon scoring
            hackathons_participated = student_data.get('hackathonsParticipated', False)
            num_hackathons = int(student_data.get('numHackathons', 0))
            hackathon_winner = student_data.get('hackathonWinner', '').lower()
            
            if hackathons_participated and num_hackathons > 0:
                # Each hackathon participation adds 3 points
                hackathon_score = num_hackathons * 3
                experience_bonus += hackathon_score
                
                # If winner, add 10 bonus points
                if hackathon_winner == 'yes':
                    experience_bonus += 10
            
            # Internship scoring (existing logic)
            if student_data.get('internshipsCompleted', False):
                num_internships = int(student_data.get('numInternships', 0))
                internship_score = min(num_internships * 3, 15)  # Up to 15 points for internships
                experience_bonus += internship_score
            
            # Final score calculation
            final_score = (academic_score * 0.4) + skills_score + experience_bonus
            
            # Add slight randomness for realistic predictions
            final_score += np.random.normal(0, 3)
            final_score = max(0, min(100, final_score))
            
            # Determine placement probability
            placement_probability = round(final_score)
            
            # Determine personalization level
            if placement_probability < 40:
                personalization_level = 'low'
            elif placement_probability < 75:
                personalization_level = 'medium'
            else:
                personalization_level = 'high'
            
            # Get recommended skills
            recommended_skills = []
            for skill in domain_skills_list:
                skill_lower = skill.lower()
                if not any(skill_lower in user_skill or user_skill in skill_lower 
                          for user_skill in user_skills_lower):
                    recommended_skills.append(skill)
            
            # Get related jobs
            related_jobs = self.related_jobs.get(domain, [])
            
            # Generate personalized tips
            tips = self._get_personalized_tips(personalization_level)
            
            return {
                'placementProbability': placement_probability,
                'personalizationLevel': personalization_level,
                'recommendedSkills': recommended_skills[:5],  # Top 5 skills
                'relatedJobs': related_jobs,
                'personalizedTips': tips,
                'academicScore': round(academic_score, 2),
                'skillsScore': round(skills_score, 2),
                'experienceBonus': experience_bonus,
                'isEligible': placement_probability >= 50
            }
            
        except Exception as e:
            raise Exception(f"Error in prediction: {str(e)}")

    def _get_personalized_tips(self, level: str) -> List[str]:
        """Get personalized tips based on placement probability level"""
        tips = {
            'low': [
                "Consider taking online courses to strengthen your technical skills",
                "Work on practice projects to build your portfolio",
                "Improve your communication and presentation skills",
                "Join relevant student clubs or professional organizations",
                "Prepare for technical interviews with practice sessions"
            ],
            'medium': [
                "Focus on a specific domain within your field to become a specialist",
                "Connect with alumni for mentorship and advice",
                "Participate in hackathons or competitions to showcase your skills",
                "Apply for internships to gain practical experience",
                "Develop your soft skills alongside technical abilities"
            ],
            'high': [
                "Attend industry conferences and networking events",
                "Look for leadership opportunities in group projects",
                "Consider pursuing relevant certifications",
                "Create a strong LinkedIn profile and professional brand",
                "Research target companies and prepare company-specific strategies"
            ]
        }
        
        # Return 3 random tips from the appropriate level
        import random
        level_tips = tips.get(level, tips['medium'])
        return random.sample(level_tips, min(3, len(level_tips)))

    def get_domain_skills(self, domain: str) -> List[str]:
        """Get skills for a specific domain"""
        return self.domain_skills.get(domain, [])

    def get_related_jobs(self, domain: str) -> List[str]:
        """Get related jobs for a specific domain"""
        return self.related_jobs.get(domain, [])
