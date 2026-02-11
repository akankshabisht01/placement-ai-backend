def get_domain_data():
    """Get comprehensive domain and career data"""
    return [
        {
            "id": "cs_it",
            "name": "CS/IT",
            "categories": [
                {
                    "id": "data_ai",
                    "name": "Data & AI",
                    "roles": [
                        "Data Scientist",
                        "Data Analyst",
                        "ML Engineer",
                        "AI Engineer",
                        "Business Intelligence Analyst",
                        "NLP Engineer"
                    ],
                    "skills": [
                        "Python",
                        "SQL",
                        "Pandas",
                        "Machine Learning",
                        "Deep Learning",
                        "NLP",
                        "Git",
                        "Power BI",
                        "Tableau",
                        "TensorFlow",
                        "PyTorch",
                        "Computer Vision",
                        "Big Data",
                        "Data Visualization"
                    ],
                    "averageSalary": "8-15 LPA",
                    "demandTrend": "High and increasing",
                    "topCompanies": ["Microsoft", "Google", "Amazon", "IBM", "Accenture"]
                },
                {
                    "id": "software_dev",
                    "name": "Software Development",
                    "roles": [
                        "Full Stack Developer",
                        "Backend Developer",
                        "Frontend Developer",
                        "DevOps Engineer",
                        "Mobile App Developer",
                        "Game Developer",
                        "Cybersecurity Specialist"
                    ],
                    "skills": [
                        "JavaScript",
                        "React",
                        "Node.js",
                        "Angular",
                        "Vue.js",
                        "Java",
                        "Python",
                        "C#",
                        "PHP",
                        "Firebase",
                        "Docker",
                        "AWS",
                        "GitHub",
                        "MongoDB",
                        "SQL",
                        "REST API",
                        "GraphQL"
                    ],
                    "averageSalary": "6-14 LPA",
                    "demandTrend": "Very high",
                    "topCompanies": ["TCS", "Infosys", "Wipro", "Microsoft", "Amazon"]
                }
            ]
        },
        {
            "id": "mechanical",
            "name": "Mechanical Engineering",
            "categories": [
                {
                    "id": "mech_design",
                    "name": "Mechanical Design",
                    "roles": [
                        "Design Engineer",
                        "Automotive Engineer",
                        "HVAC Engineer",
                        "Robotics Engineer",
                        "Quality Control Engineer"
                    ],
                    "skills": [
                        "SolidWorks",
                        "AutoCAD",
                        "Thermodynamics",
                        "Finite Element Analysis",
                        "Python",
                        "MATLAB",
                        "Fluid Mechanics",
                        "3D Modeling",
                        "Manufacturing Processes",
                        "Project Management"
                    ],
                    "averageSalary": "5-10 LPA",
                    "demandTrend": "Steady",
                    "topCompanies": ["Tata Motors", "Mahindra", "Maruti Suzuki", "L&T", "Godrej"]
                }
            ]
        },
        {
            "id": "electronics",
            "name": "Electronics & Communication",
            "categories": [
                {
                    "id": "embedded_systems",
                    "name": "Embedded Systems & VLSI",
                    "roles": [
                        "Embedded Systems Engineer",
                        "VLSI Design Engineer",
                        "Signal Processing Engineer",
                        "IoT Developer",
                        "PCB Designer"
                    ],
                    "skills": [
                        "C/C++",
                        "Verilog",
                        "VHDL",
                        "Microcontrollers",
                        "MATLAB",
                        "Eagle",
                        "Arduino",
                        "Raspberry Pi",
                        "Communication Protocols",
                        "PCB Design"
                    ],
                    "averageSalary": "6-12 LPA",
                    "demandTrend": "High",
                    "topCompanies": ["Intel", "Qualcomm", "Texas Instruments", "AMD", "Broadcom"]
                }
            ]
        },
        {
            "id": "pharmacy",
            "name": "Pharmacy",
            "categories": [
                {
                    "id": "clinical_research",
                    "name": "Clinical Research & Pharmacovigilance",
                    "roles": [
                        "Clinical Research Associate",
                        "Pharmacovigilance Specialist",
                        "Drug Safety Associate",
                        "Quality Control Analyst",
                        "Medical Representative"
                    ],
                    "skills": [
                        "Clinical Trial Process",
                        "Pharmaceutical Regulations",
                        "Excel",
                        "Data Entry",
                        "Communication",
                        "Pharmacology",
                        "Drug Development",
                        "GMP Knowledge",
                        "Data Analysis"
                    ],
                    "averageSalary": "4-8 LPA",
                    "demandTrend": "Moderate",
                    "topCompanies": ["Sun Pharma", "Dr. Reddy's", "Cipla", "Abbott", "Pfizer"]
                }
            ]
        },
        {
            "id": "bba",
            "name": "BBA",
            "categories": [
                {
                    "id": "business_management",
                    "name": "Business Management",
                    "roles": [
                        "Business Analyst",
                        "HR Executive",
                        "Marketing Specialist",
                        "Financial Analyst",
                        "Operations Manager"
                    ],
                    "skills": [
                        "Excel",
                        "PowerPoint",
                        "CRM Tools",
                        "Digital Marketing",
                        "Communication",
                        "Project Management",
                        "Financial Analysis",
                        "Market Research",
                        "Business Development",
                        "Leadership"
                    ],
                    "averageSalary": "4-9 LPA",
                    "demandTrend": "Steady",
                    "topCompanies": ["Deloitte", "KPMG", "EY", "PwC", "McKinsey"]
                }
            ]
        },
        {
            "id": "agriculture",
            "name": "Agriculture",
            "categories": [
                {
                    "id": "agri_science",
                    "name": "Agricultural Science",
                    "roles": [
                        "Agricultural Officer",
                        "Agronomist",
                        "Quality Assurance Officer",
                        "Food Safety Analyst",
                        "Farm Manager"
                    ],
                    "skills": [
                        "Soil Science",
                        "GIS Tools",
                        "Pest Management",
                        "Report Writing",
                        "Excel",
                        "R/Python",
                        "Agricultural Economics",
                        "Crop Management",
                        "Sustainable Farming Practices"
                    ],
                    "averageSalary": "4-7 LPA",
                    "demandTrend": "Growing",
                    "topCompanies": ["Syngenta", "Bayer CropScience", "ITC Agri", "Godrej Agrovet", "Nuziveedu Seeds"]
                }
            ]
        }
    ]

def get_all_skills():
    """Get all unique skills across all domains"""
    domains = get_domain_data()
    all_skills = set()
    
    for domain in domains:
        for category in domain["categories"]:
            all_skills.update(category["skills"])
    
    return sorted(list(all_skills))

def get_all_roles():
    """Get all unique roles across all domains"""
    domains = get_domain_data()
    all_roles = set()
    
    for domain in domains:
        for category in domain["categories"]:
            all_roles.update(category["roles"])
    
    return sorted(list(all_roles))

def get_domain_by_id(domain_id):
    """Get domain data by ID"""
    domains = get_domain_data()
    for domain in domains:
        if domain["id"] == domain_id:
            return domain
    return None

def get_domain_by_name(domain_name):
    """Get domain data by name"""
    domains = get_domain_data()
    for domain in domains:
        if domain["name"].lower() == domain_name.lower():
            return domain
    return None
