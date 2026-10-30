"""The tree requirements are filed in. This is the starting tree; the user can rename, move, add
and delete groups in the app. Groups made from this list keep their key, so the dictionary
(skills.py) can still find "its" group after the user renames it."""

# (key, name, description shown to the model, children)
DEFAULT_TREE: list[tuple[str, str, str, list]] = [
    ("tech", "Technologies", "Things a candidate uses.", [
        ("tech.languages", "Programming languages", "Python, R, Java, C++, Go, Scala, JavaScript", []),
        ("tech.libraries", "Libraries & frameworks",
         "pandas, NumPy, scikit-learn, PyTorch, TensorFlow, Hugging Face, LangChain, FastAPI, React. "
         "Give the programming language they belong to as parent.", []),
        ("tech.databases", "Databases & SQL",
         "SQL, PostgreSQL, MySQL, MongoDB, Redis, vector databases (Pinecone, pgvector), warehouses (Snowflake, BigQuery)", []),
        ("tech.cloud", "Cloud & infrastructure",
         "AWS, Azure, Google Cloud and their services (parent: the cloud), Docker, Kubernetes, Terraform, Linux", []),
        ("tech.data_eng", "Data engineering", "Spark, Airflow, Kafka, dbt, Databricks, ETL, data pipelines, data warehousing", []),
        ("tech.mlops", "MLOps & dev tools", "MLflow, Weights & Biases, Git, CI/CD, model deployment, model monitoring, MLOps", []),
        ("tech.bi", "BI & visualization tools", "Tableau, Power BI, Looker, Excel", []),
    ]),
    ("know", "Knowledge areas", "Things a candidate knows how to do.", [
        ("know.ml", "Machine learning",
         "Machine learning, regression, classification, clustering, tree-based models, feature engineering, "
         "model training, model evaluation, time series, recommender systems, reinforcement learning", []),
        ("know.dl", "Deep learning", "Deep learning, NLP, computer vision, transformers, speech, distributed training", []),
        ("know.genai", "Generative AI", "LLMs, RAG, fine-tuning, prompt engineering, AI agents, embeddings", []),
        ("know.data", "Data analysis & statistics",
         "Statistics, probability, exploratory data analysis, A/B testing, data mining, data preprocessing, data visualization", []),
        ("know.swe", "Software engineering",
         "System design, APIs, testing, microservices, algorithms and data structures, object-oriented programming, agile", []),
        ("know.domain", "Domain knowledge", "Knowledge of an industry or business area: pharmaceuticals, finance, e-commerce", []),
    ]),
    ("experience", "Experience",
     "Overall years of professional experience, and track record such as publications or open-source work. "
     "Years with a specific technology belong on that technology, not here.", []),
    ("education", "Education", "Degrees: Bachelor's, Master's, PhD.", []),
    ("spoken", "Spoken languages", "English, Turkish, German...", []),
    ("soft", "Soft skills", "Communication, analytical thinking, problem solving, teamwork, stakeholder management", []),
]

# Kept apart in the gap list unless the user shows them (they rarely tell you what to learn next).
HIDDEN_BY_DEFAULT = ("soft",)
OVERALL_EXPERIENCE = "Professional experience"


def flatten(tree=DEFAULT_TREE, parent: str | None = None):
    """Yields (key, name, description, parent_key, position) in order."""
    for position, (key, name, description, children) in enumerate(tree):
        yield key, name, description, parent, position
        yield from flatten(children, key)
