"""Role/qualification evidence extraction with documented conservative fallback rules."""

from dataclasses import dataclass
import html
import re

# Fixed feature vocabulary; weights remain exclusively in validated configuration.
SKILLS = {
    "python": r"\bpython\b", "pytorch": r"\bpytorch\b", "mujoco": r"\bmujoco\b",
    "lerobot": r"\blerobot\b", "act": r"(?-i:\bACT\b)|action chunking transformer",
    "imitation_learning": r"imitation learning|behavio[ur]+ cloning",
    "manipulation": r"(?:robot|robotic|learned) manipulation|manipulation polic",
    "model_training": r"train(?:ing|ed)?[^.\n]{0,45}(?:models?|polic|networks?)|fine[- ]tun|training runs|training loops",
    "evaluation": r"evaluat(?:ion|e|ing)|benchmark|failure modes",
    "research_experiments": r"(?:research|training|controlled) experiments?|hyperparameter|ablation",
    "data_workflows": r"data (?:pipeline|processing|curation|workflow)|dataset|training data|train/val/test",
    "linux": r"\blinux\b", "git": r"\bgit\b", "multimodal": r"multimodal|multi-modal",
    "sensor_fusion": r"sensor fusion|fus(?:e|ing|ion)[^.\n]{0,45}(?:sensor|signal)|acoustic APG|gyroscope",
    "cross_attention": r"cross[- ]attention", "bilstm": r"bi[- ]?lstm|bidirectional lstm",
    "cpp": r"c\+\+", "c": r"(?-i:\bC\b)(?![a-zA-Z+#])", "java": r"\bjava\b",
    "sql": r"\bsql\b", "tensorflow": r"\btensorflow\b", "jax": r"\bjax\b",
    "numpy": r"\bnumpy\b", "pandas": r"\bpandas\b", "sklearn": r"scikit[- ]learn",
    "transformers": r"hugging face|\btransformers\b", "cuda": r"\bcuda\b",
    "ros": r"\bros(?:[ /]?2)?\b|robot operating system",
    "isaac": r"\bisaac(?: sim| lab)?\b", "gazebo": r"\bgazebo\b",
    "unity": r"\bunity\b", "unreal": r"\bunreal\b", "docker": r"\bdocker\b",
    "cloud": r"cloud (?:gpu|infrastructure)|\baws\b|\bazure\b|\bgcp\b",
    "distributed": r"distributed (?:train|system|comput)",
    "reinforcement_learning": r"reinforcement learning|(?-i:\bRL\b)",
    "real_robot": r"real[- ]robot|physical (?:robot|hardware)|on-machine|hardware deployment",
    "production": r"production (?:robot|system|deployment|experience)|deploy[^.\n]{0,25}production",
    "diffusion": r"diffusion|flow matching|\bVAEs?\b", "vla": r"vision[- ]language[- ]action|\bVLA\b",
    "vlm": r"vision[- ]language model|\bVLM\b", "llm": r"large language model|\bLLM\b",
    "world_models": r"world model|world modeling|\bcosmos\b",
    "slam": r"\bslam\b|state estimation|learned mapping", "graphics": r"neural rendering|3d reconstruction|computer graphics",
    "planning": r"motion planning|task planning|behavior trees|locomotion|path planning",
    "hardware_design": r"circuit|pcb|cad|mechanical design|electrical design|oscilloscope|solder",
    "web": r"javascript|react|angular|frontend|front-end|api development",
    "matlab": r"\bmatlab\b", "go": r"\bgolang\b|(?-i:\bGo\b)", "kotlin": r"\bkotlin\b",
}
LABELS = {key: key.replace("_", " ") for key in SKILLS}
LABELS.update(python="Python", pytorch="PyTorch", mujoco="MuJoCo", lerobot="LeRobot", act="ACT",
              cpp="C++", c="C", ros="ROS/ROS 2", sql="SQL", vla="VLA models", vlm="VLM models",
              llm="LLM models", jax="JAX", real_robot="physical robot deployment", production="production systems")
