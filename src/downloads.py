"""Browser-native download links that do not depend on Streamlit dynamic components."""

import base64


def download_link(label: str, data: str | bytes, filename: str, mime_type: str) -> str:
    payload = data.encode("utf-8") if isinstance(data, str) else data
    encoded = base64.b64encode(payload).decode("ascii")
    safe_label = label.replace("[", "\\[").replace("]", "\\]")
    return f"[{safe_label} — {filename}](data:{mime_type};base64,{encoded})"
