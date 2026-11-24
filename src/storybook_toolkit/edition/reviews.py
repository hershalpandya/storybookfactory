"""Review records: each review is valid only while the dependency it names is unchanged."""

from ..store import load, prose, require, write_json


def active_reviews(root):
    path = root / "edition-reviews.json"
    return load(path) if path.is_file() else {}


def record_review(root, key, dependency, reviewer, role, decision, evidence):
    require(prose(reviewer) and prose(evidence), "Review needs a named reviewer and evidence")
    result = {"dependency": dependency, "reviewer": reviewer, "role": role,
              "decision": decision, "evidence": evidence}
    reviews = active_reviews(root)
    reviews.setdefault(key, {})[dependency] = result
    write_json(root / "edition-reviews.json", reviews)
    return result


def review_for(reviews, key, dependency):
    return reviews.get(key, {}).get(dependency)
