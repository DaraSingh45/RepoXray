"""Fast unit tests (no network)."""
import os
import tempfile
from collections import Counter
from pathlib import Path

os.environ.setdefault("REPOXRAY_DATA_DIR", tempfile.mkdtemp())

import pytest  # noqa: E402

from app.analyzer import deps, docs, flows, graph, scanner, stack  # noqa: E402
from app.github import RepoError, parse_github_url  # noqa: E402
from app.llm.providers import parse_json  # noqa: E402
from app.rag.index import RepoIndex, build_chunks  # noqa: E402


@pytest.mark.parametrize("url,owner,repo,ref,sub", [
    ("https://github.com/pallets/flask", "pallets", "flask", None, None),
    ("github.com/pallets/flask.git", "pallets", "flask", None, None),
    ("git@github.com:pallets/flask.git", "pallets", "flask", None, None),
    ("pallets/flask", "pallets", "flask", None, None),
    ("https://github.com/a/b/tree/dev/src/app", "a", "b", "dev", "src/app"),
    ("https://www.github.com/a/b/?tab=readme#x", "a", "b", None, None),
])
def test_parse_url(url, owner, repo, ref, sub):
    r = parse_github_url(url)
    assert (r.owner, r.repo, r.ref, r.subpath) == (owner, repo, ref, sub)


@pytest.mark.parametrize("bad", ["", "hello", "https://gitlab.com/a/b", "https://github.com/onlyowner"])
def test_parse_url_bad(bad):
    with pytest.raises(RepoError):
        parse_github_url(bad)


def make_repo(files: dict[str, str]) -> Path:
    root = Path(tempfile.mkdtemp())
    for p, c in files.items():
        f = root / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(c)
    return root


SAMPLE = {
    "README.md": "# Demo\n\nDemo is a small web API that manages todo items for teams and individuals.\n\n## Features\n- Fast\n- Simple\n",
    "requirements.txt": "fastapi==0.95.0\nsqlalchemy>=1.4\npytest\n",
    "app/main.py": "from fastapi import FastAPI\nfrom app.api import routes\napp = FastAPI()\n\n@app.get('/health')\ndef health():\n    return {'ok': True}\n\nif __name__ == '__main__':\n    import uvicorn; uvicorn.run(app)\n",
    "app/api/routes.py": "from app.services.todo import create\n\n@router.post('/todos')\ndef add():\n    return create()\n",
    "app/services/todo.py": "from app.models import Todo\n\ndef create():\n    # TODO: validate\n    return Todo()\n",
    "app/models.py": "class Todo:\n    '''A todo.'''\n    pass\n",
    "tests/test_todo.py": "def test_x():\n    assert True\n",
    "web/package.json": '{"name":"web","dependencies":{"react":"^18.0.0"},"scripts":{"dev":"vite"}}',
    "web/src/main.tsx": "import React from 'react'\nimport App from './App'\ncreateRoot(document.getElementById('root')).render(<App/>)\n",
    "web/src/App.tsx": "import { api } from '@/lib/api'\nexport default function App(){ return null }\n",
    "web/src/lib/api.ts": "export const api = 1\n",
    ".env": "SECRET=abc",
    "logo.png": "\x00binary",
}


def test_full_static_analysis():
    root = make_repo(SAMPLE)
    sc = scanner.scan(root, 1000, 100000)
    assert any(f.path == "logo.png" and f.is_binary for f in sc.files)
    d = deps.collect(sc.contents)
    names = {x["name"] for x in d["dependencies"]}
    assert {"fastapi", "sqlalchemy", "react"} <= names
    langs = scanner.language_breakdown(sc.files)
    st = stack.detect(sc.files, d["dependencies"], langs, sc.contents)
    tech = {t["name"] for t in st}
    assert {"FastAPI", "React", "SQLAlchemy", "pytest"} <= tech
    assert stack.project_type(st, sc.files, d["projects"]) == "Full-stack web application"
    code = {f.path for f in sc.files if f.is_code}
    g = graph.ImportGraph(sc.contents, code, {})
    g.build()
    assert ("app/main.py", "app/api/routes.py") in g.edges
    assert ("app/services/todo.py", "app/models.py") in g.edges
    assert ("web/src/main.tsx", "web/src/App.tsx") in g.edges
    routes = graph.extract_routes(sc.contents)
    assert {(r["method"], r["path"]) for r in routes} >= {("GET", "/health"), ("POST", "/todos")}
    ind, outd = Counter(), Counter()
    for (a, b) in g.edges:
        ind[b] += 1; outd[a] += 1
    eps = graph.find_entry_points(sc.files, sc.contents, d["projects"], ind, outd)
    assert eps and eps[0]["path"] in ("app/main.py", "web/src/main.tsx")
    mods = graph.aggregate_modules(g.edges, sc.files)
    assert mods["nodes"]
    arch = flows.architecture(mods, st)
    assert arch.startswith("flowchart")
    summary = docs.readme_summary(sc.contents["README.md"])
    assert "todo" in summary["intro"][0] and summary["features"] == ["Fast", "Simple"]


def test_empty_repo():
    root = make_repo({})
    sc = scanner.scan(root, 100, 1000)
    assert sc.files == []
    assert scanner.language_breakdown([]) == []
    assert graph.aggregate_modules(Counter(), [])["nodes"] == []


def test_parse_json_tolerant():
    assert parse_json('```json\n{"a": [1,2,],}\n```') == {"a": [1, 2]}
    assert parse_json("Sure! here: {\"x\": 1} hope it helps") == {"x": 1}
    assert parse_json("nope") is None


def test_rag_bm25():
    contents = {"a.py": "def compute_tax(amount):\n    return amount * 0.2\n", "b.py": "def render_page():\n    pass\n"}
    idx = RepoIndex(build_chunks(contents, {}), None, None)
    hits = idx.search("how is tax computed", 2)
    assert hits[0]["path"] == "a.py"


def test_manifests_varied():
    assert deps.parse_go_mod("module x\n\ngo 1.21\nrequire (\n\tgithub.com/gin-gonic/gin v1.9.0\n)\n", "go.mod")[0][0]["name"] == "github.com/gin-gonic/gin"
    assert deps.parse_cargo('[package]\nname="x"\n[dependencies]\nserde = "1"\ntokio = { version = "1" }\n', "Cargo.toml")[0][1]["spec"] == "1"
    assert deps.parse_pyproject('[project]\nname="x"\ndependencies=["httpx>=0.2", "rich"]\n', "pyproject.toml")[0][0]["name"] == "httpx"
    assert deps.parse_package_json("not json", "package.json") == ([], {})


def test_thinking_models_are_cleaned():
    from app.llm.providers import parse_json, without_thinking
    toks = ["<thi", "nk>reasoning {x}", "</th", "ink>\n\nAnswer", " here."]
    assert "".join(without_thinking(iter(toks))) == "Answer here."
    assert "".join(without_thinking(iter(["a < b ", "<b>x</b>"]))) == "a < b <b>x</b>"
    assert parse_json('<think>{"wrong": 1}</think>{"summary": "ok"}') == {"summary": "ok"}
