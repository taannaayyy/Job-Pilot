"""The skill dictionary: finds known skills in a job description and gives each one a single name,
so "pytorch", "PyTorch" and "Torch" count as one skill. Works without any AI model; the model
(see ai.py) only adds what a dictionary can't know."""

import re
from dataclasses import dataclass

from jobpilot import taxonomy
from jobpilot.linkedin import fold
from jobpilot.models import Importance

# (name, category, aliases). Aliases match case-insensitively as whole words; "=X" matches
# case-sensitively (for names that are also ordinary words: "React", "Spark"); "re:..." is a
# regular expression. When an entry has such an alias, its name is only found through them.
_ENTRIES: list[tuple[str, str, tuple[str, ...]]] = [
    # Programming languages
    ("Python", "language", ("python3",)),
    ("SQL", "language", ()),
    ("Java", "language", ()),
    ("JavaScript", "language", ("js", "ecmascript")),
    ("TypeScript", "language", ()),
    ("C++", "language", ("cpp",)),
    ("C#", "language", ("csharp", "c sharp")),
    ("C", "language", ("=C",)),
    ("Go", "language", ("golang", r"re:\bGo\b(?=\s*(?:,|/|\)|and\b|or\b|$))")),
    ("Rust", "language", ()),
    ("R", "language", (r"re:(?<![\w&/.-])R(?![\w&+#'-])",)),
    ("Scala", "language", ()),
    ("Kotlin", "language", ()),
    ("Swift", "language", ("=Swift",)),
    ("Julia", "language", ()),
    ("MATLAB", "language", ()),
    ("Bash", "language", ("shell scripting",)),
    ("CUDA", "language", ()),
    ("PHP", "language", ()),
    ("Ruby", "language", ()),
    # ML and data frameworks and libraries
    ("PyTorch", "framework", ("torch",)),
    ("TensorFlow", "framework", ()),
    ("Keras", "framework", ()),
    ("JAX", "framework", ()),
    ("scikit-learn", "framework", ("sklearn", "scikit learn")),
    ("Hugging Face", "framework", ("huggingface", "hugging face transformers", "hf transformers")),
    ("XGBoost", "framework", ()),
    ("LightGBM", "framework", ()),
    ("CatBoost", "framework", ()),
    ("pandas", "framework", ()),
    ("NumPy", "framework", ()),
    ("SciPy", "framework", ()),
    ("Polars", "framework", ()),
    ("OpenCV", "framework", ()),
    ("spaCy", "framework", ()),
    ("NLTK", "framework", ()),
    ("LangChain", "framework", ()),
    ("LangGraph", "framework", ()),
    ("LlamaIndex", "framework", ("llama index", "llama-index")),
    ("vLLM", "framework", ()),
    ("ONNX", "framework", ()),
    ("TensorRT", "framework", ()),
    ("Apache Spark", "framework", ("=Spark", "pyspark", "apache spark")),
    ("Dask", "framework", ()),
    ("Ray", "framework", ("=Ray",)),
    ("FastAPI", "framework", ()),
    ("Flask", "framework", ()),
    ("Django", "framework", ()),
    ("Streamlit", "framework", ()),
    ("React", "framework", ("=React", "react.js", "reactjs")),
    ("Node.js", "framework", ("nodejs", "node.js")),
    ("Spring", "framework", (r"re:\bSpring\b(?!\s+(?:\d|semester|term|internship))", "spring boot")),
    (".NET", "framework", ("dotnet",)),
    ("Matplotlib", "framework", ()),
    ("Plotly", "framework", ()),
    # Tools and platforms
    ("Docker", "tool", ("containers", "containerization")),
    ("Kubernetes", "tool", ("k8s",)),
    ("Git", "tool", ("github", "gitlab")),
    ("Linux", "tool", ("unix",)),
    ("Airflow", "tool", ("apache airflow",)),
    ("Kafka", "tool", ("apache kafka",)),
    ("dbt", "tool", ()),
    ("MLflow", "tool", ()),
    ("Weights & Biases", "tool", ("wandb", "w&b")),
    ("Kubeflow", "tool", ()),
    ("Terraform", "tool", ()),
    ("CI/CD", "practice", ("ci / cd", "continuous integration", "continuous delivery", "continuous deployment")),
    ("Jenkins", "tool", ()),
    ("GitHub Actions", "tool", ()),
    ("Tableau", "tool", ()),
    ("Power BI", "tool", ("powerbi",)),
    ("Looker", "tool", ()),
    ("Excel", "tool", ("=Excel", "ms excel", "microsoft excel")),
    ("Jupyter", "tool", ("jupyter notebooks",)),
    ("Databricks", "tool", ()),
    ("Snowflake", "database", ()),
    ("Prometheus", "tool", ()),
    ("Grafana", "tool", ()),
    ("REST APIs", "concept", ("restful", "rest api", "rest apis", "restful apis")),
    ("gRPC", "tool", ()),
    ("GraphQL", "tool", ()),
    # Cloud
    ("AWS", "cloud", ("amazon web services",)),
    ("Amazon SageMaker", "cloud", ("sagemaker",)),
    ("Google Cloud", "cloud", ("gcp", "google cloud platform")),
    ("Vertex AI", "cloud", ()),
    ("BigQuery", "database", ()),
    ("Azure", "cloud", ("microsoft azure",)),
    ("Azure ML", "cloud", ("azure machine learning",)),
    # Databases
    ("PostgreSQL", "database", ("postgres",)),
    ("MySQL", "database", ()),
    ("MongoDB", "database", ("mongo",)),
    ("Redis", "database", ()),
    ("Elasticsearch", "database", ("elastic search", "opensearch")),
    ("NoSQL", "database", ()),
    ("Cassandra", "database", ()),
    ("Vector databases", "database", ("vector database", "vector db", "vector dbs", "vector stores", "vector store")),
    ("Pinecone", "database", ()),
    ("Weaviate", "database", ()),
    ("Milvus", "database", ()),
    ("Qdrant", "database", ()),
    ("Chroma", "database", ("=Chroma", "chromadb")),
    ("pgvector", "database", ()),
    ("FAISS", "database", ()),
    # Concepts
    ("Machine learning", "concept", ("ml",)),
    ("Deep learning", "concept", ("dl",)),
    ("NLP", "concept", ("natural language processing",)),
    ("Computer vision", "concept", ()),
    ("LLMs", "concept", ("llm", "large language models", "large language model", "genai", "generative ai", "gen ai")),
    ("RAG", "concept", ("retrieval-augmented generation", "retrieval augmented generation")),
    ("Transformers", "concept", ("transformer", "transformer architectures", "attention mechanism")),
    ("Fine-tuning", "concept", ("fine tuning", "finetuning", "fine-tune", "fine tune", "lora", "peft", "qlora")),
    ("Prompt engineering", "concept", ("prompting",)),
    ("AI agents", "concept", ("agentic", "llm agents", "ai agents", "agent frameworks", "multi-agent", "tool calling", "function calling")),
    ("Embeddings", "concept", ("embedding", "semantic search", "vector search")),
    ("Recommender systems", "concept", ("recommendation systems", "recommender system", "recommendation engine", "recsys")),
    ("Reinforcement learning", "concept", ("rl", "rlhf")),
    ("Time series", "concept", ("time-series", "forecasting")),
    ("Statistics", "concept", ("statistical", "statistical modeling", "statistical modelling")),
    ("Probability", "concept", ()),
    ("Linear algebra", "concept", ()),
    ("Optimization", "concept", ("optimisation",)),
    ("A/B testing", "practice", ("ab testing", "a/b tests", "experimentation", "a/b test")),
    ("Causal inference", "concept", ()),
    ("Feature engineering", "concept", ()),
    ("Data visualization", "concept", ("data visualisation", "dashboards")),
    ("ETL", "concept", ("elt", "data pipelines", "data pipeline")),
    ("Data warehousing", "concept", ("data warehouse", "data lake", "lakehouse")),
    ("Distributed systems", "concept", ("distributed computing",)),
    ("Distributed training", "concept", ("multi-gpu", "gpu training")),
    ("Microservices", "concept", ("microservice",)),
    ("System design", "concept", ("software architecture",)),
    ("Data structures and algorithms", "concept", ("data structures", "algorithms and data structures")),
    ("Object-oriented programming", "concept", ("oop", "object oriented")),
    ("Speech recognition", "concept", ("asr", "speech-to-text")),
    ("Model evaluation", "practice", ("evaluation frameworks", "evals", "llm evaluation", "model evaluation")),
    ("Model deployment", "practice", ("model serving", "deploy models", "deploying models", "productionizing", "model inference")),
    ("Monitoring", "practice", ("observability", "model monitoring")),
    # Practices
    ("MLOps", "practice", ("ml ops", "llmops")),
    ("Software testing", "practice", ("unit testing", "unit tests", "integration tests", "automated testing", "test-driven development", "tdd")),
    ("Agile", "practice", ("scrum", "kanban")),
    ("Code review", "practice", ("code reviews",)),
    ("Research publications", "practice", ("publications", "published papers", "peer-reviewed", "neurips", "icml", "acl", "cvpr", "iclr")),
    ("Open-source contributions", "practice", ("open source contributions", "contributions to open source", "open-source projects", "open source projects")),
    # Soft skills
    ("Communication", "soft_skill", (
        r"re:(?i)communication skills|communicator|(?:strong|excellent|good|clear|effective|written and verbal|verbal and written) communication|communicat\w* (?:clearly|effectively)",
    )),
    ("Teamwork", "soft_skill", ("team player", "collaboration skills", "teamwork skills")),
    ("Problem solving", "soft_skill", ("problem-solving",)),
    ("Mentoring", "soft_skill", ("mentor", "mentoring others")),
    ("Stakeholder management", "soft_skill", ("managing stakeholders", "stakeholder communication")),
]

