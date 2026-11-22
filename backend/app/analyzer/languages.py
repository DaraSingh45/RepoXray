"""Extension -> language map, colors and ignore rules."""
from __future__ import annotations

LANGS: dict[str, tuple[str, str]] = {
    # ext: (language, color)
    ".py": ("Python", "#3572A5"), ".pyi": ("Python", "#3572A5"), ".ipynb": ("Jupyter Notebook", "#DA5B0B"),
    ".js": ("JavaScript", "#f1e05a"), ".mjs": ("JavaScript", "#f1e05a"), ".cjs": ("JavaScript", "#f1e05a"),
    ".jsx": ("JavaScript", "#f1e05a"), ".ts": ("TypeScript", "#3178c6"), ".tsx": ("TypeScript", "#3178c6"),
    ".mts": ("TypeScript", "#3178c6"), ".cts": ("TypeScript", "#3178c6"),
    ".vue": ("Vue", "#41b883"), ".svelte": ("Svelte", "#ff3e00"), ".astro": ("Astro", "#ff5a03"),
    ".go": ("Go", "#00ADD8"), ".rs": ("Rust", "#dea584"), ".java": ("Java", "#b07219"),
    ".kt": ("Kotlin", "#A97BFF"), ".kts": ("Kotlin", "#A97BFF"), ".scala": ("Scala", "#c22d40"),
    ".groovy": ("Groovy", "#4298b8"), ".c": ("C", "#555555"), ".h": ("C", "#555555"),
    ".cpp": ("C++", "#f34b7d"), ".cc": ("C++", "#f34b7d"), ".cxx": ("C++", "#f34b7d"), ".hpp": ("C++", "#f34b7d"),
    ".hh": ("C++", "#f34b7d"), ".cs": ("C#", "#178600"), ".fs": ("F#", "#b845fc"), ".vb": ("Visual Basic", "#945db7"),
    ".swift": ("Swift", "#F05138"), ".m": ("Objective-C", "#438eff"), ".mm": ("Objective-C++", "#6866fb"),
    ".rb": ("Ruby", "#701516"), ".php": ("PHP", "#4F5D95"), ".pl": ("Perl", "#0298c3"), ".lua": ("Lua", "#000080"),
    ".r": ("R", "#198CE7"), ".jl": ("Julia", "#a270ba"), ".dart": ("Dart", "#00B4AB"),
    ".ex": ("Elixir", "#6e4a7e"), ".exs": ("Elixir", "#6e4a7e"), ".erl": ("Erlang", "#B83998"),
    ".hs": ("Haskell", "#5e5086"), ".ml": ("OCaml", "#3be133"), ".clj": ("Clojure", "#db5855"),
    ".zig": ("Zig", "#ec915c"), ".nim": ("Nim", "#ffc200"), ".sol": ("Solidity", "#AA6746"),
    ".sh": ("Shell", "#89e051"), ".bash": ("Shell", "#89e051"), ".zsh": ("Shell", "#89e051"),
    ".ps1": ("PowerShell", "#012456"), ".bat": ("Batchfile", "#C1F12E"),
    ".html": ("HTML", "#e34c26"), ".htm": ("HTML", "#e34c26"), ".css": ("CSS", "#563d7c"),
    ".scss": ("SCSS", "#c6538c"), ".sass": ("Sass", "#a53b70"), ".less": ("Less", "#1d365d"),
    ".sql": ("SQL", "#e38c00"), ".graphql": ("GraphQL", "#e10098"), ".gql": ("GraphQL", "#e10098"),
    ".proto": ("Protocol Buffers", "#4a90e2"), ".tf": ("HCL", "#844FBA"), ".hcl": ("HCL", "#844FBA"),
    ".md": ("Markdown", "#083fa1"), ".mdx": ("MDX", "#fcb32c"), ".rst": ("reStructuredText", "#141414"),
    ".json": ("JSON", "#292929"), ".yml": ("YAML", "#cb171e"), ".yaml": ("YAML", "#cb171e"),
    ".toml": ("TOML", "#9c4221"), ".xml": ("XML", "#0060ac"), ".gradle": ("Gradle", "#02303a"),
    ".cmake": ("CMake", "#DA3434"), ".mk": ("Makefile", "#427819"),
}

SPECIAL_FILES: dict[str, str] = {
    "Dockerfile": "Dockerfile", "Makefile": "Makefile", "CMakeLists.txt": "CMake", "Jenkinsfile": "Groovy",
    "Rakefile": "Ruby", "Gemfile": "Ruby", "Vagrantfile": "Ruby", "Procfile": "Procfile",
}

# Languages that count as "code" (vs data/docs/markup) for metrics and graphs
CODE_LANGS = {
    "Python", "JavaScript", "TypeScript", "Vue", "Svelte", "Astro", "Go", "Rust", "Java", "Kotlin", "Scala",
    "Groovy", "C", "C++", "C#", "F#", "Visual Basic", "Swift", "Objective-C", "Objective-C++", "Ruby", "PHP",
    "Perl", "Lua", "R", "Julia", "Dart", "Elixir", "Erlang", "Haskell", "OCaml", "Clojure", "Zig", "Nim",
    "Solidity", "Shell", "PowerShell", "Batchfile", "SQL", "Jupyter Notebook",
}
DOC_LANGS = {"Markdown", "MDX", "reStructuredText"}
STYLE_LANGS = {"HTML", "CSS", "SCSS", "Sass", "Less"}

LANG_COLOR = {name: color for name, color in LANGS.values()}
LANG_COLOR.update({"Dockerfile": "#384d54", "Makefile": "#427819", "CMake": "#DA3434", "Procfile": "#888888",
                   "Other": "#6b7280"})

IGNORE_DIRS = {
    ".git", "node_modules", "bower_components", "vendor", "venv", ".venv", "env", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".tox", ".idea", ".vscode", "dist", "build", "out", "target", ".next", ".nuxt", ".svelte-kit",
    ".turbo", ".cache", "coverage", ".gradle", "Pods", "DerivedData", ".terraform", "site-packages", ".dart_tool",
    ".angular", ".expo", "bin", "obj", ".parcel-cache", "storybook-static", "htmlcov", ".eggs",
}
# Directories we skip for code-graph purposes but still list (e.g. generated / vendored)
GENERATED_HINTS = ("min.js", ".min.css", ".map", ".lock", "-lock.json", ".pb.go", "_pb2.py", ".generated.", ".gen.", "_generated.", ".g.dart", ".freezed.dart")

BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".icns", ".webp", ".avif", ".svg", ".pdf", ".zip", ".gz",
    ".tgz", ".bz2", ".xz", ".7z", ".rar", ".jar", ".war", ".class", ".so", ".dll", ".dylib", ".exe", ".bin",
    ".o", ".a", ".lib", ".pyc", ".pyo", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp3", ".mp4", ".wav",
    ".ogg", ".mov", ".avi", ".webm", ".psd", ".sketch", ".fig", ".db", ".sqlite", ".sqlite3", ".pkl", ".pt",
    ".pth", ".onnx", ".h5", ".npy", ".npz", ".parquet", ".wasm", ".DS_Store", ".keystore", ".jks",
}


def detect_language(name: str) -> str | None:
    if name in SPECIAL_FILES:
        return SPECIAL_FILES[name]
    if name.startswith("Dockerfile"):
        return "Dockerfile"
    dot = name.rfind(".")
    if dot == -1:
        return None
    ext = name[dot:].lower()
    entry = LANGS.get(ext)
    return entry[0] if entry else None
