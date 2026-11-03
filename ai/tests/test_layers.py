"""docs/ARCHITECTURE.md 「의존 방향」 규칙을 import로 검사한다.

app/ 아래 모든 파일의 import를 읽어, 층 방향 · 묶음 · 영역 안 순서를 어기거나 순환하면 실패한다.
"""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

ALLOWED = {
    "main": {"api", "services", "tasks", "clients", "schemas", "core"},
    "api": {"api", "services", "schemas", "core"},
    "services": {"services", "tasks", "clients", "schemas", "core"},
    "tasks": {"tasks", "clients", "schemas", "core"},
    "clients": {"schemas", "core"},
    "schemas": {"schemas", "core"},
    "core": {"core", "schemas"},
}
API_EXCEPTIONS = {"app.clients.llm"}
AREA_ORDER = {"": 0, "parts": 1, "landmarks": 2, "common": 3}


def module_name(path: Path) -> str:
    parts = path.relative_to(APP.parent).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def module_file(name: str) -> Path | None:
    base = APP.parent.joinpath(*name.split("."))
    for path in (base.with_suffix(".py"), base / "__init__.py"):
        if path.is_file():
            return path
    return None


def imported_modules(path: Path) -> set[str]:
    """from X import Y에서 X.Y가 모듈이면 X.Y를, 아니면 X를 가져온 것으로 본다."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names if alias.name.startswith("app.")}
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app"):
            for alias in node.names:
                child = f"{node.module}.{alias.name}"
                found.add(child if module_file(child) else node.module)
    return found


def graph() -> dict[str, set[str]]:
    return {module_name(path): imported_modules(path) for path in APP.rglob("*.py")}


def layer(name: str) -> str:
    parts = name.split(".")
    return parts[1] if len(parts) > 1 else "main"


def area_level(name: str) -> int:
    path = module_file(name)
    assert path is not None
    relative = path.relative_to(APP / "tasks" / "area").parts
    return AREA_ORDER[relative[0] if len(relative) > 1 else ""]


def violation(source: str, target: str) -> str | None:
    source_layer, target_layer = layer(source), layer(target)
    if target_layer not in ALLOWED[source_layer]:
        if source_layer == "api" and target in API_EXCEPTIONS:
            return None
        return f"{source_layer} → {target_layer}"
    group = 2
    if source_layer == target_layer in ("services", "tasks"):
        source_group, target_group = source.split(".")[group], target.split(".")[group]
        if source_group != target_group:
            return f"{source_layer} 묶음 {source_group} → {target_group}"
        if source_layer == "tasks" and source_group == "area":
            if area_level(target) < area_level(source):
                return "tasks/area 안에서 위로 (입구 → parts → landmarks → common 순서)"
    return None


def test_imports_follow_layer_rules():
    problems = [
        f"{source} → {target}: {reason}"
        for source, targets in graph().items()
        for target in sorted(targets)
        if (reason := violation(source, target))
    ]

    assert problems == []


def test_no_import_cycles():
    edges = graph()
    cycles: list[list[str]] = []
    done: set[str] = set()

    def visit(name: str, path: list[str]) -> None:
        for target in edges.get(name, ()):
            if target in path:
                cycles.append(path[path.index(target) :] + [target])
            elif target not in done:
                visit(target, path + [target])
        done.add(name)

    for name in sorted(edges):
        if name not in done:
            visit(name, [name])

    assert cycles == []


def test_rules_catch_a_bad_import():
    assert violation("app.tasks.explanation.guide_explainer", "app.services.guide_job.runner")
    assert violation("app.api.v1.guide_jobs", "app.tasks.area.area_work")
    assert violation("app.tasks.explanation.guide_explainer", "app.tasks.area.reference_area")
    assert violation("app.tasks.area.common.face_map", "app.tasks.area.parts.lip_area")
    assert violation("app.api.v1.guide_jobs", "app.clients.llm") is None
