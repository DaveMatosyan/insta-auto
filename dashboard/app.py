"""
Monitoring dashboard — view-only Flask app for ramp progress.

Run on either PC for real-time visibility:
    python dashboard/app.py
    # Opens at http://localhost:5555
"""

from flask import Flask, render_template, jsonify
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.supabase_client import supabase
from follow.ramp import get_all_active_accounts, get_phase_info

app = Flask(__name__)


@app.route("/")
def index():
    """Main dashboard page."""
    accounts = get_all_active_accounts()
    return render_template("index.html", accounts=accounts)


@app.route("/api/accounts")
def api_accounts():
    """JSON endpoint for account data (used by auto-refresh)."""
    accounts = get_all_active_accounts()
    return jsonify(accounts)


@app.route("/api/activity")
def api_activity():
    """JSON endpoint for recent follow activity."""
    resp = supabase.table("follow_log") \
        .select("*") \
        .order("followed_at", desc=True) \
        .limit(30) \
        .execute()
    return jsonify(resp.data)


@app.route("/api/stats")
def api_stats():
    """JSON endpoint for aggregate stats."""
    accounts = get_all_active_accounts()
    total_follows = sum(a["total_follows"] for a in accounts)
    total_remaining = sum(a["remaining"] for a in accounts)
    total_today = sum(a["daily_follows_today"] for a in accounts)

    return jsonify({
        "total_accounts": len(accounts),
        "total_follows": total_follows,
        "total_today": total_today,
        "total_remaining": total_remaining,
    })


if __name__ == "__main__":
    print("Dashboard running at http://localhost:5555")
    app.run(host="0.0.0.0", port=5555, debug=True)
