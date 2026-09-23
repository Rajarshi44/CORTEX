---
description: Guardrail for resetting or modifying local databases
---

# Safe Database Resets

When asked to reset, drop, or recreate a database (especially SQLite `.db` files):
1. **Never delete the database file directly** (e.g., using `Remove-Item` or `rm`) while the backend service is running. This corrupts the connection pool and crashes the application.
2. **Prefer graceful programmatic resets**: Use SQLAlchemy's `metadata.drop_all()` and `create_all()`, or execute `TRUNCATE / DELETE` queries to clear data while keeping the schema and connections intact.
3. **If file deletion is absolutely necessary**: You MUST gracefully shut down all background tasks and server processes (e.g., Uvicorn) that have open handles to the file before deleting it, and restart them afterward.
