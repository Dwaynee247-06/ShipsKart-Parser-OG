import os
import requests
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "dev-secret")

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", api_base=API_BASE)


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file or not file.filename:
        flash("Please select a file.")
        return redirect(url_for("index"))

    # ── flags ────────────────────────────────────────────────
    advanced    = request.form.get("advanced") == "on"
    use_lev     = request.form.get("use_lev") == "on"
    use_tfidf   = request.form.get("use_tfidf") == "on"
    use_inv     = request.form.get("use_inv") == "on"
    use_phonetic = request.form.get("use_phonetic") == "on"
    top_n       = int(request.form.get("top_n", 5))

    params = {
        "advanced":           str(advanced).lower(),
        "use_levenshtein":    str(use_lev).lower(),
        "use_tfidf":          str(use_tfidf).lower(),
        "use_inverted_index": str(use_inv).lower(),
        "use_phonetic":       str(use_phonetic).lower(),
        "top_n":              top_n,
    }

    try:
        resp = requests.post(
            f"{API_BASE}/api/v1/parse/match",
            params=params,
            files={"file": (file.filename, file.stream, file.content_type)},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as exc:
        flash(f"API error: {exc}")
        return redirect(url_for("index"))

    return render_template(
        "results.html",
        response=data,
        api_base=API_BASE,
        top_n=top_n,
        advanced=advanced,
        use_lev=use_lev,
        use_tfidf=use_tfidf,
        use_inv=use_inv,
        use_phonetic=use_phonetic,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
