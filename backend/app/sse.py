import json


def sse(event: str, data: dict) -> str:
    """Formata um evento Server-Sent Events."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
