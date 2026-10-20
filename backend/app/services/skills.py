# Skill list with aliases ("ReactJS" = "React") and matching of JD skills against a resume
from __future__ import annotations

import re
from functools import lru_cache

# canonical name -> aliases (case-insensitive unless prefixed with "cs:")
SKILL_TAXONOMY: dict[str, list[str]] = {
    "Python": ["python", "python3", "py"],
    "Java": ["java", "core java", "java 8", "java 11", "java 17"],
    "JavaScript": ["javascript", "js", "ecmascript", "es6", "vanilla js"],
    "TypeScript": ["typescript", "ts"],
    "C": ["cs:C", "c language", "c programming"],
    "C++": ["c++", "cpp"],
    "C#": ["c#", "csharp", "c sharp"],
    "Go": ["golang", "cs:Go", "go lang"],
    "Rust": ["rust"],
    "Kotlin": ["kotlin"],
    "Swift": ["swift"],
    "PHP": ["php"],
    "Ruby": ["ruby"],
    "R": ["cs:R", "r programming", "r language"],
    "Scala": ["scala"],
    "Dart": ["dart"],
    "MATLAB": ["matlab"],
    "Bash": ["bash", "shell scripting", "shell script", "unix shell"],
    "SQL": ["sql", "t-sql", "pl/sql", "plsql", "structured query language"],
    "HTML": ["html", "html5"],
    "CSS": ["css", "css3"],
    "React": ["cs:React", "reactjs", "react.js", "react js"],
    "Next.js": ["next.js", "nextjs", "next js"],
    "Angular": ["angular", "angularjs", "angular.js"],
    "Vue.js": ["vue", "vue.js", "vuejs"],
    "Svelte": ["svelte", "sveltekit"],
    "Redux": ["redux", "redux toolkit", "rtk"],
    "Tailwind CSS": ["tailwind", "tailwindcss", "tailwind css"],
    "Bootstrap": ["bootstrap"],
    "Sass": ["sass", "scss"],
    "jQuery": ["jquery"],
    "Webpack": ["webpack"],
    "Vite": ["vite"],
    "Material UI": ["material ui", "material-ui", "mui"],
    "Responsive Design": ["responsive design", "responsive web design", "mobile-first"],
    "Web Accessibility": ["web accessibility", "accessibility", "wcag", "a11y", "aria"],
    "Figma": ["figma"],
    "Adobe XD": ["adobe xd"],
    "Node.js": ["node.js", "nodejs", "node js", "cs:Node"],
    "Express.js": ["cs:Express", "express.js", "expressjs"],
    "Django": ["django", "django rest framework", "drf"],
    "Flask": ["flask"],
    "FastAPI": ["fastapi", "fast api"],
    "Spring Boot": ["spring boot", "springboot", "spring framework", "spring mvc"],
    "Hibernate": ["hibernate", "jpa"],
    ".NET": [".net", "dotnet", "asp.net", ".net core"],
    "Laravel": ["laravel"],
    "Ruby on Rails": ["rails", "ruby on rails"],
    "NestJS": ["nestjs", "nest.js"],
    "REST APIs": ["rest api", "rest framework", "api development", "web apis", "rest apis", "restful", "restful api", "restful apis", "rest services"],
    "GraphQL": ["graphql"],
    "gRPC": ["grpc"],
    "Microservices": ["microservices", "microservice", "micro-services", "microservice architecture"],
    "WebSockets": ["websocket", "websockets", "socket.io"],
    "Celery": ["celery"],
    "OAuth/JWT": ["oauth", "oauth2", "jwt", "json web token"],
    "System Design": ["system design", "distributed systems", "scalable systems"],
    "PostgreSQL": ["postgresql", "postgres", "psql"],
    "MySQL": ["mysql", "mariadb"],
    "SQLite": ["sqlite"],
    "Oracle DB": ["oracle database", "oracle db", "cs:Oracle"],
    "SQL Server": ["sql server", "mssql", "ms sql"],
    "MongoDB": ["mongodb", "mongo", "mongoose"],
    "Redis": ["redis"],
    "Cassandra": ["cassandra"],
    "DynamoDB": ["dynamodb"],
    "Elasticsearch": ["elasticsearch", "elastic search", "opensearch"],
    "Firebase": ["firebase", "firestore"],
    "AWS": ["aws", "amazon web services", "ec2", "aws s3", "aws lambda"],
    "Azure": ["azure", "microsoft azure"],
    "GCP": ["gcp", "google cloud", "google cloud platform"],
    "Docker": ["docker", "dockerfile", "docker compose", "docker-compose", "containerization"],
    "Kubernetes": ["kubernetes", "k8s", "eks", "aks", "gke"],
    "Terraform": ["terraform"],
    "Ansible": ["ansible"],
    "Jenkins": ["jenkins"],
    "GitHub Actions": ["github actions"],
    "CI/CD": ["ci/cd", "ci cd", "cicd", "continuous integration", "continuous deployment",
              "continuous delivery"],
    "Linux": ["linux", "ubuntu", "unix"],
    "Nginx": ["nginx"],
    "Git": ["git", "github", "gitlab", "bitbucket", "version control"],
    "Kafka": ["kafka", "apache kafka"],
    "RabbitMQ": ["rabbitmq"],
    "Prometheus": ["prometheus", "grafana"],
    "Machine Learning": ["machine learning", "ml", "ml models", "predictive modeling", "predictive modelling"],
    "Deep Learning": ["deep learning", "neural networks", "neural network", "cnn", "rnn", "lstm"],
    "NLP": ["nlp", "natural language processing", "text classification", "named entity recognition"],
    "Computer Vision": ["computer vision", "opencv", "image classification", "object detection", "yolo"],
    "Generative AI": ["generative ai", "genai", "gen ai"],
    "LLMs": ["llm", "llms", "large language model", "large language models", "gpt", "gemini api",
             "openai api", "prompt engineering"],
    "RAG": ["rag", "retrieval augmented generation", "retrieval-augmented generation"],
    "LangChain": ["langchain", "langgraph", "llamaindex", "llama index"],
    "Vector Databases": ["vector database", "vector databases", "faiss", "pinecone", "chromadb",
                         "chroma", "weaviate", "pgvector", "qdrant"],
    "Hugging Face": ["hugging face", "huggingface", "transformers library"],
    "TensorFlow": ["tensorflow", "keras", "tf2"],
    "PyTorch": ["pytorch", "torch"],
    "scikit-learn": ["scikit-learn", "sklearn", "scikit learn"],
    "pandas": ["pandas"],
    "NumPy": ["numpy"],
    "Matplotlib": ["matplotlib", "seaborn", "plotly"],
    "Statistics": ["statistics", "statistical analysis", "hypothesis testing", "a/b testing",
                   "probability", "regression analysis"],
    "Data Analysis": ["data analysis", "data analytics", "exploratory data analysis", "eda"],
    "Data Visualization": ["data visualization", "data visualisation", "dashboards", "dashboarding"],
    "Feature Engineering": ["feature engineering"],
    "XGBoost": ["xgboost", "lightgbm", "catboost"],
    "MLOps": ["mlops", "mlflow", "kubeflow", "model deployment", "model serving"],
    "Spark": ["spark", "pyspark", "apache spark"],
    "Hadoop": ["hadoop", "hive", "hdfs"],
    "Airflow": ["airflow", "apache airflow"],
    "ETL": ["etl", "elt", "data pipelines", "data pipeline"],
    "Tableau": ["tableau"],
    "Power BI": ["power bi", "powerbi"],
    "Excel": ["cs:Excel", "ms excel", "microsoft excel", "advanced excel", "vlookup", "pivot tables"],
    "Jupyter": ["jupyter", "jupyter notebook", "google colab", "colab"],
    "AWS SageMaker": ["sagemaker", "aws sagemaker"],
    "Android": ["android", "android studio"],
    "iOS": ["ios", "xcode"],
    "React Native": ["react native", "react-native"],
    "Flutter": ["flutter"],
    "Unit Testing": ["unit testing", "unit tests", "tdd", "test driven development"],
    "pytest": ["pytest", "unittest"],
    "Jest": ["jest", "react testing library", "vitest"],
    "Cypress": ["cypress", "playwright"],
    "Selenium": ["selenium", "selenium webdriver"],
    "JUnit": ["junit", "testng", "mockito"],
    "Postman": ["postman", "api testing"],
    "Agile": ["agile", "scrum", "kanban", "sprint"],
    "Jira": ["jira", "confluence"],
    "Data Structures & Algorithms": ["data structures", "algorithms", "dsa", "data structures and algorithms"],
    "OOP": ["oop", "object oriented programming", "object-oriented programming", "oops"],
    "Design Patterns": ["design patterns", "solid principles"],
    "UI/UX Design": ["ui/ux", "ux design", "ui design", "user experience", "user research",
                     "wireframing", "prototyping", "usability testing"],
    "SEO": ["seo", "search engine optimization", "search engine optimisation"],
    "Digital Marketing": ["digital marketing", "google ads", "social media marketing",
                          "email marketing", "content marketing"],
    "Leadership": ["team lead", "led a team", "leadership", "mentored", "mentoring"],
    "Communication": ["communication skills", "stakeholder management", "presentation skills"],
}