# Where each entry goes in the tree (taxonomy.py): by its kind above, unless named here.
_GROUP_BY_KIND = {
    "language": "tech.languages", "framework": "tech.libraries", "tool": "tech.mlops", "cloud": "tech.cloud",
    "database": "tech.databases", "concept": "know.ml", "practice": "know.swe", "soft_skill": "soft",
}
_GROUP_BY_NAME = {
    "SQL": "tech.databases", "Apache Spark": "tech.data_eng", "Dask": "tech.data_eng", "Ray": "tech.data_eng",
    "Docker": "tech.cloud", "Kubernetes": "tech.cloud", "Terraform": "tech.cloud", "Linux": "tech.cloud",
    "Airflow": "tech.data_eng", "Kafka": "tech.data_eng", "dbt": "tech.data_eng", "Databricks": "tech.data_eng",
    "Snowflake": "tech.databases", "BigQuery": "tech.databases",
    "Tableau": "tech.bi", "Power BI": "tech.bi", "Looker": "tech.bi", "Excel": "tech.bi",
    "gRPC": "know.swe", "GraphQL": "know.swe", "REST APIs": "know.swe",
    "Deep learning": "know.dl", "NLP": "know.dl", "Computer vision": "know.dl", "Transformers": "know.dl",
    "Speech recognition": "know.dl", "Distributed training": "know.dl",
    "LLMs": "know.genai", "RAG": "know.genai", "Fine-tuning": "know.genai", "Prompt engineering": "know.genai",
    "AI agents": "know.genai", "Embeddings": "know.genai",
    "Statistics": "know.data", "Probability": "know.data", "Linear algebra": "know.data", "A/B testing": "know.data",
    "Causal inference": "know.data", "Data visualization": "know.data",
    "ETL": "tech.data_eng", "Data warehousing": "tech.data_eng",
    "Distributed systems": "know.swe", "Microservices": "know.swe", "System design": "know.swe",
    "Data structures and algorithms": "know.swe", "Object-oriented programming": "know.swe",
    "Model evaluation": "know.ml", "Model deployment": "tech.mlops", "Monitoring": "tech.mlops", "MLOps": "tech.mlops",
    "CI/CD": "tech.mlops", "Research publications": "experience", "Open-source contributions": "experience",
    "ONNX": "tech.mlops", "TensorRT": "tech.mlops",
}
# What a skill belongs to: libraries to their language, cloud services to their cloud.
PARENTS = {
    **{lib: "Python" for lib in (
        "PyTorch", "TensorFlow", "Keras", "JAX", "scikit-learn", "Hugging Face", "XGBoost", "LightGBM", "CatBoost",
        "pandas", "NumPy", "SciPy", "Polars", "OpenCV", "spaCy", "NLTK", "LangChain", "LangGraph", "LlamaIndex",
        "vLLM", "FastAPI", "Flask", "Django", "Streamlit", "Matplotlib", "Plotly",
    )},
    "React": "JavaScript", "Node.js": "JavaScript", "Spring": "Java", ".NET": "C#",
    "Amazon SageMaker": "AWS", "Vertex AI": "Google Cloud", "Azure ML": "Azure", "BigQuery": "Google Cloud",
    **{db: "Vector databases" for db in ("Pinecone", "Weaviate", "Milvus", "Qdrant", "Chroma", "pgvector", "FAISS")},
}


