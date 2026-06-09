"""CLI helpers for the api_doc_gen skill.

Reads an OpenAPI / Swagger spec from a file path (JSON or YAML).

    python scripts/openapi_tools.py parse_openapi /tmp/petstore.json
    python scripts/openapi_tools.py get_endpoint_details /tmp/petstore.json /pets/{petId} GET
    python scripts/openapi_tools.py get_schema /tmp/petstore.json Pet

Pip deps (declared in SKILL.md frontmatter):
  PyYAML>=6.0   — required to parse .yaml / .yml specs

Exit codes: 0 = ok, 1 = runtime error, 2 = usage error.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _load_spec(spec_path: str) -> dict:
    """Read and parse a JSON or YAML OpenAPI spec from disk."""
    p = Path(spec_path)
    if not p.exists():
        return {"error": f"Spec file not found: {spec_path!r}"}
    raw = p.read_text(encoding="utf-8", errors="replace")
    try:
        spec = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        try:
            import yaml  # type: ignore
        except ImportError:
            return {"error": "PyYAML is required to parse non-JSON specs (declared in SKILL.md requirements)"}
        try:
            spec = yaml.safe_load(raw)
        except Exception as e:
            return {"error": f"Could not parse spec as JSON or YAML: {type(e).__name__}: {e}"}
    if not isinstance(spec, dict):
        return {"error": "Spec must be a JSON object / YAML mapping at the top level"}
    return spec


def _get_base_url(spec: dict) -> str:
    servers = spec.get("servers") or []
    if servers and isinstance(servers[0], dict):
        return servers[0].get("url") or "https://api.example.com"
    host = spec.get("host", "api.example.com")
    scheme = (spec.get("schemes") or ["https"])[0]
    base = spec.get("basePath", "/")
    return f"{scheme}://{host}{base}"


_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def parse_openapi(spec_path: str) -> dict:
    spec = _load_spec(spec_path)
    if "error" in spec:
        return spec
    info = spec.get("info") or {}
    paths = spec.get("paths") or {}
    endpoints = []
    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, details in methods.items():
            if method.lower() not in _HTTP_METHODS:
                continue
            if not isinstance(details, dict):
                continue
            endpoints.append({
                "path": path,
                "method": method.upper(),
                "summary": details.get("summary", ""),
                "description": (details.get("description") or "")[:200],
                "operationId": details.get("operationId", ""),
                "tags": details.get("tags") or [],
            })
    return {
        "api_title": info.get("title", ""),
        "api_version": info.get("version", ""),
        "base_url": _get_base_url(spec),
        "description": (info.get("description") or "")[:400],
        "endpoint_count": len(endpoints),
        "endpoints": endpoints,
    }


def get_endpoint_details(spec_path: str, path: str, method: str) -> dict:
    spec = _load_spec(spec_path)
    if "error" in spec:
        return spec
    paths = spec.get("paths") or {}
    method_lc = method.lower()
    endpoint = (paths.get(path) or {}).get(method_lc)
    if endpoint is None:
        # case-insensitive path fallback
        for p, methods in paths.items():
            if isinstance(methods, dict) and p.lower() == path.lower() and method_lc in methods:
                endpoint = methods[method_lc]
                break
    if endpoint is None:
        available = []
        for p, methods in paths.items():
            if isinstance(methods, dict):
                for m in methods:
                    if m.lower() in _HTTP_METHODS:
                        available.append(f"{m.upper()} {p}")
        return {
            "error": f"{method.upper()} {path} not found in spec",
            "available_endpoints": available[:30],
        }
    result = dict(endpoint)
    result["_base_url"] = _get_base_url(spec)
    components = spec.get("components") or {}
    result["_security_schemes"] = components.get("securitySchemes") or spec.get("securityDefinitions") or {}
    return result


def get_schema(spec_path: str, schema_name: str) -> dict:
    spec = _load_spec(spec_path)
    if "error" in spec:
        return spec
    schemas = (spec.get("components") or {}).get("schemas") or {}
    definitions = spec.get("definitions") or {}
    combined = {**definitions, **schemas}
    if schema_name in combined:
        return {"name": schema_name, "schema": combined[schema_name]}
    for k, v in combined.items():
        if k.lower() == schema_name.lower():
            return {"name": k, "schema": v}
    return {
        "error": f"Schema {schema_name!r} not found",
        "available_schemas": list(combined.keys()),
    }


_USAGE = """\
usage:
  python scripts/openapi_tools.py parse_openapi <spec_path>
  python scripts/openapi_tools.py get_endpoint_details <spec_path> <path> <method>
  python scripts/openapi_tools.py get_schema <spec_path> <schema_name>
"""


def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(_USAGE, file=sys.stderr); return 2
    cmd = argv[1]
    try:
        if cmd == "parse_openapi":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            result: object = parse_openapi(argv[2])
        elif cmd == "get_endpoint_details":
            if len(argv) < 5: print(_USAGE, file=sys.stderr); return 2
            result = get_endpoint_details(argv[2], argv[3], argv[4])
        elif cmd == "get_schema":
            if len(argv) < 4: print(_USAGE, file=sys.stderr); return 2
            result = get_schema(argv[2], argv[3])
        else:
            print(f"unknown command: {cmd!r}\n\n{_USAGE}", file=sys.stderr); return 2
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"})); return 1
    print(json.dumps(result, ensure_ascii=False)); return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
