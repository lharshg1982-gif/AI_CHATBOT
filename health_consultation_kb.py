import json
from pathlib import Path
from typing import Any, Dict, List

KB_PATH = Path(__file__).with_name("health_consultation_kb.json")


def load_knowledge_base() -> List[Dict[str, Any]]:
    with KB_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def retrieve_health_guidance(query: str, limit: int = 3) -> List[Dict[str, Any]]:
    query_terms = set(query.lower().replace("-", " ").split())
    scored = []
    for entry in load_knowledge_base():
        topic_terms = set()
        for topic in entry["topics"]:
            topic_terms.update(topic.lower().replace("-", " ").split())
        score = len(query_terms & topic_terms)
        if score:
            scored.append((score, entry))

    scored.sort(key=lambda item: (-item[0], item[1]["id"]))
    return [
        {
            "id": entry["id"],
            "title": entry["title"],
            "guidance": entry["guidance"],
            "safety": entry["safety"],
            "source": entry["source"],
            "match_score": score,
        }
        for score, entry in scored[:limit]
    ]
