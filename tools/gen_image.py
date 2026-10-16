#!/usr/bin/env python
"""Generate an image via OpenRouter (Gemini image models).
Usage: python tools/gen_image.py "prompt text" out.png [--model MODEL] [--ref ref.png]
Reads OPENROUTER_API_KEY from .env in the project root.
Prints spend after the call. Default model is cheap (~$0.04/img)."""
import sys, os, json, base64, argparse, urllib.request, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
def load_key():
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip()
    sys.exit("no OPENROUTER_API_KEY in .env")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt"); ap.add_argument("out")
    ap.add_argument("--model", default="google/gemini-3.1-flash-image")
    ap.add_argument("--ref", action="append", default=[], help="reference image(s) for consistency")
    ap.add_argument("--aspect", default=None, help="e.g. 1:1, 16:9, 9:16")
    a = ap.parse_args()
    key = load_key()
    content = [{"type": "text", "text": a.prompt}]
    for r in a.ref:
        b = base64.b64encode(pathlib.Path(r).read_bytes()).decode()
        ext = pathlib.Path(r).suffix.lstrip(".").replace("jpg", "jpeg")
        content.append({"type": "image_url", "image_url": {"url": f"data:image/{ext};base64,{b}"}})
    body = {"model": a.model, "messages": [{"role": "user", "content": content}],
            "modalities": ["image", "text"]}
    if a.aspect:
        body["image_config"] = {"aspect_ratio": a.aspect}
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "HTTP-Referer": "https://github.com/klaymendel-art/tesla-flip", "X-Title": "Tesla Flip"})
    try:
        resp = json.load(urllib.request.urlopen(req, timeout=180))
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode()[:800]}")
    msg = resp["choices"][0]["message"]
    imgs = msg.get("images") or []
    if not imgs:
        print("NO IMAGE. Text reply:", (msg.get("content") or "")[:600]); sys.exit(2)
    url = imgs[0]["image_url"]["url"]
    data = base64.b64decode(re.sub(r"^data:image/\w+;base64,", "", url))
    pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(a.out).write_bytes(data)
    u = resp.get("usage", {})
    print(f"saved {a.out} ({len(data)//1024} KB) | tokens in={u.get('prompt_tokens')} out={u.get('completion_tokens')} | text: {(msg.get('content') or '')[:150]}")

if __name__ == "__main__":
    main()
