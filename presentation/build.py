"""Junta src/ em um único arquivo: apresentacao.html (CSS, JS e fontes embutidos).

Uso: python internal_tests/apresentacao/build.py
O arquivo gerado abre direto no navegador, sem servidor e sem internet.
"""

import base64
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "src"
OUT = HERE / "apresentacao.html"


def font_uri(match):
    data = (SRC / "css" / match.group(1)).resolve().read_bytes()
    return "url(data:font/woff2;base64," + base64.b64encode(data).decode() + ")"


def inline_css(match):
    css = (SRC / match.group(1)).read_text(encoding="utf-8")
    css = re.sub(r"url\(([^)]+\.woff2)\)", font_uri, css)
    return "<style>\n" + css + "</style>"


def inline_js(match):
    path = SRC / match.group(1)
    if not path.exists():
        return ""
    js = path.read_text(encoding="utf-8").replace("</script", "<\\/script")
    return "<script>\n" + js + "</script>"


def main():
    html = (SRC / "index.html").read_text(encoding="utf-8")
    html = re.sub(r'<link rel="stylesheet" href="([^"]+)">', inline_css, html)
    html = re.sub(r'<script src="([^"]+)"></script>', inline_js, html)
    html = html.replace("<head>", "<head>\n<!-- GERADO por build.py a partir de src/. Edite src/ e rode o build. -->", 1)
    OUT.write_text(html, encoding="utf-8")
    print(f"{OUT.name}: {OUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
