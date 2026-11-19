# Empty rc65 workspace

The corrected v2 kit uses a standalone SQLite database in DELETE journal mode. Validation opens it with `mode=ro&immutable=1`, preventing the validation itself from leaving WAL/SHM files beside the distributed baseline. Only an explicit file allowlist is archived. The launcher rejects sidecars and checks the empty baseline and installer hashes before making a fresh isolated copy.

No prior office database or backup is an input. The baseline contains zero users/credentials, cases, payments, imported legacy rows, audit entries or saved office settings. Built-in code/ZIP reference lists and schema/counters remain. First Administrator setup is expected; leave fictional sample cases unchecked. After setup, that active copy contains the new account you create.

## Build the kit

From the repository root, with the verified rc65 installer available outside Git:

```powershell
python scripts/build_empty_workspace_kit.py --installer "C:\BuildArtifacts\Worthless-Check-Setup-rc65.exe" --output "C:\BuildArtifacts\EmptyWorkspace-v2"
```

The output folder must not exist. The builder creates and validates the baseline, inserts both hashes into the launcher and writes Worthless-Check-rc65-Empty-Workspace-v2.zip. Run only the generated launcher in the extracted kit, not the hash-placeholder source template. Use verified build artifacts; generating a hash is not proof an installer is trusted.

The launcher extracts the program without installation or shared-directory/group changes, copies only the empty baseline into a new per-user LocalAppData profile and uses `--data` in test mode. It never copies existing office records. Retain its printed `-WorkspaceFolder` command to reopen the same copy; without that argument another empty workspace is created.

This is setup/testing, not a production activation. Standard receipts/reports use your Administrator-configured Office Information. Original agency-specific forms are archived and blocked pending custom templates. Existing databases, backups, live records and pending Troy receipt pairs remain untouched.

Regression tests: `python tests/test_empty_workspace.py`. Build artifacts, databases and resulting ZIPs stay out of Git.
