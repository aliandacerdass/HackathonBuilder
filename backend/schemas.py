"""Boru hattındaki her ajanın çıktı şeması.

pydantic modeli iki iş görür:
  1. `json_schema(Model)` → CLI'a verilen JSON schema (model bu formatta cevap verir)
  2. `Model.model_validate(dict)` → gelen cevabı doğrular
"""
from pydantic import BaseModel


class Refined(BaseModel):
    """Refiner çıktısı: kullanıcının ham konusunun netleştirilmiş hâli."""
    topic: str                  # 1-2 cümlelik net konu
    jury_criteria: list[str]    # jürinin muhtemel değerlendirme kriterleri
    constraints: list[str]      # süre, ekip, teknik kısıtlar
    keywords: list[str]


class Idea(BaseModel):
    title: str
    pitch: str                  # tek cümle
    problem: str
    solution: str
    mvp_scope: list[str]        # süreye sığan özellikler
    wow_factor: str             # demoda jüriyi etkileyecek an
    risks: list[str]


class Ideas(BaseModel):
    """Konsey tur 1: her model bağımsız fikir üretir."""
    ideas: list[Idea]


class Critique(BaseModel):
    idea_id: str
    strengths: list[str]
    weaknesses: list[str]


class Round2(BaseModel):
    """Konsey tur 2: diğer fikirleri eleştir + en iyisini sentezle."""
    critiques: list[Critique]
    improved_idea: Idea


class Score(BaseModel):
    idea_id: str
    jury_fit: int       # 1-10
    feasibility: int    # 1-10, verilen sürede yapılabilir mi
    wow: int            # 1-10
    originality: int    # 1-10
    demo: int           # 1-10, canlı demo edilebilir mi
    reasoning: str


class Verdict(BaseModel):
    scores: list[Score]


def json_schema(model: type[BaseModel]) -> dict:
    """pydantic şemasını 3 CLI'ın da kabul ettiği strict şemaya çevirir:
    $ref'ler açılır, title'lar silinir, tüm alanlar zorunlu, ekstra alan yasak."""
    raw = model.model_json_schema()
    defs = raw.pop("$defs", {})

    def fix(node):
        if isinstance(node, list):
            return [fix(n) for n in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            return fix(defs[node["$ref"].split("/")[-1]])
        # "title" meta verisi silinir; ama "properties" içindeki alan ADLARINA dokunulmaz
        node = {k: ({p: fix(s) for p, s in v.items()} if k == "properties" else fix(v))
                for k, v in node.items() if k != "title"}
        if node.get("type") == "object":
            node["required"] = list(node.get("properties", {}))
            node["additionalProperties"] = False
        return node

    return fix(raw)


# ---------- V2: araştırma ----------

class Queries(BaseModel):
    """Sorgu yazıcı: seçilen fikirden her kaynak için arama sorgusu."""
    paper_queries: list[str]    # akademik terimler (OpenAlex)
    repo_queries: list[str]     # kısa GitHub arama terimleri
    web_queries: list[str]      # makale, haber, hackathon kazananları
    video_queries: list[str]    # YouTube demo / anlatım


class Source(BaseModel):
    title: str
    url: str
    kind: str                   # article | hackathon | video | other
    finding: str                # somut bilgi, mümkünse sayı


class WebFindings(BaseModel):
    sources: list[Source]


class RepoPick(BaseModel):
    name: str                   # owner/repo (verilen listeden)
    reuse: str                  # projeye ne alınabilir
    caution: str                # lisans, bakım, kalite uyarısı


class RepoReview(BaseModel):
    picks: list[RepoPick]


class Stat(BaseModel):
    claim: str                  # tam cümle
    value: str                  # ör. "53.9%"
    source_url: str             # verilen kaynaklardan biri OLMALI
    pitch_use: str              # jüri sunumunda nasıl kullanılır


class Stats(BaseModel):
    stats: list[Stat]


class Feature(BaseModel):
    name: str
    why: str                    # jüri / kullanıcı için değeri
    effort: str                 # low | medium | high (verilen sürede)
    source_urls: list[str]      # ilham aldığı kaynaklar (verilenlerden)


class Features(BaseModel):
    features: list[Feature]
