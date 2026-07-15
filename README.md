# Proteomics CSV Validation System

**Author:** Joanne Yu Yan Chan  
**Version:** 0.1.0  
**Release focus:** Initial validation implementation

## Purpose

The Proteomics CSV Validation System is a local, rule-based Python prototype for technical review of synthetic processed-sample CSV files before downstream analysis. Target users are technical reviewers, data analysts, laboratory personnel, and project personnel who review synthetic CSV inputs.

Version 0.1.0 includes:

- CSV ingestion and parse-integrity checks
- required-column schema validation
- detection of missing and duplicate `sample_id` values
- deterministic finding order and summary counts
- Markdown technical review report generation
- automated verification with baseline and seeded-error fixtures

Processing order:

```text
synthetic CSV input
→ ingestion
→ schema validation
→ identifier validation
→ finding aggregation
→ Markdown report
```

## Version 0.1.0 scope

Version 0.1.0 checks CSV structure and `sample_id` values with a named, versioned validation profile.

Excluded work:

- raw LC-MS and vendor-format file processing
- mzML and mzXML parsing
- imputation and normalization
- batch correction
- statistical analysis
- biological or clinical interpretation
- regulatory decision-making
- formal repository or SDRF conformance checks
- institutional records
- patient, participant, and clinical data
- proprietary laboratory data
- passwords, access tokens, and other credentials
- database and cloud upload
- production deployment
- continuous deployment

Exit status `0` confirms completed validation and report publication. Runs with schema or identifier findings return `0`. The reviewer decides whether an input file is acceptable for later work.

## Synthetic data and validation profile

Store synthetic fixture files in `data/synthetic/`.

Built-in profile:

- profile ID: `proteomics_processed_sample_summary`
- profile version: `0.1.0`
- descriptor schema version: `1.0.0`
- file grain: one study per file
- record grain: one processed sample-summary record per row
- record key: exact, case-sensitive `sample_id`

Required columns:

1. `study_id`
2. `sample_id`
3. `experimental_condition`
4. `sample_preparation_batch`
5. `quantified_protein_group_count`
6. `protein_group_intensity_sum`

## Repository structure

```text
data/
  expected/       reviewed expected findings
  synthetic/      synthetic CSV fixtures
src/
  proteomics_csv_validation/
    profiles/     versioned profile files and loader
    validators/   schema and identifier validators
    aggregate.py  deterministic finding order and summary counts
    cli.py        command-line interface
    ingest.py     CSV ingestion and input checks
    pipeline.py   validation workflow
    report.py     Markdown report rendering and publication
tests/            unit, CLI, pipeline, packaging, report, and end-to-end tests
README.md         setup, use, scope, and verification documentation
pyproject.toml    build, package, command, and test configuration
```

`.gitignore` excludes virtual environments, caches, generated package metadata, build artifacts, and generated reports.

## Environment

- declared Python support: Python 3.11 or newer
- verified local runtime: macOS with Python 3.14.5
- third-party runtime dependencies: none
- development dependency: `pytest>=8.0,<9`

## Installation

Run the commands from the repository root.

### macOS or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

### Windows PowerShell

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The `dev` extra installs pytest for local verification.

## Verification

Confirm the installed application version:

```bash
proteomics-csv-validate --version
```

Expected output:

```text
proteomics-csv-validate 0.1.0
```

Run the complete automated test suite:

```bash
python -m pytest
```

Verified result for version 0.1.0:

```text
67 passed
```

## Distribution build and verification

Build the source distribution and wheel:

```bash
python -m pip install --upgrade build
python -m build
```

The build writes both archives to `dist/`.

Version 0.1.0 distribution checks passed:

- successful source-distribution and `py3-none-any` wheel builds
- matching hashes for the source and packaged profile resource
- wheel installation in an isolated Python 3.14.5 environment
- installed package version and console entry point
- baseline and seeded-error execution outside the repository
- reports omitted the local repository path

## Command-line use

Display command help:

```bash
proteomics-csv-validate --help
```

### Baseline fixture

Run the baseline fixture:

```bash
proteomics-csv-validate \
  data/synthetic/baseline_valid.csv \
  --output reports/baseline_report.md
```

Expected key lines:

```text
status: completed
rows: 8
total_findings: 0
category_counts:
  ingestion: 0
  schema: 0
  identifier: 0
```

### Seeded-error fixture

Run the seeded-error fixture:

```bash
proteomics-csv-validate \
  data/synthetic/seeded_errors.csv \
  --output reports/seeded_report.md
```

Expected key lines:

```text
status: completed
rows: 8
total_findings: 4
category_counts:
  ingestion: 0
  schema: 1
  identifier: 3
```

The seeded fixture produces four findings:

- missing required column `study_id`
- duplicate `sample_id` value `S003` at CSV rows 4 and 5
- missing `sample_id` at CSV row 9

The command creates a missing output parent directory and protects existing reports from replacement.

Supply `--overwrite` to replace the named report:

```bash
proteomics-csv-validate \
  data/synthetic/seeded_errors.csv \
  --output reports/seeded_report.md \
  --overwrite
```

Run the package as a Python module:

```bash
python -m proteomics_csv_validation INPUT --output OUTPUT
```

## Exit codes

- `0`: validation and report publication completed, including completed runs with findings
- `1`: unexpected internal failure
- `2`: invalid command-line usage
- `3`: input access failure or validation stopped after a fatal ingestion finding
- `4`: profile-definition failure
- `5`: report-publication failure

## Repository workflow

- repository visibility: private
- reviewed default branch: `main`
- change-testing branch: `development`
- version 0.1.0 verification: local test execution
- planned CI platform: GitHub Actions
- continuous deployment: excluded from the capstone scope

## Planned modules

- missingness validation beyond `sample_id`
- batch and group distribution review
- quantitative and threshold validation
- PHI or PII-style field-name detection

## Command-line use

Baseline synthetic input:

```text
proteomics-csv-validate data/synthetic/baseline_valid.csv --output reports/baseline_report.md
```

Seeded-error synthetic input:

```text
proteomics-csv-validate data/synthetic/seeded_errors.csv --output reports/seeded_report.md
```

An existing distinct report is protected by default. Use `--overwrite` only after reviewing the target path.

Equivalent module execution:

```text
python3 -m proteomics_csv_validation INPUT --output OUTPUT
```

## Exit status

- `0`: completed validation and report publication, including completed runs with findings
- `1`: unexpected internal failure
- `2`: invalid command-line usage
- `3`: input access failure or validation stopped after a fatal ingestion finding
- `4`: profile-definition failure
- `5`: report-publication failure

Schema or identifier findings are technical review evidence and do not create a nonzero exit status.

## Current automation status

GitHub is the repository platform. Hosted continuous integration through GitHub Actions remains proposed and is not operational in version 0.1.0. Continuous deployment remains outside the capstone scope.