def group_of(name: str, kind: str) -> str:
    return _GROUP_BY_NAME.get(name) or _GROUP_BY_KIND.get(kind, kind)


@dataclass(frozen=True)
class Found:
    name: str
    group: str  # a tree key from taxonomy.py
    importance: Importance
    evidence: str
    min_years: int | None = None
    max_years: int | None = None
    detail: str | None = None  # degrees: the fields of study

    @property
    def parent(self) -> str | None:
        return PARENTS.get(self.name)


def skill_key(name: str) -> str:
    """'PyTorch', ' pytorch ' -> 'pytorch'. Keeps + and # so C++ and C# stay apart from C."""
    text = fold(name).replace("&", " and ")
    text = re.sub(r"[^\w+#./ -]", " ", text)
    return re.sub(r"[\s_-]+", " ", text).strip(" .")


def _alias_pattern(alias: str) -> str:
    if alias.startswith("re:"):
        return alias[3:]
    if alias.startswith("="):
        word = re.escape(alias[1:])
        # "React" in a list, but not "React to feedback" opening a sentence.
        return rf"(?:(?<!^)(?<![\w+#.]){word}(?![\w+#'-])|^{word}(?![\w+#'-])(?!\s+[a-z]))"
    words = r"[\s-]+".join(re.escape(w) for w in alias.split())
    return rf"(?i:(?<![\w+#]){words}(?![\w+#]|\.\w))"


