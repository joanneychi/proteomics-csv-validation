# Local Wheel Deployment Plan

## Selected method

Deploy `proteomics-csv-validation` version `0.5.0` as its verified wheel inside a dedicated Python virtual environment on an authorized local workstation.

The base command-line interface retains zero third-party runtime dependencies. The optional browser application uses the same local package with the `web` extra, binds to loopback only, stores durable run and configuration state in a local SQLite database, and stores Result Bundle artifacts on the local filesystem. The deployment does not create a hosted service, remote API, cloud upload path, or continuous-deployment pipeline.

## Prerequisites

- Python 3.11 or newer
- `venv`
- `pip`
- local file-system access
- verified release wheel
- authorized compatible CSV inputs

Required runtime environment variables: none.

## Artifact verification

Compare the wheel with the published SHA-256 record before installation.

```bash
shasum -a 256 proteomics_csv_validation-0.5.0-py3-none-any.whl
```

Expected SHA-256:

```text
d4311d4832960089efcb83906e31d2e96d1c46ee75776f58b044d1ecf45e36b8
```

Linux systems may use `sha256sum`. Windows PowerShell may use `Get-FileHash -Algorithm SHA256`.

## macOS and Linux installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --no-deps ./proteomics_csv_validation-0.5.0-py3-none-any.whl
python -m pip check
proteomics-csv-validate --version
```

## Windows PowerShell installation

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --no-deps ./proteomics_csv_validation-0.5.0-py3-none-any.whl
python -m pip check
proteomics-csv-validate --version
```

## Optional browser application

Install the same local wheel with the browser extra when the browser review workflow is required:

```bash
python -m pip install "./proteomics_csv_validation-0.5.0-py3-none-any.whl[web]"
python -m pip check
proteomics-csv-app --version
```

Installing the `web` extra may contact the configured package index to obtain its declared dependencies. `proteomics-csv-app` binds to `127.0.0.1` only and uses port `8000` by default. Launch the application with:

```bash
proteomics-csv-app
```

## Smoke-test fixture

The release wheel installs the runtime application. Obtain `baseline_valid.csv` from the certified `v0.5.0` source tree and place it in the deployment working directory.

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
| Application version | `0.5.0` |
| Python requirement | `>=3.11` |
| Runtime dependencies | none |
| Console command | `proteomics-csv-validate` |
| Optional browser command | `proteomics-csv-app` |
| Browser bind address | `127.0.0.1` only |
| Built-in profile ID | `proteomics_processed_sample_summary` |
| Default profile version | `0.2.0` |
| Reduced Metadata profile version | `0.3.0`, selected explicitly with `--profile-version 0.3.0` |
| Descriptor schema | `1.0.0` |
| Column-mapping specification | `1.0.0` |
| Report format | `1.1.0` |
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
- baseline smoke-test result;
- browser startup and loopback-bind result when the browser extra is installed.

No remote telemetry or user tracking is required.

## Rollback

1. Preserve the current environment and reports.
2. Create a separate rollback virtual environment.
3. Install the prior verified artifact.
4. Confirm the installed version.
5. Run the baseline smoke test.
6. Redirect local use to the verified rollback environment.
7. Document the reason, time, version, and verification result.

For rollback from `v0.5.0`, `v0.4.0` is the immediate prior verified release. Earlier preserved releases `v0.3.0`, `v0.2.0`, and `v0.1.0` remain historical recovery points. Select a rollback version only after confirming that its documented capabilities meet the required use case.

## Deferred deployment methods

A container remains optional future portability work. Hosted on-premises or cloud deployment remains deferred because it would require a service interface, network controls, authentication, operational monitoring, infrastructure configuration, and additional security review.

## Current official guidance checked

- Python Packaging User Guide, virtual environments and local archive installation
- [Python Packaging User Guide: Installing Packages](https://packaging.python.org/en/latest/tutorials/installing-packages/)
- [pip documentation: Requirement Specifiers](https://pip.pypa.io/en/stable/reference/requirement-specifiers/)
- [Python documentation: `venv`](https://docs.python.org/3/library/venv.html)

Retrieval date: September 1, 2026.
