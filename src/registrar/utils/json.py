import json


def dumps_min(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
