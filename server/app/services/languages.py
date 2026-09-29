"""Maps file extensions to editor/runtime language identifiers."""

EXTENSION_LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".json": "json",
    ".md": "markdown",
    ".html": "html",
    ".css": "css",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".sh": "shell",
    ".sql": "sql",
    ".txt": "plaintext",
}


def detect_language(filename: str) -> str:
    lowered = filename.lower()

    for extension, language in EXTENSION_LANGUAGES.items():
        if lowered.endswith(extension):
            return language

    return "plaintext"
