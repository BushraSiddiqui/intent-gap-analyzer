import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATE_NAME = "report.html.j2"


def _find_template_dir() -> Path:
    here = Path(__file__).resolve().parent
    candidates = [
        here.parent / "templates",
        here / "templates",
        here.parent,
        here,
        Path("/app/templates"),
        Path("/app"),
        Path.cwd() / "templates",
        Path.cwd(),
    ]
    for c in candidates:
        if (c / TEMPLATE_NAME).exists():
            return c
    return candidates[0]


def build_report(output_path: Path, **ctx) -> None:
    template_dir = _find_template_dir()
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["tojson_pretty"] = lambda v: json.dumps(v, indent=2, default=str)
    template = env.get_template(TEMPLATE_NAME)
    html = template.render(**ctx)
    output_path.write_text(html, encoding="utf-8")
