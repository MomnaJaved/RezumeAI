"""
Legacy entrypoint — delegates to api.main:app.
Prefer: uvicorn api.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import sys

from api.paths import repo_root

ROOT = repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.main import app  # noqa: F401

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)
