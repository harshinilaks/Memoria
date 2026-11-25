import os

# Settings require DATABASE_URL at import time. Unit tests never connect, so any URL works;
# integration tests point everything at TEST_DATABASE_URL.
os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://unused@localhost/unused"),
)
