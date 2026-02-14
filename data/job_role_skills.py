# Complete mapping of job roles to their required skills
# This matches the frontend roleSkillsMap in PredictionForm.js
# Includes both display format ("NLP Engineer") and ID format ("nlp_engineer")

_SKILLS_DATA = {
    # Web Development
    'Frontend Developer': [
        'HTML', 'CSS', 'JavaScript (ES6+)', 'Responsive Design', 'React.js', 'Angular', 'Vue.js', 'Bootstrap', 'Git', 'Browser Developer Tools', 'DOM Manipulation', 'API Integration (REST)', 'Debugging'
    ],
    'Backend Developer': [
        'JavaScript (Node.js)', 'Python (Django)', 'Java (Spring Boot)', 'C# (.NET)', 'Express.js', 'Django', 'Spring Boot', 'ASP.NET Core', 'SQL', 'NoSQL Databases', 'REST API Development', 'Git', 'Authentication and Authorization', 'Basic Cloud or Deployment (Heroku, AWS)', 'Unit Testing'
    ],
    'Full-Stack Developer': [
        'HTML', 'CSS', 'JavaScript', 'React.js', 'Angular', 'Vue.js', 'Node.js', 'Django', 'Spring Boot', 'ASP.NET Core', 'REST APIs', 'SQL', 'NoSQL Databases', 'Responsive Design', 'Git', 'Basic Testing (Jest, Mocha, JUnit)', 'Cross-functional Collaboration'
    ],
    'UI/UX Developer': [
        'Wireframing and Prototyping', 'User Interface (UI) Design', 'User Experience (UX) Principles', 'Figma', 'Adobe XD', 'HTML', 'CSS', 'JavaScript (basic)', 'Responsive Design', 'Accessibility (WCAG)', 'Usability Testing'
    ],
    
    # Mobile Development
    'Android Developer': [
        'Kotlin', 'Java', 'Android SDK', 'Android Studio', 'XML/JSON', 'REST APIs', 'SQLite', 'UI/UX Design', 'Material Design', 'Git', 'Unit Testing'
    ],
    'iOS Developer': [
        'Swift', 'Objective-C', 'iOS SDK', 'Xcode', 'UIKit', 'Auto Layout', 'Storyboarding', 'REST APIs', 'Core Data', 'Git', 'Unit Testing'
    ],
    'Cross-Platform Developer': [
        'Flutter', 'Dart', 'React Native', 'JavaScript (ES6+)', 'Mobile App Development', 'UI/UX Design', 'API Integration', 'State Management (Redux, Provider, Bloc)', 'Git', 'Automated Testing'
    ],
    
    # Data & Analytics
    'Data Analyst': [
        'Data Analysis', 'SQL', 'Microsoft Excel', 'Data Visualization', 'Tableau', 'Power BI', 'Data Cleaning', 'Statistical Analysis', 'Python', 'R', 'Reporting'
    ],
    'Business Intelligence (BI) Analyst / BI Developer': [
        'Business Intelligence', 'SQL', 'Data Visualization (Tableau, Power BI)', 'ETL', 'Dashboard Development', 'Data Modeling', 'Reporting', 'Data Mining', 'Critical Thinking'
    ],
    'Data Engineer': [
        'Data Engineering', 'SQL', 'ETL', 'Python', 'Scala', 'Java', 'Data Warehousing', 'Cloud Platforms', 'Big Data (Hadoop, Spark)', 'Database Design', 'Git'
    ],
    'Big Data Engineer': [
        'Hadoop', 'Spark', 'Kafka', 'SQL', 'NoSQL Databases', 'Data Pipelines', 'ETL', 'Python', 'Java', 'Scala', 'Cloud Platforms', 'Data Modeling'
    ],
    'Junior Data Scientist': [
        'Python', 'Machine Learning', 'SQL', 'Data Analysis', 'Data Visualization', 'Statistics', 'scikit-learn', 'Data Cleaning', 'Communication Skills'
    ],
    'Data Scientist': [
        'Python', 'R', 'Machine Learning', 'Deep Learning', 'SQL', 'Statistics', 'Data Visualization', 'scikit-learn', 'TensorFlow', 'PyTorch', 'Feature Engineering', 'Model Evaluation'
    ],
    
    # AI & ML
    'Machine Learning Engineer': [
        'Machine Learning', 'Python', 'scikit-learn', 'Model Development', 'Data Preprocessing', 'Model Training', 'Model Deployment', 'Git', 'Statistics'
    ],
    'AI Engineer': [
        'Machine Learning', 'Python', 'Model Integration', 'Software Engineering', 'API Development', 'Data Analytics'
    ],
    'Deep Learning Engineer': [
        'Deep Learning', 'Python', 'TensorFlow', 'PyTorch', 'CNN/RNN', 'Neural Networks', 'Data Preprocessing', 'Model Optimization', 'Git'
    ],
    'NLP Engineer': [
        'Natural Language Processing (NLP)', 'Python', 'Text Preprocessing', 'Transformers', 'Chatbots', 'Machine Learning Models', 'scikit-learn'
    ],
    'Computer Vision Engineer': [
        'Computer Vision', 'Python', 'OpenCV', 'Image Processing', 'Deep Learning', 'CNNs', 'Model Deployment'
    ],
    'AI Research Assistant / Junior Researcher': [
        'Python', 'Machine Learning', 'Data Analysis', 'Research', 'Model Implementation', 'Communication Skills'
    ],
    'Data Scientist (ML Focus)': [
        'Python', 'Machine Learning', 'Deep Learning', 'Statistics', 'Data Analysis', 'Feature Engineering', 'Model Evaluation', 'TensorFlow', 'PyTorch', 'SQL'
    ],
    
    # Cloud & DevOps
    'Cloud Engineer': [
        'AWS', 'Microsoft Azure', 'Google Cloud Platform (GCP)', 'EC2', 'S3', 'Lambda', 'VM', 'Blob Storage (platform services)', 'Cloud Architecture', 'Bash', 'Python', 'Terraform', 'CloudFormation', 'Linux Systems', 'Git', 'Monitoring Tools (CloudWatch, Azure Monitor)', 'Troubleshooting'
    ],
    'DevOps Engineer': [
        'CI/CD Pipelines (Jenkins, GitLab CI)', 'Docker', 'Kubernetes', 'Infrastructure as Code (Terraform/Ansible)', 'Scripting (Bash/Python)', 'Linux Administration', 'Git', 'Monitoring/Logging (Prometheus, Grafana, ELK Stack)'
    ],
    'Site Reliability Engineer (SRE)': [
        'Monitoring & Incident Response', 'Automation (Python, Bash)', 'Cloud Platforms', 'Docker/Kubernetes', 'Reliability Engineering', 'Linux/Unix Systems', 'Troubleshooting'
    ],
    
    # Cybersecurity
    'Cybersecurity Analyst': [
        'Security Operations Center (SOC) skills', 'Threat Monitoring & Detection', 'SIEM Tools (Splunk, QRadar)', 'Incident Response', 'Network Security Fundamentals', 'Report Writing', 'Communication Skills'
    ],
    'Application Security Engineer': [
        'Secure Coding Practices', 'Application Vulnerability Assessment', 'OWASP Top 10', 'Static/Dynamic Analysis', 'Penetration Testing (basics)', 'Code Review'
    ],
    'Penetration Tester / Ethical Hacker': [
        'Penetration Testing', 'Kali Linux', 'Burp Suite', 'Metasploit', 'Web Application Security', 'Network Security', 'Scripting (Python, Bash)', 'Reporting'
    ],
}