_BY_KEY: dict[str, tuple[str, str]] = {}
_PATTERNS: list[tuple[re.Pattern, str, str]] = []
for _name, _kind, _aliases in _ENTRIES:
    _category = group_of(_name, _kind)
    for _alias in (_name, *_aliases):
        if not _alias.startswith(("re:", "=")):
            _BY_KEY.setdefault(skill_key(_alias), (_name, _category))
    special = [a for a in _aliases if a.startswith(("re:", "="))]
    plain = [a for a in (*(() if special else (_name,)), *_aliases) if not a.startswith(("re:", "="))]
    # Longest first, so "hugging face transformers" wins over "transformers" on the same words.
    alts = sorted(plain, key=len, reverse=True)
    _PATTERNS.append((re.compile("|".join([*(_alias_pattern(a) for a in alts), *(_alias_pattern(a) for a in special)])), _name, _category))


def lookup(name: str) -> tuple[str, str] | None:
    """The dictionary's name and tree group key for a name or alias, or None."""
    return _BY_KEY.get(skill_key(name))


# Section headings and phrases that mark a requirement as nice to have.
_NICE = re.compile(
    r"nice[\s-]to[\s-]have|good[\s-]to[\s-]have|\bpreferred\b|\bpreferably\b|\bbonus\b|\ba plus\b|is a plus|are a plus|"
    r"\bplus\b(?=\s*[:.)]|\s*$)|\badvantage(?:ous)?\b|\bdesirable\b|\boptional\b|\bideally\b|avantaj|tercih",
    re.IGNORECASE,
)
# Headings start with these words: "Requirements", "What you'll do:", "Nice to have".
_NICE_HEADING = re.compile(
    r"(?:nice|good)[\s-]to[\s-]have|preferred|bonus|pluses|plus\b|desirable|optional|ideally|"
    r"tercih(?: sebebi| edilen)?|avantaj",
    re.IGNORECASE,
)
_MUST_HEADING = re.compile(
    r"requirements|(?:minimum |basic |required )?qualifications|must[\s-]have|what you(?:'ll| will)? (?:bring|need|have|do)|"
    r"you have|who you are|we(?:'re| are) looking for|(?:key )?responsibilities|about the (?:job|role)|the role|your role|"
    r"(?:required |technical )?skills|(?:key )?duties|tasks|aranan nitelikler|gereksinimler|sorumluluklar|iş tanımı",
    re.IGNORECASE,
)
# Sections that describe the company, not the role.
_SKIP_HEADING = re.compile(
    r"(?:what )?we offer|benefits|perks|why (?:join|us|work)|about (?:us|the company)|our (?:culture|values|mission)|"
    r"equal opportunity|sunduklarımız|yan haklar|hakkımızda",
    re.IGNORECASE,
)


