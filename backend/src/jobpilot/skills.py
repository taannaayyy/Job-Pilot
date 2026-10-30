"""The skill dictionary: finds known skills in a job description and gives each one a single name,
so "pytorch", "PyTorch" and "Torch" count as one skill. Works without any AI model; the model
(see ai.py) only adds what a dictionary can't know."""

import re
from dataclasses import dataclass

from jobpilot import taxonomy
from jobpilot.linkedin import fold
from jobpilot.models import Importance

# (name, aliases). The names match the tree's (taxonomy.py) where the tree has the skill; others
# wait in Unsorted. Aliases match case-insensitively as whole words; "=X" matches case-sensitively (for names that are also ordinary
# words: "React", "Spark"); "re:..." is a regular expression. When an entry has such an alias, its
# name is only found through them.
_ENTRIES: list[tuple[str, tuple[str, ...]]] = [
    # Programming languages
    ("Python", ("python3",)),
    ("SQL", ()),
    ("Java", ()),
    ("JavaScript", ("js", "ecmascript")),
    ("TypeScript", ()),
    ("C++", ("cpp",)),
    ("C#", ("csharp", "c sharp")),
    ("C", ("=C",)),
    ("Go", ("golang", r"re:\bGo\b(?=\s*(?:,|/|\)|and\b|or\b|$))")),
    ("Rust", ()),
    ("R", (r"re:(?<![\w&/.-])R(?![\w&+#'-])",)),
    ("Scala", ()),
    ("Kotlin", ()),
    ("Swift", ("=Swift",)),
    ("Julia", ()),
    ("MATLAB", ()),
    ("Bash", ("shell scripting",)),
    ("CUDA", ()),
    ("PHP", ()),
    ("Ruby", ()),
    # Libraries and frameworks (filed under their language)
    ("PyTorch", ("torch",)),
    ("TensorFlow", ()),
    ("Keras", ()),
    ("JAX", ()),
    ("scikit-learn", ("sklearn", "scikit learn")),
    ("Hugging Face", ("huggingface", "hugging face transformers", "hf transformers")),
    ("XGBoost", ()),
    ("LightGBM", ()),
    ("CatBoost", ()),
    ("pandas", ()),
    ("NumPy", ()),
    ("SciPy", ()),
    ("Polars", ()),
    ("OpenCV", ()),
    ("spaCy", ()),
    ("NLTK", ()),
    ("LangChain", ()),
    ("LangGraph", ()),
    ("LlamaIndex", ("llama index", "llama-index")),
    ("vLLM", ()),
    ("ONNX", ()),
    ("TensorRT", ()),
    ("Apache Spark", ("=Spark", "pyspark", "apache spark")),
    ("Dask", ()),
    ("Ray", ("=Ray",)),
    ("FastAPI", ()),
    ("Flask", ()),
    ("Django", ()),
    ("Streamlit", ()),
    ("React", ("=React", "react.js", "reactjs")),
    ("Node.js", ("nodejs", "node.js")),
    ("Spring", (r"re:\bSpring\b(?!\s+(?:\d|semester|term|internship))", "spring boot")),
    (".NET", ("dotnet",)),
    ("Matplotlib", ()),
    ("Plotly", ()),
    # Tools and platforms
    ("Docker", ("containers", "containerization")),
    ("Kubernetes", ("k8s",)),
    ("Git", ("github", "gitlab")),
    ("Linux", ("unix",)),
    ("Airflow", ("apache airflow",)),
    ("Kafka", ("apache kafka",)),
    ("dbt", ()),
    ("MLflow", ()),
    ("Weights & Biases", ("wandb", "w&b")),
    ("Kubeflow", ()),
    ("Terraform", ()),
    ("CI/CD", ("ci / cd", "continuous integration", "continuous delivery", "continuous deployment")),
    ("Jenkins", ()),
    ("GitHub Actions", ()),
    ("Tableau", ()),
    ("Power BI", ("powerbi",)),
    ("Looker", ()),
    ("Excel", ("=Excel", "ms excel", "microsoft excel")),
    ("Jupyter", ("jupyter notebooks",)),
    ("Databricks", ()),
    ("Prometheus", ()),
    ("Grafana", ()),
    ("APIs", ("restful", "rest api", "rest apis", "restful apis", "api design", "api development")),
    ("gRPC", ()),
    ("GraphQL", ()),
    # Cloud
    ("AWS", ("amazon web services",)),
    ("Amazon SageMaker", ("sagemaker",)),
    ("Google Cloud", ("gcp", "google cloud platform")),
    ("Vertex AI", ()),
    ("BigQuery", ()),
    ("Azure", ("microsoft azure",)),
    ("Azure ML", ("azure machine learning",)),
    # Databases
    ("PostgreSQL", ("postgres",)),
    ("MySQL", ()),
    ("MongoDB", ("mongo",)),
    ("Redis", ()),
    ("Elasticsearch", ("elastic search", "opensearch")),
    ("Relational (SQL)", ("relational databases", "relational database", "rdbms")),
    ("NoSQL", ()),
    ("Cassandra", ()),
    ("Snowflake", ()),
    ("Vector databases", ("vector database", "vector db", "vector dbs", "vector stores", "vector store")),
    ("Pinecone", ()),
    ("Weaviate", ()),
    ("Milvus", ()),
    ("Qdrant", ()),
    ("Chroma", ("=Chroma", "chromadb")),
    ("pgvector", ()),
    ("FAISS", ()),
    # Machine learning
    ("Machine learning", ("ml", "artificial intelligence")),
    ("Classical ML", ("classical machine learning", "traditional machine learning", "classical ml",
                               "traditional ml", "classic ml")),
    ("Regression", (r"re:(?i:\b(?:linear |logistic )?regression\b(?!\s+test))",)),
    ("Classification", (r"re:(?i:(?<!image )(?<!text )\bclassification\b)",)),
    ("Clustering", ()),
    ("Tree-based models", ("tree based models", "decision trees", "decision tree", "random forest",
                                        "random forests", "gradient boosting", "gradient boosted trees")),
    ("Feature engineering", ()),
    ("Model training", ("training models", "train models")),
    ("Model evaluation", ("evaluation frameworks", "evals", "llm evaluation")),
    ("Recommender systems", ("recommendation systems", "recommender system", "recommendation engine", "recsys")),
    ("Reinforcement learning", ("rl", "rlhf")),
    ("Time series", ("time-series", "forecasting")),
    # Deep learning
    ("Deep learning", ("dl",)),
    ("Neural networks", ("neural network",)),
    ("CNNs", ("cnn", "convolutional neural networks", "convolutional neural network")),
    ("RNNs", ("rnn", "lstm", "lstms", "recurrent neural networks")),
    ("Transformers", ("transformer", "transformer architectures", "attention mechanism")),
    ("Diffusion models", ("diffusion model", "stable diffusion")),
    ("Distributed training", ("multi-gpu", "gpu training")),
    # Computer vision
    ("Computer vision", ()),
    ("Object detection", ("detection models",)),
    ("Image segmentation", ("semantic segmentation", "instance segmentation",
                                         r"re:(?i:(?<!customer )(?<!market )(?<!user )\bsegmentation\b)")),
    ("Image classification", ()),
    ("Object tracking", ("multi-object tracking",)),
    ("Pose estimation", ()),
    ("OCR", ("optical character recognition",)),
    ("YOLO", (r"re:\bYOLO(?:v?\d+)?\b", r"re:(?i:\byolov\d+\b)")),
    ("U-Net", ("unet",)),
    ("ResNet", ()),
    ("Vision transformers", ("vision transformer", "vit")),
    # NLP and LLMs
    ("NLP", ("natural language processing",)),
    ("Named entity recognition", ("ner",)),
    ("Sentiment analysis", ()),
    ("Text classification", ()),
    ("Machine translation", ()),
    ("Embeddings", ("embedding", "semantic search", "vector search")),
    ("Language models", (r"re:(?i:(?<!large )(?<!large-)\blanguage models?\b)",)),
    ("BERT", ("roberta",)),
    ("Speech recognition", ("asr", "speech-to-text")),
    ("Generative AI", ("genai", "generative ai", "gen ai")),
    ("LLMs", ("llm", "large language models", "large language model")),
    ("RAG", ("retrieval-augmented generation", "retrieval augmented generation")),
    ("Fine-tuning", ("fine tuning", "finetuning", "fine-tune", "fine tune", "lora", "peft", "qlora")),
    ("Prompt engineering", ("prompting",)),
    ("AI agents", ("agentic", "llm agents", "agent frameworks", "multi-agent", "tool calling", "function calling")),
    ("GPT", ("gpt-4", "gpt-4o", "chatgpt")),
    ("Llama", ("llama 2", "llama 3")),
    # Data and statistics
    ("Statistics", ("statistical", "statistical modeling", "statistical modelling")),
    ("Probability", ()),
    ("Linear algebra", ()),
    ("Optimization", ("optimisation",)),
    ("A/B testing", ("ab testing", "a/b tests", "experimentation", "a/b test")),
    ("Hypothesis testing", ()),
    ("Causal inference", ()),
    ("Exploratory data analysis", ("=EDA", "exploratory analysis")),
    ("Data preprocessing", ("data cleaning", "data preparation", "preprocessing")),
    ("Data mining", ()),
    ("Data visualization", ("data visualisation", "dashboards")),
    ("ETL", ("elt", "data pipelines", "data pipeline")),
    ("Data warehousing", ("data warehouse", "data lake", "lakehouse")),
    # Software engineering
    ("Distributed systems", ("distributed computing",)),
    ("Microservices", ("microservice",)),
    ("System design", ("software architecture",)),
    ("Data structures and algorithms", ("data structures", "algorithms and data structures")),
    ("Object-oriented programming", ("oop", "object oriented")),
    ("Software testing", ("unit testing", "unit tests", "integration tests", "automated testing", "test-driven development", "tdd")),
    ("Agile", ("scrum", "kanban")),
    ("Code review", ("code reviews",)),
    # MLOps
    ("MLOps", ("ml ops", "llmops")),
    ("Model deployment", ("model serving", "deploy models", "deploying models", "productionizing", "model inference")),
    ("Monitoring", ("observability", "model monitoring")),
    # Domains
    ("Pharmaceuticals", ("pharmaceutical", "pharma", "pharmaceutical industry")),
    # Track record
    ("Research publications", ("publications", "published papers", "peer-reviewed", "neurips", "icml", "acl", "cvpr", "iclr")),
    ("Open-source contributions", ("open source contributions", "contributions to open source", "open-source projects", "open source projects")),
    # Soft skills
    ("Communication", (
        r"re:(?i)communication skills|communicator|(?:strong|excellent|good|clear|effective|written and verbal|verbal and written) communication|communicat\w* (?:clearly|effectively)",
    )),
    ("Teamwork", ("team player", "collaboration skills", "teamwork skills")),
    ("Problem solving", ("problem-solving",)),
    ("Mentoring", ("mentor", "mentoring others")),
    ("Stakeholder management", ("managing stakeholders", "stakeholder communication")),
]

