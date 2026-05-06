from __future__ import annotations

import os
import sqlite3
import time
from functools import wraps

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

from auth.login import authenticate_voter
from blockchain.blockchain import LightweightVotingBlockchain
from blockchain.transaction import create_vote_transaction, is_transaction_signature_valid
from blockchain.validation import validate_vote_transaction
from database.db import Database

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "research-prototype-change-me")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

db = Database()
voting_chain = LightweightVotingBlockchain(db)

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")


@app.context_processor
def inject_shell_context():
    """Small UI context layer for the dashboard shell."""

    try:
        shell_health = voting_chain.chain_health()
    except Exception:
        shell_health = {"is_valid": False, "status": "CHECK UNAVAILABLE", "nodes": {}, "errors": []}
    return {
        "shell_health": shell_health,
        "shell_election_active": db.is_election_active(),
        "shell_node_count": len(shell_health.get("nodes", {})),
        "shell_user_label": session.get("voter_name") or ("Admin" if session.get("admin") else "Guest"),
    }


def voter_required(route):
    @wraps(route)
    def wrapper(*args, **kwargs):
        if "voter_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return route(*args, **kwargs)

    return wrapper


def admin_required(route):
    @wraps(route)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            flash("Admin access required.", "warning")
            return redirect(url_for("admin_login"))
        return route(*args, **kwargs)

    return wrapper


@app.route("/")
def index():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        voter = authenticate_voter(db, request.form["voter_id"].strip(), request.form["password"])
        if voter:
            session.clear()
            session["voter_id"] = voter["voter_id"]
            session["voter_name"] = voter["name"]
            return redirect(url_for("vote"))
        flash("Invalid voter ID or password.", "danger")
    return render_template("login.html")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form["username"] == ADMIN_USERNAME and request.form["password"] == ADMIN_PASSWORD:
            session.clear()
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Invalid admin credentials.", "danger")
    return render_template("admin_login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))


@app.route("/vote", methods=["GET", "POST"])
@voter_required
def vote():
    voter = db.get_voter(session["voter_id"])
    candidates = db.get_candidates()
    if request.method == "POST":
        if not db.is_election_active():
            flash("Election is currently stopped.", "warning")
            return redirect(url_for("vote"))

        candidate = request.form["candidate"]
        transaction = create_vote_transaction(voter["voter_id"], candidate, voter["private_key"], voter["public_key"])

        signature_start = time.perf_counter()
        is_transaction_signature_valid(transaction)
        signature_verification_time_ms = (time.perf_counter() - signature_start) * 1000

        start = time.perf_counter()
        is_valid, message = validate_vote_transaction(db, voter["voter_id"], transaction)
        validation_time_ms = (time.perf_counter() - start) * 1000

        if not is_valid:
            flash(message, "danger")
            return redirect(url_for("vote"))

        voting_chain.add_pending_transaction(transaction, validation_time_ms, signature_verification_time_ms)
        db.mark_voter_voted(voter["voter_id"])

        created, block_message, _ = voting_chain.create_block_from_pending()
        flash(f"{message} {block_message if created else ''}", "success")
        return redirect(url_for("results"))

    return render_template(
        "vote.html",
        voter=voter,
        candidates=candidates,
        election_active=db.is_election_active(),
    )


@app.route("/admin")
@admin_required
def admin_dashboard():
    metrics = db.performance_metrics()
    metrics.update(voting_chain.storage_metrics())
    metrics.update(voting_chain.consensus_comparison_metrics())
    health = voting_chain.chain_health()
    return render_template(
        "admin.html",
        voters=db.get_voters(),
        candidates=db.get_candidates(),
        election_active=db.is_election_active(),
        metrics=metrics,
        health=health,
        pending_count=len(voting_chain.pending_transactions),
    )


@app.route("/admin/register-voter", methods=["POST"])
@admin_required
def register_voter():
    try:
        db.add_voter(request.form["voter_id"].strip(), request.form["name"].strip(), request.form["password"])
        flash("Voter registered successfully.", "success")
    except sqlite3.IntegrityError:
        flash("Voter ID already exists.", "danger")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/add-candidate", methods=["POST"])
@admin_required
def add_candidate():
    try:
        db.add_candidate(request.form["name"].strip())
        flash("Candidate added successfully.", "success")
    except sqlite3.IntegrityError:
        flash("Candidate already exists.", "danger")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/election/<action>", methods=["POST"])
@admin_required
def election_action(action):
    db.set_election_status(action == "start")
    flash(f"Election {'started' if action == 'start' else 'stopped'}.", "info")
    return redirect(url_for("admin_dashboard"))


@app.route("/blockchain")
def blockchain_explorer():
    return render_template("blockchain.html", blocks=voting_chain.get_chain(), health=voting_chain.chain_health())


@app.route("/results")
def results():
    candidates = [candidate["name"] for candidate in db.get_candidates()]
    vote_totals = {candidate: 0 for candidate in candidates}
    vote_totals.update(voting_chain.calculate_results())
    metrics = db.performance_metrics()
    metrics.update(voting_chain.storage_metrics())
    metrics.update(voting_chain.consensus_comparison_metrics())
    return render_template("results.html", results=vote_totals, metrics=metrics, health=voting_chain.chain_health())


@app.route("/metrics")
def metrics_dashboard():
    metrics = db.performance_metrics()
    metrics.update(voting_chain.storage_metrics())
    metrics.update(voting_chain.consensus_comparison_metrics())
    return render_template("metrics.html", metrics=metrics, health=voting_chain.chain_health())


@app.route("/settings")
def settings():
    return render_template("settings.html")


@app.route("/admin/simulate-tamper", methods=["POST"])
@admin_required
def simulate_tamper():
    if db.tamper_latest_block():
        flash("Latest block transaction was intentionally modified for tamper-detection demonstration.", "warning")
    else:
        flash("No non-genesis block is available to tamper with yet.", "info")
    return redirect(url_for("admin_dashboard"))


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(force=True)
    voter = authenticate_voter(db, data.get("voter_id", ""), data.get("password", ""))
    if not voter:
        return jsonify({"success": False, "message": "Invalid credentials"}), 401
    session.clear()
    session["voter_id"] = voter["voter_id"]
    session["voter_name"] = voter["name"]
    return jsonify({"success": True, "voter": {"voter_id": voter["voter_id"], "name": voter["name"]}})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"success": True})


