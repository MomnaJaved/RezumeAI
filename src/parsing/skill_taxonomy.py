from __future__ import annotations

# Canonical normalization for common variants across domains
CANON = {
    #------------Engineers------------------- 
    # Languages
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "golang": "go",
    "cplusplus": "c++",
    "c#.net": "c#",
    "c#net": "c#",
    "dotnet": ".net",
    "asp.net": "asp.net",
    "asp net": "asp.net",

    # Frontend
    "react.js": "react",
    "nextjs": "next.js",
    "nodejs": "node.js",
    "vuejs": "vue.js",
    "nuxtjs": "nuxt.js",
    "angularjs": "angular",
    "tailwind": "tailwind css",
    "material ui": "material-ui",
    "mui": "material-ui",

    "reactjs": "react",
    "react js": "react",
    "node js": "node.js",
    "express js": "express.js",
    "expressjs": "express.js",

    # Backend frameworks
    "express": "express.js",
    "nestjs": "nest.js",
    "spring boot": "spring",
    "springboot": "spring",
    "fast api": "fastapi",

    # Databases
    "postgres": "postgresql",
    "mongo": "mongodb",
    "ms sql": "mssql",
    "ms-sql": "mssql",
    "sql server": "mssql",

    # Cloud & DevOps
    "amazon web services": "aws",
    "google cloud": "gcp",
    "google cloud platform": "gcp",
    "k8s": "kubernetes",
    "docker-compose": "docker compose",
    "github-action": "github actions",
    "github-actions": "github actions",
    "ci cd": "ci/cd",
    "cicd": "ci/cd",

    # Testing
    "unit testing": "unit tests",
    "integration testing": "integration tests",
    "e2e testing": "e2e tests",

    # API/Auth
    "oauth 2": "oauth2",
    "open api": "openapi",
    "open api 3": "openapi",
    "jwt tokens": "jwt",

    # Data/ML basics (developer-adjacent)
    "scikit learn": "scikit-learn",

    #------------HR------------------- 
    "recruiting": "talent acquisition",
    "hiring": "talent acquisition",
    "talent acquisition specialist": "talent acquisition",
    "human resources": "hr",
    "human resource": "hr",
    "hr generalist": "hr generalist",
    "on boarding": "onboarding",
    "people operations": "people ops",
    "people ops": "people ops",
    "employee relations": "employee relations",
    "payroll management": "payroll",
    "kpis": "kpi",
    "okrs": "okr",

    # Psychology / org behavior (common in HR resumes)
    "organizational behaviour": "organizational behavior",
    "industrial psychology": "industrial-organizational psychology",
    "i/o psychology": "industrial-organizational psychology",
    "io psychology": "industrial-organizational psychology",

    #------------Designers------------------- 
    # Design canon / variants
    "ui ux": "ui/ux",
    "ux ui": "ui/ux",
    "user interface": "ui",
    "user experience": "ux",
    "adobe ps": "adobe photoshop",
    "photoshop": "adobe photoshop",
    "illustrator": "adobe illustrator",
    "indesign": "adobe indesign",
    "after effects": "adobe after effects",
    "premiere pro": "adobe premiere",
    "adobe premiere pro": "adobe premiere",
    "xd": "adobe xd",
    "figma app": "figma",
    "proto pie": "protopie",
    "ux research": "user research",
    "wireframes": "wireframing",
    "prototypes": "prototyping",
    "design system": "design systems",

    #------------Data Scientist------------------- 
    # Data science canon / abbreviations
    "ml": "machine learning",
    "dl": "deep learning",
    "eda": "exploratory data analysis",
    "nlp": "natural language processing",
    "cv": "computer vision",
    "a/b testing": "ab testing",
    "ab-testing": "ab testing",
    "ab test": "ab testing",

    # Platforms/tech variants
    "aws s3": "s3",
    "aws ec2": "ec2",
    "gcs": "google cloud storage",
    "bigquery": "bigquery",
    "powerbi": "power bi",
    "microsoft excel": "ms excel",

    # Common libraries variations
    "sklearn": "scikit-learn",
    "scikit learn": "scikit-learn",
    "tf": "tensorflow",
    "torch": "pytorch",

    #------------Business / Marketing / Sales------------------- 
    # Marketing canon
    "search engine optimization": "seo",
    "seo optimization": "seo",
    "sem": "search engine marketing",
    "ppc": "pay per click",
    "google adwords": "google ads",
    "adwords": "google ads",
    "fb ads": "meta ads",
    "facebook ads": "meta ads",
    "instagram ads": "meta ads",
    "meta business suite": "meta ads",
    "ga": "google analytics",
    "ga4": "google analytics",
    "content strategy": "content marketing",

    # Sales/BD canon
    "business development executive": "business development",
    "bd": "business development",
    "bdr": "sales development",
    "sdr": "sales development",
    "lead gen": "lead generation",
    "customer relationship management": "crm",

    # CRM canon
    "salesforce crm": "salesforce",
    "hubspot crm": "hubspot",
    "zoho crm": "zoho crm",

    #------------Finance------------------- 
    # Finance canon
    "financial analysis": "finance analysis",
    "fp&a": "fp&a",
    "fpa": "fp&a",
    "financial planning and analysis": "fp&a",
    "management accounting": "management accounting",
    "costing": "cost accounting",
    "book keeping": "bookkeeping",
    "accounts payable": "accounts payable",
    "accounts receivable": "accounts receivable",
    "ar": "accounts receivable",
    "ap": "accounts payable",
    "p&l": "profit and loss",
    "pnl": "profit and loss",
    "ifrs standards": "ifrs",
    "gaap standards": "gaap",
    "vat": "vat",
    "gst": "gst",

    # ERP / accounting software
    "ms excel": "ms excel",
    "microsoft excel": "ms excel",
    "quick books": "quickbooks",
    "tally erp": "tally",
    "sap fico": "sap fico",
    "oracle financials": "oracle financials",
    "netsuite erp": "netsuite",

    #------------QA------------------- 
    # QA canon
    "sqa": "qa",
    "quality assurance": "qa",
    "quality analyst": "qa",
    "qa engineer": "qa",

    "test automation": "automation testing",
    "automated testing": "automation testing",
    "manual test": "manual testing",
    "manual tests": "manual testing",

    "api test": "api testing",
    "api tests": "api testing",

    "performance test": "performance testing",
    "load test": "performance testing",
    "stress test": "performance testing",

    "ui test": "ui testing",
    "e2e": "e2e testing",
    "end to end testing": "e2e testing",
    "end-to-end testing": "e2e testing",

    "bdd": "behavior driven development",
    "tdd": "test driven development",

    #------------Product------------------- 
    # Product canon
    "product management": "product management",
    "product manager": "product management",
    "product owner": "product owner",
    "po": "product owner",
    "ba": "business analysis",
    "business analyst": "business analysis",

    "user story": "user stories",
    "prd": "product requirements document",
    "prds": "product requirements document",
    "mvp": "minimum viable product",
    "kpi": "kpi",
    "okrs": "okr",

    # -------- Operations --------
    # Ops canon
    "operations management": "operations management",
    "business operations": "business operations",
    "ops management": "operations management",
    "standard operating procedures": "sops",
    "sop": "sops",
    "sops": "sops",
    "process improvement": "process optimization",
    "process improvements": "process optimization",
    "process optimisation": "process optimization",
    "kpi": "kpi",
    "okrs": "okr",
    "vendor mgmt": "vendor management",
    "procurement management": "procurement",
    "inventory mgmt": "inventory management",

}