# Skills in the same family give 50% credit for each other.
SKILL_FAMILIES: dict[str, set[str]] = {
    "relational_db": {"PostgreSQL", "MySQL", "SQLite", "Oracle DB", "SQL Server"},
    "nosql_db": {"MongoDB", "Cassandra", "DynamoDB", "Redis", "Firebase"},
    "python_web": {"Django", "Flask", "FastAPI"},
    "js_backend": {"Node.js", "Express.js", "NestJS"},
    "frontend_fw": {"React", "Angular", "Vue.js", "Svelte", "Next.js"},
    "css_fw": {"Tailwind CSS", "Bootstrap", "Material UI", "Sass"},
    "cloud": {"AWS", "Azure", "GCP"},
    "dl_fw": {"TensorFlow", "PyTorch"},
    "containers": {"Docker", "Kubernetes"},
    "ci": {"CI/CD", "Jenkins", "GitHub Actions"},
    "queues": {"Kafka", "RabbitMQ", "Celery"},
    "bi": {"Tableau", "Power BI"},
    "js_test": {"Jest", "Cypress"},
    "mobile_xp": {"React Native", "Flutter"},
    "llm_stack": {"LLMs", "RAG", "LangChain", "Generative AI", "Hugging Face", "Vector Databases"},
    "java_web": {"Spring Boot", "Hibernate"},
    "design_tools": {"Figma", "Adobe XD", "UI/UX Design"},
    "typed_js": {"JavaScript", "TypeScript"},
}