# Never what years of experience are about: "5+ years, strong communication" is overall experience.
_NO_YEARS = {"Research publications", "Open-source contributions", "Communication", "Teamwork", "Problem solving", "Mentoring", "Stakeholder management"}
DEGREES = ("PhD", "Master's degree", "Bachelor's degree")


@dataclass(frozen=True)
class Found:
    name: str
    importance: Importance
    evidence: str
    min_years: int | None = None
    max_years: int | None = None
    detail: str | None = None  # degrees: the fields of study


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


_BY_KEY: dict[str, str] = {}
_PATTERNS: list[tuple[re.Pattern, str]] = []
for _name, _aliases in _ENTRIES:
    for _alias in (_name, *_aliases):
        if not _alias.startswith(("re:", "=")):
            _BY_KEY.setdefault(skill_key(_alias), _name)
    special = [a for a in _aliases if a.startswith(("re:", "="))]
    plain = [a for a in (*(() if special else (_name,)), *_aliases) if not a.startswith(("re:", "="))]
    # Longest first, so "hugging face transformers" wins over "transformers" on the same words.
    alts = sorted(plain, key=len, reverse=True)
    _PATTERNS.append((re.compile("|".join([*(_alias_pattern(a) for a in alts), *(_alias_pattern(a) for a in special)])), _name))