@app.route("/api/register-voter", methods=["POST"])
@admin_required
def api_register_voter():
    data = request.get_json(force=True)
    try:
        db.add_voter(data["voter_id"], data["name"], data["password"])
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "Voter ID already exists"}), 409
    return jsonify({"success": True})


@app.route("/api/cast-vote", methods=["POST"])
@voter_required
def api_cast_vote():
    data = request.get_json(force=True)
    voter = db.get_voter(session["voter_id"])
    transaction = create_vote_transaction(voter["voter_id"], data["candidate"], voter["private_key"], voter["public_key"])
    signature_start = time.perf_counter()
    is_transaction_signature_valid(transaction)
    signature_verification_time_ms = (time.perf_counter() - signature_start) * 1000
    validation_start = time.perf_counter()
    is_valid, message = validate_vote_transaction(db, session["voter_id"], transaction)
    validation_time_ms = (time.perf_counter() - validation_start) * 1000
    if not is_valid:
        return jsonify({"success": False, "message": message}), 400
    voting_chain.add_pending_transaction(transaction, validation_time_ms, signature_verification_time_ms)
    db.mark_voter_voted(session["voter_id"])
    created, block_message, block = voting_chain.create_block_from_pending()
    return jsonify({"success": created, "message": block_message, "transaction": transaction, "block": block})


@app.route("/api/validate-transaction", methods=["POST"])
@voter_required
def api_validate_transaction():
    transaction = request.get_json(force=True)
    valid, message = validate_vote_transaction(db, session["voter_id"], transaction)
    return jsonify({"valid": valid, "message": message})


@app.route("/api/create-block", methods=["POST"])
@admin_required
def api_create_block():
    created, message, block = voting_chain.create_block_from_pending()
    return jsonify({"success": created, "message": message, "block": block})


@app.route("/api/blockchain")
def api_blockchain():
    return jsonify(voting_chain.get_chain())


@app.route("/api/results")
def api_results():
    return jsonify(voting_chain.calculate_results())


@app.route("/api/chain/validate")
def api_validate_chain():
    return jsonify(voting_chain.chain_health())


@app.route("/api/tamper-demo", methods=["POST"])
@admin_required
def api_tamper_demo():
    tampered = db.tamper_latest_block()
    return jsonify({"tampered": tampered, "health": voting_chain.chain_health()})


if __name__ == "__main__":
    debug_enabled = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug_enabled, host="127.0.0.1", port=int(os.environ.get("PORT", "5000")))