# Build JOB_ROLE_SKILLS with both display format and ID format
JOB_ROLE_SKILLS = {}

for display_name, skills in _SKILLS_DATA.items():
    # Add display format (e.g., "NLP Engineer")
    JOB_ROLE_SKILLS[display_name] = skills
    
    # Add ID format (e.g., "nlp_engineer")
    id_format = display_name.lower().replace(' ', '_').replace('/', '_').replace('(', '').replace(')', '')
    JOB_ROLE_SKILLS[id_format] = skills

def get_job_role_skills(job_role_name):
    """
    Get the list of required skills for a specific job role.
    
    Handles both formats automatically:
    - Display format: "NLP Engineer", "Data Analyst" 
    - ID format: "nlp_engineer", "data_analyst"
    
    Args:
        job_role_name (str): The name of the job role in any format
    
    Returns:
        list: List of required skills for that job role, or empty list if not found
    """
    # Direct lookup (handles both formats since dictionary has both)
    if job_role_name in JOB_ROLE_SKILLS:
        return JOB_ROLE_SKILLS[job_role_name]
    
    # Try case-insensitive match
    for role, skills in JOB_ROLE_SKILLS.items():
        if role.lower() == job_role_name.lower():
            return skills
    
    # Try partial match as fallback
    for role, skills in JOB_ROLE_SKILLS.items():
        if job_role_name.lower() in role.lower() or role.lower() in job_role_name.lower():
            return skills
    
    return []
