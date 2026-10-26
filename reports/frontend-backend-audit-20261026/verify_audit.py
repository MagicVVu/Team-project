"""Validate report references and read-only audit evidence, without network access."""
import hashlib
import json
import pathlib
import re

here = pathlib.Path(__file__).resolve().parent
root = here.parent.parent
spec = json.loads((here / "production-openapi.json").read_text(encoding="utf-8-sig"))
runtime = json.loads((here / "runtime-evidence.json").read_text(encoding="utf-8-sig"))
report = (here / "audit-report.md").read_text(encoding="utf-8")

links = []
for target in re.findall(r"\]\(([^)]+)\)", report):
    name, _, line = target.partition(":")
    path = (here / name).resolve()
    valid = path.is_file()
    if valid and line:
        valid = 1 <= int(line) <= len(path.read_text(encoding="utf-8-sig").splitlines())
    links.append({"target": target, "valid": valid})

h = "/api/v1/households/{household_id}"
routes = [
    ("get", "/api/v1/agent/conversation"),
    ("post", "/api/v1/agent/conversation/reset"),
    ("post", "/api/v1/agent/conversation-turns"),
    ("get", "/api/v1/agent/conversation-turns/{request_id}"),
    ("patch", h + "/shopping-list/items/{item_id}"),
    ("get", h + "/operations/{operation_id}/summary"),
    ("post", h + "/products"),
    ("put", h + "/inventory-items/{item_id}/product"),
    ("get", h + "/inventory-events"),
    ("post", h + "/inventory-items/{item_id}/corrections"),
    ("post", "/api/v1/operations/{operation_id}/feedback"),
    ("get", h + "/inventory-ai-compatibility"),
    ("get", h + "/inventory-items"),
    ("post", "/api/v1/drafts/{draft_id}/planning-revalidation"),
]
route_checks = [
    {"method": method, "path": path, "present": method in spec["paths"].get(path, {})}
    for method, path in routes
]
hash_checks = {
    name: hashlib.sha256((root / "backend/server" / name).read_bytes()).hexdigest() == value
    for name, value in runtime["production_source_sha256"].items()
}
markers = ["/conversation-turns", "/conversation/reset", "inventory-events", "/corrections",
           "inventory-ai-compatibility", "/feedback", "/summary", "/products", "/product",
           "planning-revalidation"]
source_files = list((root / "frontend/app/src/main").rglob("*.kt"))
marker_matches = {
    marker: [str(path.relative_to(root)) for path in source_files
             if marker in path.read_text(encoding="utf-8-sig")]
    for marker in markers
}
result = {
    "reference_count": len(links), "references": links,
    "production_routes": route_checks, "production_source_matches_local": hash_checks,
    "frontend_missing_route_marker_matches": marker_matches,
    "missing_markers_are_supporting_evidence_only": True,
    "p9_preflight_check_count": len(runtime["p9_read_only_preflight"]["checks"]),
    "business_mutations_performed": runtime["business_mutations_performed"],
    "model_calls_performed": runtime["model_calls_performed"],
}
result["passed"] = (
    all(row["valid"] for row in links)
    and all(row["present"] for row in route_checks)
    and all(hash_checks.values())
    and not any(marker_matches.values())
    and all(runtime["p9_read_only_preflight"]["checks"].values())
)
(here / "audit-validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"passed": result["passed"], "references": len(links), "routes": len(routes),
                  "source_hash_matches": sum(hash_checks.values())}, ensure_ascii=False))
raise SystemExit(0 if result["passed"] else 1)
