# Check Management

Private source repository for the configurable Windows check-management application. Current release: **1.0.0-rc64**.

The application supports separate office workspaces, case entry, payment allocation, receipt generation/reprints, reporting, named Staff/Administrator accounts and SQLite backups. rc63 permits Staff to create new cases and record payments while preserving Administrator restrictions on existing-record edits, other master-record creation, settings, users and reconciliation.

## Source layout

- `source/app.py`: application interface and SQLite store.
- `source/legacy_work.py`, `source/case_window.py`: imported case workflows and access checks.
- `source/login.py`, `source/users.py`: authentication, roles and office settings.
- `source/legacy_functions.py`, `source/reporting.py`: reports and registers.
- `source/deployment.py`, `source/divisions.py`: startup, office selection and output modes.
- `source/build_desktop.py`, `source/Build-Windows.ps1`, `source/installer.iss`: Windows build and installer.
- `source/licenses/`, `source/THIRD-PARTY-NOTICES.txt`: bundled dependency notices.

Reference JSON files contain schema definitions, report layouts and bank/WC/ZIP reference data. Real office databases and credentials are not included. Historical VERSION files and BUILD-NOTES may describe earlier releases; the current release constants are in deployment.py and installer.iss.

## Windows development build

Use Windows x64, Python 3.14 including Tcl/Tk, PyInstaller and Inno Setup 7. Packaged rc63 checks ran with Python 3.14.10. Install build dependencies in a virtual environment:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-build.txt
cd source
.\Build-Windows.ps1 -InnoCompiler 'C:\Program Files\Inno Setup 7\ISCC.exe'
```

Output: `source/build/installer/Check-Management-Setup-rc64.exe`.
The installer is unsigned. Rebuilt binaries can differ from the previously verified installer hash; do not bypass a deployment tool's hash guard.

## Disposable self-test

From `source`, run the built payload with an absolute report path in a development directory:

```powershell
& '.\build\frozen\PikeCountyWC\PikeCountyWC.exe' --self-test 'C:\Development\rc63-self-test.json'
```

The self-test creates fictional data beside the report and checks authentication, payments, report generation, concurrent connections and backup/reopen behavior. Keep test data outside version control. Do not run the installer or a default application launch against an operational server merely to review code.

## Repository boundaries

The `.gitignore` excludes runtime databases, legacy files, exports, archives, credentials, generated binaries and local deployment helpers/evidence. These exclusions are preventive and are not a substitute for reviewing staged changes. Auth code is included; actual account databases and passwords are not.

Keep this repository **private**. Use fictional fixtures in development. Do not commit real case details, receipt exports, source backups, authentication data, internal recovery manifests or encryption keys. Review third-party notices and ownership before changing visibility or licensing. No top-level distribution license is asserted by this preparation.

Local `tools/` and `evidence/` from the source ZIP remain available on disk but are intentionally ignored because they contain deployment-specific information.

Production deployment remains a separately authorized operation. The three pending Troy receipt pairs remain pending; source control preparation does not authorize reconciliation or live changes.

## Saving future changes

This project tracks `main` in the private GitHub repository. Before starting new work, run `git pull --ff-only` with a clean working folder. After editing, review the changes and stage only the intended files:

```powershell
git diff
git add README.md
git diff --cached
git commit -m "Update project documentation"
git push
```

Use the actual changed file paths when saving code changes. A push updates source control only; it does not install or deploy the application.

## Custom organization headings (rc64)

Sign in as an Administrator and open **Office Information**. Set Organization / office name, optional heading lines 2-4, and an optional workspace name. Fill in your own address and contact information and choose **Save Office Information**. New banners, standard receipts and reports use those values. Blank identity fields show only Check Management; no DA, judicial circuit, Alabama or county heading is inferred. State/region is optional. Existing fees, numbering and legacy fields are preserved when omitted from an office-information save.

Workspace selectors use Office 1 and Office 2 by default. Internal troy/enterprise keys, executable filename, Windows groups and existing data paths remain compatibility identifiers; they are not printed organization names. Existing installations can keep their prior install directory; new installations default to Check Management.

Archived original agency forms contain specialized wording/signatures and are blocked from rendering in this reusable edition until organization-specific templates are prepared and reviewed. This does not delete templates or alter saved original documents. Standard receipt/report output remains configurable. Previously exported files are not rewritten. New heading settings apply when documents are generated, including reprints; historic financial snapshots remain unchanged.

This release changes the heading/configuration plan; prior rc63 office approval is not approval to install rc64. No live database is migrated, no production deployment is performed and the three Troy receipt pairs remain pending.

Run the disposable custom-organization and permission checks with `python tests/test_custom_organization.py` from the repository root. They create temporary fictional databases and do not inspect production.

## Fresh empty workspace

See [the empty-workspace guide](docs/empty-workspace.md) for the corrected v2 packaging workflow. It starts with zero users and business records, retains standard reference lists, excludes SQLite sidecars from the kit, and preserves existing databases/backups.