LANGUAGES = {"python", "cpp", "c", "java", "sql", "go", "kotlin"}
FRAMEWORKS = {"pytorch", "tensorflow", "jax"}
SIMULATORS = {"mujoco", "isaac", "gazebo", "unity", "unreal"}
HEADINGS = {
    "duties": r"(?:you|we)[^a-zA-Z]{0,4}re excited about this opportunity because you[^a-zA-Z]*|what you(?:['’]ll| will) do|what you(?:['’]ll| will) work on|what you will get to do|what you(?:['’]ll| will) get to do|what will you get to do|we(?:['’]re| are) excited about you because you(?:['’]ll| will)|your role|responsibilities|key responsibilities",
    "required": r"we[^a-zA-Z]{0,4}re excited about you because you[^a-zA-Z]*|what we(?:['’]re| are) looking for|we(?:['’]re| are) looking for|what we look for|what you have|requirements|qualifications|required(?: qualifications)?|minimum qualifications|we(?:['’]re| are) excited about you because you",
    "preferred": r"preferred(?: or bonus)?(?: qualifications)?|nice to have|what will set you apart|bonus(?: points)?",
    "role": r"about the role(?: & team)?|about the team|the role|role overview",
    "ignore": r"about (?:us|the company)|our internship program|application review process|compensation|benefits|equal opportunity|privacy|our commitment",
}


@dataclass(frozen=True)
class JobEvidence:
    duties: tuple[str, ...]
    required: tuple[str, ...]
    preferred: tuple[str, ...]
    role: tuple[str, ...]
    features: frozenset[str]


def hits(text):
    return frozenset(key for key, pattern in SKILLS.items() if re.search(pattern, text, re.I))


def extract_job_evidence(description):
    text = re.sub(r"data:image/[^;,\s]+;base64,[A-Za-z0-9+/=]+", "", description)
    text = html.unescape(re.sub(r"<[^>]*>", "\n", text)).replace("\u00a0", " ")
    # Some cached HTML-to-text conversions glue headings to their paragraphs.
    for pattern in HEADINGS.values():
        text = re.sub(rf"(?i)({pattern})(?=[:\s]|[A-Z])", r"\n\1\n", text)
    parts = {key: [] for key in HEADINGS}
    state = "ignore"
    for raw in text.splitlines():
        line = raw.strip(" -:*#\t")
        if not line:
            continue
        heading = next((key for key, pattern in HEADINGS.items()
                        if re.fullmatch(pattern, line, re.I)), None)
        if heading:
            state = heading
            continue
        actual_state = "preferred" if re.search(r"\b(?:preferred|ideally|nice to have|bonus)\b", line, re.I) else state
        if actual_state != "ignore":
            parts[actual_state].append(line)
        elif re.search(r"(?:you(?:['’]ll| will)|this role|as (?:an?|our) .*intern)[^.\n]{0,100}(?:train|build|develop|evaluate|implement|research)", line, re.I):
            parts["duties"].append(line)
    content = "\n".join(parts["duties"] + parts["required"] + parts["preferred"] + parts["role"])
    return JobEvidence(*(tuple(parts[key]) for key in ("duties", "required", "preferred", "role")), hits(content))


def skill_groups(evidence):
    """Unique skills: required=2, preferred=1, duties=1. Alternatives count once."""
    groups = []
    seen = set()
    for importance, lines in (("REQUIRED", evidence.required), ("PREFERRED", evidence.preferred), ("DUTY", evidence.duties)):
        for line in lines:
            keys = set(hits(line))
            # Degree specialization text does not assert technical experience.
            if re.search(r"\b(?:pursuing|enrolled|degree|bachelor|master(?:['’]s)?|ph\.?d)\b", line, re.I) and not re.search(r"experience|proficien|strong (?:python|coding)", line, re.I):
                continue
            alternatives = []
            if re.search(r"\bor\b|and/or|at least one|one or more", line, re.I):
                for category in (LANGUAGES, FRAMEWORKS, SIMULATORS):
                    selected = keys & category
                    if len(selected) > 1:
                        alternatives.append(frozenset(selected));keys -= selected
            for group in alternatives + [frozenset({key}) for key in sorted(keys)]:
                if group <= seen:
                    continue
                seen.update(group)
                groups.append((importance, tuple(sorted(group)), line))
    return groups
