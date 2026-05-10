import hashlib
import json

from registrar.utils.json import dumps_min


class IndexManager:
    def __init__(self):
        self.data = {"version": "v1.0.0", "themes": {"dark": [], "light": []}}

    def add(self, entry):
        self.data["themes"][entry.ui_type].append(entry.__dict__)

    def _hash(self):
        return hashlib.sha256(
            json.dumps(self.data, sort_keys=True).encode()
        ).hexdigest()

    def write(self, path):
        with open(path, "w") as f:
            f.write(dumps_min(self.data))
