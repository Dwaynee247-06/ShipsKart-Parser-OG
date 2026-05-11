from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import requests
import os

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "change-me-in-prod")

API_BASE_DEFAULT = os.environ.get("PARSER_API_BASE", "http://localhost:8000")


def bool_to_str(x: bool) -> str:
    return "true" if x else "false"


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        file = request.files.get("file")
        if not file or file.filename == "":
            flash("Please choose a file to upload.", "error")
            return redirect(url_for("index"))

        top_n = request.form.get("top_n", "5") or "5"
        api_base = request.form.get("api_base") or API_BASE_DEFAULT

        advanced   = request.form.get("advanced")          == "on"
        use_lev    = request.form.get("use_levenshtein")   == "on"
        use_tfidf  = request.form.get("use_tfidf")         == "on"
        use_inv    = request.form.get("use_inverted_index") == "on"
        use_phon   = request.form.get("use_phonetic")      == "on"

        params = {
            "top_n":               top_n,
            "advanced":            bool_to_str(advanced),
            "use_levenshtein":     bool_to_str(use_lev),
            "use_tfidf":           bool_to_str(use_tfidf),
            "use_inverted_index":  bool_to_str(use_inv),
            "use_phonetic":        bool_to_str(use_phon),
        }

        files = {
            "file": (
                file.filename,
                file.stream,
                file.mimetype or "application/octet-stream",
            )
        }

        try:
            resp = requests.post(
                f"{api_base}/api/v1/parse/match",
                params=params,
                files=files,
                timeout=120,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            flash(f"API error: {exc}", "error")
            return redirect(url_for("index"))

        data = resp.json()
        return render_template(
            "results.html",
            response=data,
            api_base=api_base,
            top_n=int(top_n),
            advanced=advanced,
            use_lev=use_lev,
            use_tfidf=use_tfidf,
            use_inv=use_inv,
            use_phon=use_phon,
        )

    return render_template("index.html", api_base=API_BASE_DEFAULT)


@app.route("/confirm_match", methods=["POST"])
def confirm_match():
    """
    Called via fetch() from results.html when a user selects a candidate.
    Forwards the confirmed mapping to the FastAPI backend feedback cache.
    """
    payload = request.get_json(force=True) or {}
    api_base = payload.get("api_base") or API_BASE_DEFAULT
    raw_query  = payload.get("raw_query", "")
    product_id = payload.get("product_id")

    if not raw_query or product_id is None:
        return jsonify({"ok": False, "error": "Missing raw_query or product_id"}), 400

    try:
        resp = requests.post(
            f"{api_base}/api/v1/confirm_match",
            json={"raw_query": raw_query, "product_id": product_id},
            timeout=10,
        )
        resp.raise_for_status()
        return jsonify({"ok": True})
    except requests.RequestException as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("FLASK_PORT", 5000)))
