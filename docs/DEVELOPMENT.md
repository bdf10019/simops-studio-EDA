# Development workflow

## VS Code

Open the repository folder, select the `.venv` interpreter, and use **Terminal → Run Task**.
Tracked tasks provide verification, the complete demo, and the local dashboard. The Python
Test Explorer discovers the `unittest` suite through `.vscode/settings.json`.

## Visual Studio

Visual Studio with the Python development workload can open the repository as a folder. Select
the virtual environment, use `src` as the source root, and run the same PowerShell scripts in
its integrated terminal. No generated `.sln`, user profile, or machine-specific interpreter
path is committed.

## Git workflow

The baseline is developed in small stage commits. Before committing:

```powershell
.\scripts\verify.ps1
git diff --check
git status --short
```

Generated databases, reports, models, logs, backups, virtual environments, and `.env` files are
excluded by `.gitignore`. Do not commit solver licenses, credentials, proprietary board files,
or copied production datasets.

## SQL inspection

Application SQL lives in `src/simops_studio/database.py` and uses parameterized statements and
explicit transactions. After running the demo, an SQLite client can inspect the operational
state with read-only queries such as:

```sql
SELECT status, COUNT(*) AS cases
FROM cases
GROUP BY status;

SELECT pass_fail, COUNT(*) AS cases
FROM results
GROUP BY pass_fail;

SELECT c.assigned_worker,
       COUNT(*) AS completed_cases,
       ROUND(AVG(c.duration_ms), 3) AS average_duration_ms
FROM cases AS c
WHERE c.status = 'COMPLETED'
GROUP BY c.assigned_worker;

SELECT timestamp, level, case_id, message
FROM events
ORDER BY id DESC
LIMIT 20;
```

The database is a generated local artifact at `outputs/demo/simops.db`; it is intentionally not
part of source control.
