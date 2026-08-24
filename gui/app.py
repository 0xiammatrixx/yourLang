"""Flask web GUI: shows the database and the pipeline trace in the browser.

Run:
    .venv/bin/python -m gui.app
Then open:
    http://127.0.0.1:5001
"""

from __future__ import annotations

from flask import Flask, redirect, render_template, request, url_for

from gui.web import new_store, run_web
from translator import Translator

app = Flask(__name__)

store = new_store()
state: dict = {"pending": None, "last": None}
translator = Translator()


def _fields(docs: list[dict]) -> list[str]:
    keys: list[str] = []
    for doc in docs:
        for key in doc:
            if key not in keys:
                keys.append(key)
    return keys


@app.get("/")
def index():
    snapshot = store.snapshot()
    fields = {name: _fields(docs) for name, docs in snapshot.items()}
    return render_template(
        "index.html",
        collections=snapshot,
        fields=fields,
        last=state.get("last"),
        pending=state.get("pending"),
    )


@app.post("/execute")
def execute():
    instruction = request.form.get("instruction", "")
    answer = request.form.get("answer", "").strip()
    state["last"] = run_web(translator, store, state, instruction, answer)
    return redirect(url_for("index"))


@app.post("/reset")
def reset():
    global store
    store = new_store()
    state["pending"] = None
    state["last"] = None
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True, use_reloader=False)
