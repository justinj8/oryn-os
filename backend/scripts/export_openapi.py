"""Write the API's OpenAPI document (used to generate the frontend's typed client)."""

import json
import sys
from pathlib import Path

from oryn.api.app import create_app

out = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
out.write_text(json.dumps(create_app().openapi(), indent=2))
print(f"wrote {out}")