# Multi-word phrases that should be captured as a single skill
PHRASES = [
    #------------Engineers------------------- 
    # FE core
    "web development",
    "frontend development",
    "responsive design",
    "cross browser compatibility",
    "single page application",
    "server side rendering",
    "static site generation",
    "state management",

    # FE frameworks/libs/tools
    "react native",
    "next.js",
    "node.js",
    "express.js",
    "vue.js",
    "nuxt.js",
    "tailwind css",
    "material-ui",
    "styled components",
    "chart.js",
    "three.js",

    # Backend / API
    "rest api",
    "restful api",
    "graphql api",
    "microservices",
    "event driven architecture",
    "message queue",
    "system design",
    "api gateway",

    # Auth / Security
    "role based access control",
    "oauth2",
    "json web token",
    "jwt",
    "security best practices",
    "rate limiting",

    # Databases / data layer
    "database design",
    "query optimization",
    "data modeling",

    # DevOps / Cloud
    "cloud computing",
    "infrastructure as code",
    "ci/cd",
    "containerization",
    "docker compose",
    "kubernetes",
    "blue green deployment",
    "canary deployment",
    "auto scaling",
    "load balancing",
    "observability",
    "log monitoring",

    # AWS common services
    "aws ec2",
    "aws s3",
    "aws lambda",
    "aws ecs",
    "aws eks",
    "aws ecr",
    "aws rds",
    "aws cloudfront",
    "aws route53",

    # Azure common services
    "azure devops",
    "azure functions",

    # GCP common services
    "google cloud storage",
    "cloud run",

    # Testing / QA for devs
    "test driven development",
    "tdd",
    "bdd",
    "unit tests",
    "integration tests",
    "e2e tests",
    "api testing",

    # Mobile (developer roles)
    "android development",
    "ios development",

    # Build/Tooling
    "version control",
    "package management",

    # Data/ML developer-adjacent
    "data analysis",
    "machine learning",
    "deep learning",
    "natural language processing",

    #------------HR------------------- 
    "human resources",
    "talent acquisition",
    "recruitment",
    "end to end recruitment",
    "full cycle recruitment",
    "candidate screening",
    "resume screening",
    "interview scheduling",
    "interviewing",
    "behavioral interviewing",
    "technical recruiting",
    "onboarding",
    "offboarding",
    "employee relations",
    "employee engagement",
    "performance management",
    "performance appraisal",
    "succession planning",
    "workforce planning",
    "training and development",
    "learning and development",
    "compensation and benefits",
    "salary benchmarking",
    "job analysis",
    "job description writing",
    "policy development",
    "hr policies",
    "hr operations",
    "hr compliance",
    "labor law",
    "employment law",
    "conflict resolution",
    "grievance handling",

    # HR Tools / ATS / HRIS
    "applicant tracking system",
    "ats",
    "hris",
    "workday",
    "bamboohr",
    "zoho recruit",
    "lever",
    "greenhouse",
    "successfactors",
    "oracle hcm",
    "adp",
    "gusto",

    # HR Analytics / Reporting
    "hr analytics",
    "data analysis",
    "ms excel",
    "advanced excel",
    "power bi",
    "reporting",
    "stakeholder management",

    # Psychology / Assessment
    "psychometric testing",
    "personality assessment",
    "organizational psychology",
    "industrial-organizational psychology",
    "organizational behavior",
    "employee wellbeing",

    #------------Designers------------------ 
    # UI/UX + Product Design
    "ui/ux",
    "user interface design",
    "user experience design",
    "interaction design",
    "information architecture",
    "user research",
    "usability testing",
    "heuristic evaluation",
    "wireframing",
    "prototyping",
    "low fidelity prototyping",
    "high fidelity prototyping",
    "design systems",
    "responsive design",
    "accessibility",
    "mobile app design",
    "web design",

    # Visual / Graphic Design
    "graphic design",
    "visual design",
    "branding",
    "brand identity",
    "logo design",
    "typography",
    "layout design",
    "print design",
    "illustration",
    "social media design",

    # Motion / Media
    "motion graphics",
    "video editing",
    "photo editing",
    "content creation",

    # Design tools
    "adobe photoshop",
    "adobe illustrator",
    "adobe indesign",
    "adobe after effects",
    "adobe premiere",
    "adobe xd",
    "figma",
    "sketch",
    "invision",
    "zeplin",
    "framer",
    "protopie",
    "canva",
    "coreldraw",
    "blender",

    #------------Data Scintist------------------ 
    # DS/ML concepts
    "machine learning",
    "deep learning",
    "supervised learning",
    "unsupervised learning",
    "reinforcement learning",
    "feature engineering",
    "model training",
    "model evaluation",
    "model deployment",
    "hyperparameter tuning",
    "cross validation",
    "data preprocessing",
    "data cleaning",
    "exploratory data analysis",
    "statistical analysis",
    "predictive modeling",
    "time series",
    "time series forecasting",
    "natural language processing",
    "computer vision",
    "information retrieval",
    "recommendation systems",
    "anomaly detection",
    "clustering",
    "classification",
    "regression",
    "dimensionality reduction",
    "ab testing",

    # Data engineering
    "etl pipeline",
    "data pipeline",
    "data warehousing",
    "data lake",
    "big data",
    "batch processing",
    "stream processing",

    # Visualization / reporting
    "data visualization",
    "dashboarding",
    "data storytelling",

    # Tools / platforms (multiword)
    "google analytics",
    "power bi",
    "ms excel",
    "google cloud storage",
    "google colab",
    "jupyter notebook",
    "aws lambda",
    "aws rds",

    #------------Business / Marketing / Sales------------------- 
    # -------- Marketing --------
    "digital marketing",
    "seo",
    "search engine marketing",
    "pay per click",
    "google ads",
    "meta ads",
    "google analytics",
    "email marketing",
    "content marketing",
    "social media marketing",
    "social media management",
    "keyword research",
    "link building",
    "guest posting",
    "guest post",
    "content writing",
    "copywriting",
    "marketing strategy",
    "campaign management",
    "conversion rate optimization",
    "cro",
    "marketing automation",
    "lead nurturing",
    "funnel optimization",
    "landing page optimization",
    "brand management",
    "community management",

    # -------- Sales / Business Development --------
    "business development",
    "sales development",
    "lead generation",
    "prospecting",
    "cold calling",
    "cold emailing",
    "sales pipeline",
    "pipeline management",
    "client acquisition",
    "account management",
    "relationship management",
    "customer success",
    "deal negotiation",
    "closing deals",
    "proposal writing",
    "sales forecasting",
    "market research",
    "competitive analysis",
    "product positioning",
    "b2b sales",
    "b2c sales",

    # -------- Tools / Platforms --------
    "crm",
    "salesforce",
    "hubspot",
    "zoho crm",
    "pipedrive",
    "mailchimp",
    "sendgrid",
    "google tag manager",
    "meta business suite",
    "linkedin sales navigator",
    "google search console",

    # -------- Finance --------
    "financial reporting",
    "financial statements",
    "profit and loss",
    "balance sheet",
    "cash flow statement",
    "general ledger",
    "journal entries",
    "bank reconciliation",
    "accounts payable",
    "accounts receivable",
    "payroll processing",
    "budgeting",
    "forecasting",
    "financial modeling",
    "variance analysis",
    "cost accounting",
    "management accounting",
    "taxation",
    "corporate tax",
    "sales tax",
    "vat",
    "gst",
    "audit",
    "internal audit",
    "external audit",
    "risk management",
    "compliance",
    "ifrs",
    "gaap",

    # -------- Finance in business context --------
    "fp&a",
    "financial planning",
    "working capital management",
    "cash flow management",
    "expense management",
    "revenue recognition",
    "month end closing",
    "year end closing",
    "financial controls",

    # -------- Tools / Systems --------
    "ms excel",
    "advanced excel",
    "power bi",
    "quickbooks",
    "xero",
    "tally",
    "sap",
    "sap fico",
    "oracle financials",
    "netsuite",
    "erp",

    # -------- QA --------
    # QA Core
    "quality assurance",
    "manual testing",
    "automation testing",
    "test planning",
    "test plan",
    "test strategy",
    "test cases",
    "test case design",
    "test execution",
    "bug tracking",
    "defect tracking",
    "regression testing",
    "smoke testing",
    "sanity testing",
    "functional testing",
    "non functional testing",
    "api testing",
    "ui testing",
    "e2e testing",
    "integration testing",
    "unit testing",
    "performance testing",
    "load testing",
    "stress testing",
    "security testing",
    "uat",
    "user acceptance testing",

    # QA Tools
    "selenium",
    "cypress",
    "playwright",
    "appium",
    "postman",
    "soapui",
    "jira",
    "test rail",
    "testrail",
    "zephyr",
    "allure report",
    "jmeter",
    "k6",
    "browserstack",
    "lambdatest",

    # QA Process
    "test driven development",
    "behavior driven development",
    "agile methodology",
    "scrum",

    # -------- Product / PM / PO / BA--------
    "product management",
    "product owner",
    "business analysis",
    "requirements gathering",
    "requirements analysis",
    "stakeholder management",
    "user stories",
    "acceptance criteria",
    "backlog grooming",
    "sprint planning",
    "scrum",
    "agile methodology",
    "kanban",
    "roadmap planning",
    "product roadmap",
    "product strategy",
    "prioritization",
    "market research",
    "competitive analysis",
    "customer research",
    "user research",
    "wireframing",
    "prototyping",
    "usability testing",
    "product requirements document",
    "prd",
    "minimum viable product",
    "mvp",
    "go to market",
    "gtm",
    "release planning",
    "feature planning",
    "product analytics",
    "event tracking",
    "funnel analysis",

    # -------- Operations --------
    # Operations / Ops
    "operations management",
    "business operations",
    "operations planning",
    "service delivery",
    "customer operations",
    "process optimization",
    "process improvement",
    "workflow optimization",
    "workflow assessment",
    "sops",
    "standard operating procedures",
    "policy implementation",
    "compliance",
    "risk management",
    "quality management",
    "quality control",
    "internal controls",
    "audit coordination",
    "vendor management",
    "procurement",
    "stakeholder management",
    "resource planning",
    "capacity planning",
    "inventory management",
    "logistics management",
    "project coordination",
    "cross-functional collaboration",
    "reporting",
    "data analysis",
    "dashboarding",
    "ms excel",
    "power bi",
    "cost reduction",
    "continuous improvement",
]

