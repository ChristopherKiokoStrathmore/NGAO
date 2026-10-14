import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.pop("BACKEND_BASE_URL", None)
os.environ.pop("DB_DSN", None)
