"""Generate a private, disposable DB password outside the repository."""
import os
from pathlib import Path
import secrets
import tempfile

fd, name = tempfile.mkstemp(prefix="foodsave-sql-", suffix=".env")
os.fchmod(fd, 0o600)
with os.fdopen(fd, "w") as stream:
    stream.write("FOODSAVE_TEST_DB_PASSWORD=Fs!9" + secrets.token_hex(24) + "\n")
print(Path(name))  # Only the path is printed; never print the password.
