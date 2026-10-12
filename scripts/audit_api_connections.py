"""Inventory frontend service requests against registered FastAPI routes, without database access."""
import argparse
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def inventory(frontend):
    # Route registration is safe; do not enter lifespan or use configured production credentials.
    os.environ.update(ENVIRONMENT="test", DATABASE_URL="postgresql+psycopg://test:test@127.0.0.1:1/unused_test",
                      CONTROL_DATABASE_URL="postgresql+psycopg://test:test@127.0.0.1:1/unused_test",
                      ENABLE_SOCKET_PROGRESS="false", REQUIRE_RLS="false", AUTO_CREATE_TABLES="false")
    from app.main import create_app
    app = create_app()
    routes = []
    registered = []

    def collect(router, prefix=""):
        for route in router.routes:
            if hasattr(route, "original_router"):
                collect(route.original_router, prefix + route.include_context.prefix)
            elif hasattr(route, "methods") and getattr(route, "include_in_schema", False):
                registered.extend((method, prefix + route.path) for method in route.methods)
    collect(app.router)
    for path, operations in app.openapi()["paths"].items():
        for method, operation in operations.items():
            if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
                routes.append({"method": method.upper(), "path": path, "handler": operation["operationId"]})
    consumers = "\n".join(p.read_text(encoding="utf-8") for p in (frontend / "src").rglob("*")
                          if p.suffix in {".js", ".jsx"} and "services" not in p.parts)
    requests = []
    for file in sorted((frontend / "src/services").glob("*.js")):
        source = file.read_text(encoding="utf-8")
        constants = dict(re.findall(r"const\s+(\w+)\s*=\s*['\"]([^'\"]+)['\"]", source))
        constants["whatsappSendPath"] = "/api/communications/whatsapp/send"
        matches = []
        for match in re.finditer(r"apiWrapper\(\{(.*?)\}\)", source, re.S):
            url = re.search(r"url:\s*(`[^`]+`|'[^']+'|\"[^\"]+\"|\w+)", match[1])
            method = re.search(r"method:\s*['\"](\w+)['\"]", match[1])
            if url:
                matches.append((match.start(), (method[1] if method else "GET").upper(), url[1]))
        for match in re.finditer(r"api\.(get|post|put|patch|delete)\(\s*(`[^`]+`|'[^']+'|\"[^\"]+\")", source):
            matches.append((match.start(), match[1].upper(), match[2]))
        for offset, method, expression in sorted(matches):
            path = constants.get(expression, expression.strip("`'\""))
            for key, value in constants.items():
                path = path.replace("${" + key + "}", value)
            path = re.sub(r"\$\{[^}]+\}", "{value}", path)
            before = source[:offset]
            obj = list(re.finditer(r"export const (\w+) = \{", before))
            prop = list(re.finditer(r"\b(\w+):\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>", before))
            name = (obj[-1][1] if obj else file.stem) + "." + (prop[-1][1] if prop else "unknown")
            used = name in consumers
            candidates = [path]
            # Dynamic subscription operation is limited to three supported operations in the UI.
            if file.name == "saas.js" and "/subscription/{value}" in path:
                candidates = [path.rsplit("/", 1)[0] + "/" + op for op in ("assign", "renew", "cancel")]
            found = []
            for candidate in candidates:
                found.extend(route for route in routes if route["method"] == method and canonical(route["path"]) == canonical(candidate))
            requests.append({"service": name, "file": str(file.relative_to(frontend)).replace('\\', '/'),
                             "line": source[:offset].count("\n") + 1, "method": method, "path": path,
                             "used_by_ui": used, "matched_routes": [route["path"] for route in found],
                             "redirect": bool(found) and all(route["path"].endswith('/') != path.endswith('/') for route in found)})
    covered = {(request["method"], route) for request in requests for route in request["matched_routes"]}
    from collections import Counter
    return {"routes": routes, "requests": requests,
            "duplicate_backend_routes": [{"method": method, "path": path, "count": count}
                                         for (method, path), count in Counter(registered).items() if count > 1],
            "backend_without_service": [route for route in routes if (route["method"], route["path"]) not in covered],
            "missing_frontend_routes": [request for request in requests if not request["matched_routes"]]}


def canonical(path):
    return re.sub(r"\{[^}]+\}", "{}", path.rstrip('/'))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "API_ENDPOINT_INVENTORY.json")
    args = parser.parse_args()
    result = inventory(args.frontend)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"{len(result['routes'])} backend routes; {len(result['requests'])} frontend requests; "
          f"{len(result['missing_frontend_routes'])} unmatched requests")