# "We offer mentorship and a training budget" is about the company, wherever it appears.
_OFFER = re.compile(r"(?:we|you(?:'ll| will)?)\s+(?:offer|provide|get|enjoy|receive)\b", re.IGNORECASE)


def _heading(line: str) -> re.Pattern | None:
    """Which heading pattern a line is: a short line that starts with one ("Requirements"), or a
    sentence that introduces a list ("The requirements for the successful candidate are;",
    "It would be a plus if you have:")."""
    words = len(line.split())
    if line.endswith((":", ";")) and words <= 14 and ":" not in line[:-1]:
        text = line[:-1].strip()
        for pattern in (_SKIP_HEADING, _NICE_HEADING, _MUST_HEADING):
            if pattern.search(text):
                return pattern
        return None
    if words > 5 or line.endswith((".", ",")) or ":" in line:
        return None
    for pattern in (_SKIP_HEADING, _NICE_HEADING, _MUST_HEADING):
        if pattern.match(line):
            return pattern
    return None


def _sections(text: str):
    """Yields (clause, importance) for every part of the description that is about the role."""
    section: Importance | None = Importance.MUST
    for raw in text.splitlines():
        line = raw.strip().lstrip("-•*·▪◦–— ").strip()
        if not line:
            continue
        heading = _heading(line)
        if heading is not None:
            section = {_SKIP_HEADING: None, _NICE_HEADING: Importance.NICE, _MUST_HEADING: Importance.MUST}[heading]
            continue
        if section is None or _OFFER.match(line):
            continue
        # "BSc in CS; MSc is a plus": each part has its own importance.
        for clause in re.split(r";|\.\s+(?=[A-Z])", line):
            if clause.strip():
                nice = section == Importance.NICE or _NICE.search(clause)
                yield clause.strip(), Importance.NICE if nice else Importance.MUST


_YEARS = re.compile(
    r"(?:(?:at least|minimum|min\.?|over|more than|en az)\s+)?(?<![\d.])(\d{1,2})\s*(?:\+|or more|plus)?\s*"
    r"(?:(?:-|to|–)\s*(\d{1,2})\s*\+?\s*)?(?:years?|yrs?|yıl)",
    re.IGNORECASE,
)


def years(text: str) -> tuple[int, int | None] | None:
    """'3-5 years' -> (3, 5), '2+ years' -> (2, None); None when there are no years."""
    m = _YEARS.search(text)
    if not m:
        return None
    low, high = int(m.group(1)), int(m.group(2)) if m.group(2) else None
    if not 0 < low <= 20 or (high is not None and high < low):
        return None
    return low, high


# "BSc in a quantitative field such as Computer Engineering, Mathematics, or related disciplines"
_DEGREE_FIELDS = re.compile(
    r"\b(?:in|on)\s+(?:a\s+|an\s+)?(?:quantitative|relevant|related|technical|stem|similar)?\s*"
    r"(?:fields?|disciplines?|areas?|subjects?)?\s*(?:such as|like|e\.g\.|including|\(|:)?\s*(.+)",
    re.IGNORECASE,
)


def degree_fields(clause: str) -> str | None:
    m = _DEGREE_FIELDS.search(clause)
    if not m:
        return None
    fields = re.split(r",?\s+or\s+(?:a\s+|an\s+|other\s+)?(?:related|equivalent|similar)|\)|;", m.group(1), flags=re.IGNORECASE)[0]
    fields = fields.strip(" ,.")
    return fields[:300] or None