# Using one skill implies knowing another (Django -> Python, MySQL -> SQL ...).
SKILL_IMPLIES: dict[str, list[str]] = {
    "Django": ["Python"], "Flask": ["Python"], "FastAPI": ["Python"], "pandas": ["Python"],
    "NumPy": ["Python"], "scikit-learn": ["Python", "Machine Learning"],
    "TensorFlow": ["Deep Learning", "Machine Learning"], "PyTorch": ["Deep Learning", "Machine Learning"],
    "Deep Learning": ["Machine Learning"], "XGBoost": ["Machine Learning"],
    "MySQL": ["SQL"], "PostgreSQL": ["SQL"], "SQLite": ["SQL"], "SQL Server": ["SQL"], "Oracle DB": ["SQL"],
    "Next.js": ["React"], "Redux": ["React"], "Express.js": ["Node.js"], "NestJS": ["Node.js", "TypeScript"],
    "Node.js": ["JavaScript"], "React": ["JavaScript"], "TypeScript": ["JavaScript"],
    "Spring Boot": ["Java"], "Hibernate": ["Java"], "Kubernetes": ["Docker"],
    "LangChain": ["LLMs"], "RAG": ["LLMs"], "Hugging Face": ["NLP"], "GitHub Actions": ["CI/CD"],
    "Jenkins": ["CI/CD"], "AWS SageMaker": ["AWS", "MLOps"],
}

_FAMILY_OF: dict[str, set[str]] = {}
for _members in SKILL_FAMILIES.values():
    for _m in _members:
        _FAMILY_OF.setdefault(_m, set()).update(_members - {_m})

_BOUNDARY_L = r"(?<![A-Za-z0-9+#])"
_BOUNDARY_R = r"(?![A-Za-z0-9+#&]|\.[A-Za-z])"


def _alias_pattern(alias: str) -> re.Pattern:
    case_sensitive = alias.startswith("cs:")
    text = alias[3:] if case_sensitive else alias
    body = re.escape(text).replace(r"\ ", r"[\s\-]?")
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(_BOUNDARY_L + body + _BOUNDARY_R, flags)


@lru_cache(maxsize=1)
def _compiled() -> list[tuple[str, re.Pattern]]:
    out = []
    for canonical, aliases in SKILL_TAXONOMY.items():
        for alias in set(aliases):
            out.append((canonical, _alias_pattern(alias)))
    return out


