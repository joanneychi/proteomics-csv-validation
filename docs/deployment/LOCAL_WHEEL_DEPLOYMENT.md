# Local Wheel Deployment Plan

## Selected method

Deploy `proteomics-csv-validation` version `0.2.0` as its verified wheel inside a dedicated Python virtual environment on an authorized local workstation.

This method matches the existing command-line architecture, local-file workflow, zero third-party runtime dependencies, and synthetic-data boundary. It does not create a hosted service, production web application, database, API, or continuous-deployment pipeline.

## Prerequisites

- Python 3.11 or newer
- `venv`
- `pip`
- local file-system access
- verified release wheel
- authorized synthetic CSV inputs

Required runtime environment variables: none.

## Artifact verification

Compare the wheel with the published SHA-256 record before installation.

```bash
shasum -a 256 proteomics_csv_validation-0.2.0-py3-none-any.whl
```

Expected SHA-256:

```text
8079febb626c8cd532542eefd2230d4e10cf61a0d6145f04ff5d1acfc96a7fc9
```

Linux systems may use `sha256sum`. Windows PowerShell may use `Get-FileHash -Algorithm SHA256`.

## macOS and Linux installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --no-deps proteomics_csv_validation-0.2.0-py3-none-any.whl
python -m pip check
proteomics-csv-validate --version
```

## Windows PowerShell installation

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --no-deps proteomics_csv_validation-0.2.0-py3-none-any.whl
python -m pip check
proteomics-csv-validate --version
```

## Smoke-test fixture

The wheel contains the runtime package and built-in profile, but it does not contain the project’s top-level test fixtures. Obtain `baseline_valid.csv` from the certified `v0.2.0` source distribution or repository and place it in the deployment working directory.

Verify the fixture before use:

```bash
shasum -a 256 baseline_valid.csv
```

Expected SHA-256:

```text
9c6c85249787f728418a24653d10621b923c3c784618d867ce2a9a4e3044cbee
```

Linux may use `sha256sum`. Windows PowerShell may use `Get-FileHash -Algorithm SHA256`.

## Smoke test

```bash
proteomics-csv-validate baseline_valid.csv --output baseline_smoke_report.md --overwrite
```

Required result:

```text
rows: 8
total_findings: 0
```

## Configuration

| Configuration item | Verified value |
|---|---|
| Application version | `0.2.0` |
| Python requirement | `>=3.11` |
| Runtime dependencies | none |
| Console command | `proteomics-csv-validate` |
| Built-in profile | `proteomics_processed_sample_summary` |
| Profile version | `0.1.0` |
| Descriptor schema | `1.0.0` |
| Report format | `1.0.0` |
| Required environment variables | none |
| Input encoding | UTF-8, optional BOM |
| Maximum input bytes | 10,000,000 |
| Maximum data rows | 100,000 |
| Maximum columns | 1,000 |
| Existing output default | refuse replacement |
| Explicit replacement | `--overwrite` |

## Monitoring

Local monitoring records:

- installed application version;
- wheel checksum verification;
- installation and `pip check` status;
- command exit status;
- processed row and finding counts;
- report-publication success;
- unexpected exception output;
- baseline smoke-test result.

No remote telemetry or user tracking is required.

## Rollback

1. Preserve the current environment and reports.
2. Create a separate rollback virtual environment.
3. Install the prior verified artifact.
4. Confirm the installed version.
5. Run the baseline smoke test.
6. Redirect local use to the verified rollback environment.
7. Document the reason, time, version, and verification result.

Version `v0.1.0` is the historical rollback baseline. An installable `v0.1.0` artifact must be retained or rebuilt from its preserved tag before operational rollback is needed.

## Deferred deployment methods

A container remains optional future portability work. Hosted on-premises or cloud deployment remains deferred because it would require a service interface, network controls, authentication, operational monitoring, infrastructure configuration, and additional security review.

## Current official guidance checked

- Python Packaging User Guide, virtual environments and local archive installation
- Python Packaging User Guide, packaging flow and wheel installation
- Python documentation, `venv`

Retrieval date: July 28, 2026.