_EDUCATION = [
    ("PhD", re.compile(r"\bph\.?\s?d\b|doctorate|doktora", re.IGNORECASE)),
    ("Master's degree", re.compile(r"\bm\.?sc?\b\.?(?!\w)|master'?s(?! data)|yüksek lisans|\bms degree", re.IGNORECASE)),
    ("Bachelor's degree", re.compile(r"\bb\.?sc?\b\.?(?!\w)|bachelor|(?<!yüksek )lisans\b|\bbs degree|university degree|undergraduate", re.IGNORECASE)),
]
_FIELDS = re.compile(r"\b(?:field|fields|discipline|disciplines|major|degree|department|bölüm)\b", re.IGNORECASE)
_SPOKEN = {
    "English": re.compile(r"\benglish\b|ingilizce", re.IGNORECASE),
    "Turkish": re.compile(r"\bturkish\b|türkçe", re.IGNORECASE),
    "German": re.compile(r"\bgerman\b|almanca", re.IGNORECASE),
    "French": re.compile(r"\bfrench\b|fransızca", re.IGNORECASE),
    "Spanish": re.compile(r"\bspanish\b", re.IGNORECASE),
    "Arabic": re.compile(r"\barabic\b", re.IGNORECASE),
}
# "Fluent English", "Turkish is a plus"; not "a model for Turkish and English".
_SPOKEN_CONTEXT = re.compile(
    r"fluen|proficien|native|speak|spoken|written|verbal|command of|language skills|level|"
    r"is a plus|\bplus\b|preferred|required|iyi derecede|bilen|dil",
    re.IGNORECASE,
)


def find(text: str | None) -> list[Found]:
    """Every known skill, years of experience, degree and language the description asks for.
    A skill found in several places keeps its strongest importance (must over nice)."""
    found: dict[str, Found] = {}

    def add(item: Found) -> None:
        current = found.get(item.name)
        if current is None:
            found[item.name] = item
            return
        stronger = current.importance == Importance.NICE and item.importance == Importance.MUST
        found[item.name] = Found(
            item.name, item.group,
            Importance.MUST if stronger or current.importance == Importance.MUST else Importance.NICE,
            item.evidence if stronger else current.evidence,
            current.min_years if current.min_years is not None else item.min_years,
            current.max_years if current.min_years is not None else item.max_years,
            current.detail or item.detail,
        )

    for line, importance in _sections(text or ""):
        evidence = line[:300]
        degrees = [name for name, pattern in _EDUCATION if pattern.search(line)]
        # "BSc in Mathematics, Statistics or a related field" lists fields of study, not skills.
        field_list = degrees and _FIELDS.search(line)
        span = years(line)
        named = []
        for pattern, name, category in _PATTERNS:
            if not field_list and pattern.search(line):
                named.append((name, category))
        # "3+ years of Python and SQL": the years are about Python and SQL. Without a skill
        # named next to them, they are overall experience.
        about = [n for n in named if n[1] not in ("soft", "experience")]
        for name, category in named:
            y = span if span and (name, category) in about else None
            add(Found(name, category, importance, evidence, y and y[0], y and y[1]))
        if span and not about and not degrees:
            add(Found(taxonomy.OVERALL_EXPERIENCE, "experience", importance, evidence, span[0], span[1]))
        # "BSc or MSc": the lower degree is what's required, a higher one is a plus.
        alternatives = len(degrees) > 1 and re.search(r"\bor\b|/|veya|ya da", line, re.IGNORECASE)
        fields = degree_fields(line) if degrees else None
        for name in degrees:
            lowest = name == degrees[-1]  # _EDUCATION is ordered highest first
            add(Found(name, "education", importance if lowest or not alternatives else Importance.NICE, evidence, detail=fields))
        for name, pattern in _SPOKEN.items():
            if pattern.search(line) and (_SPOKEN_CONTEXT.search(line) or len(line.split()) <= 3):
                add(Found(name, "spoken", importance, evidence))
    return list(found.values())
