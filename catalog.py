"""Catalog loader.

The catalog (rooms, products, choices, measurements, formulas, prices, images)
lives in **catalog.json** — a plain data file. Adding a new choice, product, rule,
or price only means editing that JSON; no code change here.

The file is re-read on every access, so edits to catalog.json show up immediately
(just refresh the browser — no server restart needed).
"""
import json
import os

_PATH = os.path.join(os.path.dirname(__file__), "catalog.json")


def _data() -> dict:
    with open(_PATH, encoding="utf-8") as f:
        return json.load(f)


def categories_brief():
    return [
        {"id": c["id"], "name": c["name"], "sub_category": c.get("sub_category", ""), "image": c.get("image")}
        for c in _data()["categories"]
    ]


def get_category(category_id: str):
    return {c["id"]: c for c in _data()["categories"]}.get(category_id)


def rooms():
    return _data()["rooms"]
