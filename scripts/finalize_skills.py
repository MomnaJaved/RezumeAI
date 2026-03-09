import pandas as pd

VOCAB_PATH = "outputs/parsing/skills_vocab.csv"

df = pd.read_csv(VOCAB_PATH)

# Hard reject patterns (resume language)
REJECT_PATTERNS = [
    "-",        # hyphenated adjectives
    "driven",
    "oriented",
    "friendly",
    "motivated",
    "hands",
    "end",
    "real",
    "high",
    "well",
    "based",
    "level",
    "time",
    "site",
    "date",
]

# Known good technical signals
TECH_ALLOW = (
    "python","java","javascript","typescript","react","node","docker",
    "sql","mysql","postgresql","mongodb","aws","azure","gcp",
    "linux","git","github","kubernetes","tensorflow","pytorch",
    "django","flask","fastapi","laravel","spring","nestjs",
    "numpy","pandas","opencv","scikit","jwt","oauth",
)

def is_core_skill(skill: str) -> bool:
    s = skill.lower()

    if any(p in s for p in REJECT_PATTERNS):
        return False

    if "." in s or "+" in s or "#" in s:
        return True

    if any(t in s for t in TECH_ALLOW):
        return True

    return False

core = df[df["skill"].apply(is_core_skill)].copy()
core = core.sort_values("doc_freq", ascending=False)

core.to_csv("outputs/parsing/skills_core.csv", index=False)

print("✅ Core skills extracted:", len(core))
print("Top 30 core skills:")
print(", ".join(core.head(30)["skill"].tolist()))
