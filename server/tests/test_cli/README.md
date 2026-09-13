# CLI integration tests

The tests in this directory exercise a running ORBIT installation. Before
running the suite, always reset the SQLite database from the installation
default. This prevents sessions, failed-login counters, account lockouts, and
other state from earlier runs from causing authentication failures or login
rate-limit errors.

Run these commands from the repository root:

```bash
./bin/orbit.sh stop
cp ./orbit.db ./orbit.db.bak
cp ./install/orbit.db.default ./orbit.db
python ./utils/scripts/sync_auth_backends.py \
  --direction sqlite-to-sqlite \
  --source-db ./orbit.db.bak \
  --dest-db ./orbit.db
./bin/orbit.sh restart --delete-logs
```

The sync step restores API keys and system prompts from the backup. It does
not restore users, sessions, failed-login counters, or account-lockout state;
those remain at their clean installation defaults.

The first `cp` command overwrites `orbit.db.bak` if it already exists. Rename
an existing backup first if it must be retained.

After ORBIT starts, verify that the server is running and authenticate the CLI
before invoking pytest:

```bash
./bin/orbit.sh status
./bin/orbit.sh login
```

When prompted, use the installation-default credentials:

```text
Username: admin
Password: ChangeMe!2026
```

Do not proceed until login succeeds. This confirms that the reset database has
the expected administrator account and provides any authentication required by
the CLI commands exercised during setup and testing.

Then execute the suite:

```bash
python -m pytest server/tests/test_cli/test_cli_integration.py -v
```

The default test administrator is `admin` with password `ChangeMe!2026`.
Deployments using different credentials can set
`ORBIT_TEST_ADMIN_USERNAME` and `ORBIT_TEST_ADMIN_PASSWORD` before invoking
pytest.
