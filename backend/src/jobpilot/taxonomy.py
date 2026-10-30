"""The skill tree the app starts with, designed by the user. It is the only structure: readings
never add to it or rearrange it; they only say which of its skills a posting asks for, and
anything else waits in Unsorted until the user places it. A node is a skill, which postings ask for
("Machine learning" as much as "YOLO") and which can hold other skills, or a [group], which only
organizes ("Cloud") and is never asked for itself. A node counts the postings that ask for it or
for anything under it. The user changes the tree on the Skill Gap page; this text is only where it
starts.

Two spaces of indent are one level deeper; [brackets] mark a group."""

TREE = """
[Technologies]
  [Programming languages]
    Python
      pandas
      NumPy
      scikit-learn
      PyTorch
      TensorFlow
    SQL
    R
    Java
    C++
  Machine learning
    [Classical ML]
      Regression
      Classification
      Clustering
      Tree-based models
      Time series
      Recommender systems
    Deep learning
      Computer vision
        Object detection
          YOLO
        Image segmentation
          U-Net
        Image classification
          ResNet
      NLP
        Named entity recognition
        Text classification
        Language models
          BERT
    Generative AI
      LLMs
      RAG
      Prompt engineering
      Fine-tuning
    [ML workflow]
      Feature engineering
      Model training
      Model evaluation
  [Data & analytics]
    Statistics
      A/B testing
    Exploratory data analysis
    Data preprocessing
    Data mining
    Data visualization
      Power BI
      Tableau
  [Databases]
    Relational (SQL)
      PostgreSQL
      MySQL
    NoSQL
      MongoDB
    Vector databases
  [Data engineering]
    ETL
    Apache Spark
    Airflow
  [Cloud]
    AWS
    Azure
    Google Cloud
  [MLOps & DevOps]
    MLOps
    Model deployment
    Monitoring
    Docker
    Kubernetes
    Git
    CI/CD
  [Software engineering]
    APIs
    Data structures and algorithms
    System design
    Software testing
[Domain knowledge]
  Pharmaceuticals
  Finance
[Background]
  [Experience]
    Professional experience
  [Education]
    Bachelor's degree
    Master's degree
    PhD
  [Spoken languages]
    English
    Turkish
[Soft skills]
  Communication
  Problem solving
  Analytical thinking
  Stakeholder management
  Teamwork
"""

OVERALL_EXPERIENCE = "Professional experience"


def nodes(text: str = TREE):
    """Yields (name, parent name or None, position among its siblings, is a group) in order."""
    path: list[str] = []
    counts: dict[str | None, int] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        depth = (len(line) - len(line.lstrip(" "))) // 2
        del path[depth:]
        parent = path[-1] if path else None
        position = counts.get(parent, 0)
        counts[parent] = position + 1
        name = line.strip()
        group = name.startswith("[") and name.endswith("]")
        name = name.strip("[]")
        yield name, parent, position, group
        path.append(name)