@lru_cache(maxsize=1)
def _alias_index() -> dict[str, str]:
    idx: dict[str, str] = {}
    for canonical, aliases in SKILL_TAXONOMY.items():
        idx[_key(canonical)] = canonical
        for a in aliases:
            idx[_key(a[3:] if a.startswith("cs:") else a)] = canonical
    return idx


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9+#/]", "", s.lower())


def normalize_skill(name: str) -> str:
    name = (name or "").strip().strip(".,;:")
    if not name:
        return ""
    hit = _alias_index().get(_key(name))
    if hit:
        return hit
    head = re.split(r"[(\[]", name)[0].strip()
    if head and head != name:
        hit = _alias_index().get(_key(head))
        if hit:
            return hit
    return name[:60]


def find_skill_spans(text: str) -> list[tuple[int, int, str]]:
    spans = [(m.start(), m.end(), canonical) for canonical, pat in _compiled() for m in pat.finditer(text or "")]
    spans.sort(key=lambda t: (t[0], -(t[1] - t[0])))
    out: list[tuple[int, int, str]] = []
    for s, e, c in spans:
        if out and s < out[-1][1]:
            continue
        out.append((s, e, c))
    return out


def extract_skills(text: str, implied: bool = True) -> list[str]:
    found = {canonical for canonical, pat in _compiled() if pat.search(text or "")}
    if not implied:
        return sorted(found, key=str.lower)
    frontier = list(found)
    while frontier:
        for implied in SKILL_IMPLIES.get(frontier.pop(), []):
            if implied not in found:
                found.add(implied)
                frontier.append(implied)
    return sorted(found, key=str.lower)


def skill_in_text(skill: str, text: str, resume_skills: set[str]) -> bool:
    canonical = normalize_skill(skill)
    if canonical in resume_skills:
        return True
    if canonical in SKILL_TAXONOMY:
        return False
    words = [w for w in re.split(r"\W+", skill.lower()) if len(w) > 2]
    if not words:
        return False
    return all(re.search(r"\b" + re.escape(w), text, re.IGNORECASE) for w in words)


_ALT_SPLIT = re.compile(r"\s+or\s+|\s+/\s+|\s*\|\s*", re.I)


def split_alternatives(skill: str) -> tuple[str, ...]:
    parts = [normalize_skill(p) for p in _ALT_SPLIT.split(skill or "") if p.strip()]
    return tuple(dict.fromkeys(p for p in parts if p))


def match_skills(resume_text: str, resume_skills: list[str],
                 must_have: list[str], nice_to_have: list[str]) -> dict:
    # K = (2 * must credit + nice credit) / (2m + n); exact match = 1, related skill = 0.5
    have = set(resume_skills)

    def score_list(skills: list[str]):
        matched, partial, missing, credit = [], [], [], 0.0
        for alts in dict.fromkeys(split_alternatives(s) for s in skills if s):
            if not alts:
                continue
            label = " or ".join(alts)
            hit = next((a for a in alts if skill_in_text(a, resume_text, have)), None)
            if hit:
                matched.append(label if len(alts) == 1 else f"{hit} (for {label})")
                credit += 1.0
                continue
            related = sorted({r for a in alts for r in _FAMILY_OF.get(a, set())} & have)
            if related:
                partial.append({"skill": label, "via": related[:3]})
                credit += 0.5
            else:
                missing.append(label)
        return matched, partial, missing, credit

    mm, mp, mx, mc = score_list(must_have)
    nm, np_, nx, nc = score_list(nice_to_have)
    m = len(mm) + len(mp) + len(mx)
    n = len(nm) + len(np_) + len(nx)
    denom = 2 * m + n
    coverage = (2 * mc + nc) / denom if denom else 0.5
    must_cov = mc / m if m else 1.0
    return {
        "matched_must": mm, "partial_must": mp, "missing_must": mx,
        "matched_nice": nm, "partial_nice": np_, "missing_nice": nx,
        "coverage": round(coverage, 4), "must_coverage": round(must_cov, 4),
        "extra_skills": sorted(have - {base_skill(x) for x in mm + nm}, key=str.lower)[:25],
    }


def base_skill(label: str) -> str:
    return label.split(" (for ")[0]


def canonical_text(text: str) -> str:
    skills = extract_skills(text)
    tokens = " ".join(re.sub(r"[^A-Za-z0-9]+", "_", s) for s in skills)
    return f"{text}\n{tokens}"