def lookup(name: str) -> str | None:
    """The dictionary's name for a name or alias, or None."""
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
            item.name,
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
        for pattern, name in _PATTERNS:
            if not field_list and pattern.search(line):
                named.append(name)
        # "3+ years of Python and SQL": the years are about Python and SQL. Without a skill
        # named next to them, they are overall experience.
        about = [n for n in named if n not in _NO_YEARS]
        for name in named:
            y = span if span and name in about else None
            add(Found(name, importance, evidence, y and y[0], y and y[1]))
        if span and not about and not degrees:
            add(Found(taxonomy.OVERALL_EXPERIENCE, importance, evidence, span[0], span[1]))
        # "BSc or MSc": the lower degree is what's required, a higher one is a plus.
        alternatives = len(degrees) > 1 and re.search(r"\bor\b|/|veya|ya da", line, re.IGNORECASE)
        fields = degree_fields(line) if degrees else None
        for name in degrees:
            lowest = name == degrees[-1]  # _EDUCATION is ordered highest first
            add(Found(name, importance if lowest or not alternatives else Importance.NICE, evidence, detail=fields))
        for name, pattern in _SPOKEN.items():
            if pattern.search(line) and (_SPOKEN_CONTEXT.search(line) or len(line.split()) <= 3):
                add(Found(name, importance, evidence))
    return list(found.values())
