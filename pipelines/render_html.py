import argparse
import json
import shutil
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape


def _make_env(templates_dir: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html", "j2"]),
    )


def _load_items(curated_path: Path) -> list[dict]:
    return json.loads(curated_path.read_text(encoding="utf-8"))


def render(
    *,
    curated_path: Path,
    out_path: Path,
    templates_dir: Path,
    date: str,
    episode: int,
) -> Path:
    env = _make_env(templates_dir)
    tmpl = env.get_template("index.html.j2")
    items = _load_items(curated_path)
    html = tmpl.render(items=items, date=date, episode=episode, mode="list")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    css_src = templates_dir / "styles.css"
    css_dst = out_path.parent / "styles.css"
    shutil.copyfile(css_src, css_dst)
    return out_path


def render_frame(
    *,
    curated_path: Path,
    out_dir: Path,
    templates_dir: Path,
    date: str,
    episode: int,
    mode: str,  # "intro" | "outro" | "card"
    card_index: int | None = None,
) -> Path:
    env = _make_env(templates_dir)
    tmpl = env.get_template("index.html.j2")
    items = _load_items(curated_path)
    name = (
        f"frame_card_{card_index + 1:02d}.html" if mode == "card"
        else f"frame_{mode}.html"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / name
    html = tmpl.render(
        items=items, date=date, episode=episode,
        mode=mode, card_index=card_index or 0,
    )
    out.write_text(html, encoding="utf-8")
    # Each frame HTML needs styles.css next to it (Playwright loads via file://).
    # Always overwrite — template/CSS edits between runs must propagate.
    css_src = templates_dir / "styles.css"
    css_dst = out_dir / "styles.css"
    shutil.copyfile(css_src, css_dst)
    return out


def main():
    from core.config import Settings, day_dir, today_str
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--episode", type=int, default=1)
    args = parser.parse_args()
    settings = Settings()
    date = args.date or today_str(settings.timezone)
    d = day_dir(settings, date)
    render(
        curated_path=d / "curated.json",
        out_path=d / "index.html",
        templates_dir=settings.templates_dir,
        date=date,
        episode=args.episode,
    )
    print(f"wrote {d / 'index.html'}")


if __name__ == "__main__":
    main()