# Domain tagging: if a resume contains these skills, it belongs to the domain
DOMAIN_KEYWORDS = {
     "engineering": {
        # Languages
        "python","java","javascript","typescript","go","c++","c#",".net","php","ruby","swift","kotlin",
        # FE/BE frameworks
        "react","next.js","node.js","express.js","vue.js","nuxt.js","angular","django","flask","fastapi",
        "spring","laravel","rails","asp.net",
        # Web basics
        "html","css","sass","tailwind css",
        # APIs
        "rest api","graphql api","microservices",
        # Tooling
        "git","github","gitlab",
        # DB
        "sql","mysql","postgresql","mongodb","redis","mssql",
    },
    "devops": {
        "docker","docker compose","kubernetes","terraform","ansible","jenkins","github actions","ci/cd",
        "aws","azure","gcp","ec2","s3","lambda","ecs","eks","ecr","rds","cloudfront","route53",
        "nginx","apache","linux","bash",
        "prometheus","grafana","elk","opensearch",
    },
    "qa": {
        "selenium","cypress","playwright","postman","jira",
        "api testing","unit tests","integration tests","e2e tests",
        "test driven development","tdd","bdd",
    },
    "data": {
        "sql","python","pandas","numpy","scikit-learn","tensorflow","pytorch",
        "data analysis","machine learning","deep learning","natural language processing",
    },
    "hr": {
    # HR concepts
    "hr","human resources","talent acquisition","recruitment","candidate screening",
    "onboarding","offboarding","employee relations","employee engagement",
    "performance management","training and development","learning and development",
    "compensation and benefits","workforce planning","succession planning",
    "hr operations","hr compliance","labor law","employment law",
    "job analysis","job description writing","policy development",

    # HR systems/tools
    "ats","applicant tracking system","hris","workday","bamboohr","zoho recruit",
    "lever","greenhouse","successfactors","oracle hcm","adp","gusto",

    # Analytics tools commonly used by HR
    "ms excel","power bi",
    },
    "design": {
    # concepts
    "ui/ux","ui","ux","interaction design","information architecture","user research",
    "usability testing","heuristic evaluation","wireframing","prototyping","design systems",
    "accessibility","responsive design","mobile app design","web design",
    "graphic design","visual design","branding","brand identity","logo design","typography",
    "layout design","print design","illustration","social media design",
    "motion graphics","video editing","photo editing","content creation",

    # tools
    "figma","sketch","invision","zeplin","framer","protopie",
    "adobe photoshop","adobe illustrator","adobe indesign","adobe after effects","adobe premiere","adobe xd",
    "canva","coreldraw","blender",
    },
    "data": {
    # Concepts
    "machine learning","deep learning","feature engineering","model evaluation",
    "hyperparameter tuning","exploratory data analysis","statistical analysis",
    "data preprocessing","data cleaning","time series","ab testing",
    "natural language processing","computer vision",

    # Languages & query
    "python","r","sql",

    # Core libs
    "numpy","pandas","scikit-learn",

    # DL libs
    "tensorflow","pytorch",

    # Data engineering tools
    "spark","hadoop","airflow","kafka",
    "etl pipeline","data pipeline","data warehousing",

    # Cloud common
    "aws","gcp","azure","s3","ec2","lambda","bigquery",

    # Viz
    "data visualization","power bi","ms excel",
    },
    "marketing": {
    "digital marketing","seo","search engine marketing","pay per click",
    "google ads","meta ads","google analytics",
    "email marketing","content marketing","social media marketing","social media management",
    "keyword research","link building","guest posting",
    "conversion rate optimization","marketing automation",
    "google tag manager","google search console","meta business suite",
    "mailchimp","sendgrid",
    },

    "sales_bd": {
        "business development","sales development","lead generation","prospecting",
        "cold calling","cold emailing","sales pipeline","pipeline management",
        "account management","customer success","deal negotiation",
        "proposal writing","sales forecasting","market research","competitive analysis",
        "crm","salesforce","hubspot","zoho crm","pipedrive","linkedin sales navigator",
        "b2b sales","b2c sales",
    },
    "finance": {
    # Concepts
    "financial reporting","financial statements","profit and loss","balance sheet","cash flow statement",
    "general ledger","journal entries","bank reconciliation",
    "accounts payable","accounts receivable",
    "budgeting","forecasting","financial modeling","variance analysis",
    "cost accounting","management accounting",
    "taxation","corporate tax","vat","gst",
    "audit","internal audit","external audit",
    "risk management","compliance","ifrs","gaap",
    "fp&a","month end closing","year end closing","financial controls",

    # Tools / ERP
    "ms excel","power bi",
    "quickbooks","xero","tally",
    "sap","sap fico","oracle financials","netsuite","erp",
    },
    "qa": {
    # Concepts
    "qa","quality assurance","manual testing","automation testing","test planning",
    "test cases","regression testing","smoke testing","sanity testing",
    "functional testing","api testing","ui testing","e2e testing",
    "performance testing","load testing","stress testing","security testing","uat",

    # Tools
    "selenium","cypress","playwright","appium",
    "postman","soapui",
    "jira","testrail","test rail","zephyr","allure report",
    "jmeter","k6","browserstack","lambdatest",

    # Dev-adjacent
    "git","ci/cd",
    },
    "product": {
    "product management","product owner","business analysis",
    "requirements gathering","requirements analysis",
    "stakeholder management","user stories","acceptance criteria",
    "backlog grooming","sprint planning",
    "scrum","agile methodology","kanban",
    "product roadmap","roadmap planning","product strategy","prioritization",
    "market research","competitive analysis","customer research","user research",
    "product requirements document","prd","minimum viable product","mvp",
    "go to market","gtm","release planning","feature planning",
    "usability testing","wireframing","prototyping",
    "product analytics","event tracking","funnel analysis",
    },
    "operations": {
    "operations management","business operations","operations planning",
    "service delivery","customer operations",
    "process optimization","workflow optimization","workflow assessment",
    "sops","standard operating procedures",
    "compliance","risk management","quality management","quality control",
    "internal controls","audit coordination",
    "vendor management","procurement","inventory management","logistics management",
    "resource planning","capacity planning",
    "project coordination","cross-functional collaboration",
    "reporting","dashboarding","data analysis",
    "ms excel","power bi",
    "cost reduction","continuous improvement",
    }

}
