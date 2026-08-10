"""
Dashboard entry point — runs the Flask web UI.
This file is used when the Databricks App is configured to run the dashboard.
"""

import os
import sys
from pathlib import Path

# Switch to dashboard directory and import the Flask app
here = Path(__file__).resolve().parent
dashboard_dir = here / "dashboard"
sys.path.insert(0, str(dashboard_dir))
os.chdir(dashboard_dir)

from app import app  # noqa: E402

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=False)
