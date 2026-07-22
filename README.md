# Proteomics CSV Validation System

- **Author:** Joanne Yu Yan Chan
- **Application version:** 0.2.0
- **Release focus:** Required-value missingness validation

## Purpose

The Proteomics CSV Validation System is a local Python prototype for technical review of synthetic processed-sample CSV files before downstream analysis. Technical reviewers, data analysts, laboratory personnel, and project personnel use the command to inspect configured data-quality findings.

The application performs:

- CSV ingestion and parse checks
- required-column schema validation
- missing `sample_id` validation
- duplicate `sample_id` validation
- profile-driven missing required non-key value validation
- deterministic finding aggregation
- Markdown technical-review report generation
- command-line execution
- Python package installation
- automated verification with controlled fixtures

Processing order:

```text
synthetic CSV input
→ ingestion
→ schema validation
→ identifier validation
→ required-value missingness validation
→ finding aggregation
→ Markdown report
```

## Application boundary

Version 0.2.0 evaluates CSV structure, sample identifiers, and required non-key values under named profile and rule versions.

The application excludes:

- raw LC-MS data processing
- vendor-format parsing
- mzML and mzXML parsing
- protein inference
- imputation
- normalization
- batch correction
- statistical analysis
- biological interpretation
- clinical interpretation
- regulatory decisions
- repository-format conformance claims
- SDRF-Proteomics conformance claims
- institutional records
- patient, participant, and clinical data
- proprietary laboratory data
- passwords, access tokens, and credentials
- database services
- cloud upload
- production deployment
- continuous deployment

A completed run writes a report and returns exit status `0`, including runs with findings. Dataset acceptance occurs through reviewer judgment outside the command.

## Validation profile

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

## Rule ownership

Schema validation reports required columns absent from the CSV header.

Identifier validation reports missing or duplicate `sample_id` values.

Missingness validation reports missing values in required non-key fields present in the CSV header. Field-specific missing-value policies govern blank values and values containing whitespace with no other characters.

Current rule:

```text
rule_id: missingness.required_value
rule_version: 1.0.0
finding_code: MISSINGNESS_REQUIRED_VALUE
category: missingness
severity: error
scope: row
expected_value: nonmissing
```

The ownership boundaries prevent duplicate findings for one defect.

## Repository structure

```text
data/
  expected/       reviewed expected-result oracles
  synthetic/      synthetic CSV fixtures
src/
  proteomics_csv_validation/
    profiles/     versioned profile resources and loader
    validators/   schema, identifier, and missingness validators
    aggregate.py  deterministic finding order and summary counts
    cli.py        command-line interface
    ingest.py     CSV ingestion and input checks
    pipeline.py   validation workflow
    report.py     Markdown report rendering and publication
tests/            unit, CLI, pipeline, packaging, report, and end-to-end tests
MANIFEST.in       source-distribution test and fixture inclusion
README.md         setup, use, scope, and verification record
pyproject.toml    build, package, command, and test configuration
```

`.gitignore` excludes virtual environments, caches, generated package metadata, build artifacts, and generated reports.

## Environment

- Python requirement: 3.11 or newer
- verified local runtime: macOS with Python 3.14.5
- third-party runtime dependencies: none
- development dependency: `pytest>=8.0,<9`
- package status: alpha academic prototype

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

## Version verification

```bash
proteomics-csv-validate --version
```

Expected output:

```text
proteomics-csv-validate 0.2.0
```

## Automated tests

Run the full suite:

```bash
python -m pytest
```

Verified result on Python 3.14.5 with pytest 8.4.2:

```text
75 passed
```

The suite contains unit, integration, CLI, pipeline, report, packaging, and end-to-end tests.

## Command-line use

### Baseline fixture

```bash
proteomics-csv-validate \
  data/synthetic/baseline_valid.csv \
  --output reports/baseline_report.md
```

Expected summary:

```text
status: completed
rows: 8
total_findings: 0
category_counts:
  ingestion: 0
  schema: 0
  identifier: 0
  missingness: 0
finding_code_counts:
  none
```

### Seeded schema and identifier fixture

```bash
proteomics-csv-validate \
  data/synthetic/seeded_errors.csv \
  --output reports/seeded_report.md
```

Expected summary:

```text
status: completed
rows: 8
total_findings: 4
category_counts:
  ingestion: 0
  schema: 1
  identifier: 3
  missingness: 0
finding_code_counts:
  SCHEMA_MISSING_REQUIRED_COLUMN: 1
  IDENTIFIER_DUPLICATE_SAMPLE_ID: 2
  IDENTIFIER_MISSING_SAMPLE_ID: 1
```

Seeded findings:

- missing required column `study_id`
- duplicate `sample_id` value `S003` at CSV rows 4 and 5
- missing `sample_id` at CSV row 9

### Required-value missingness fixture

```bash
proteomics-csv-validate \
  data/synthetic/required_value_missing_values.csv \
  --output reports/required_value_missing_values_report.md
```

Expected summary:

```text
status: completed
rows: 8
total_findings: 3
category_counts:
  ingestion: 0
  schema: 0
  identifier: 0
  missingness: 3
finding_code_counts:
  MISSINGNESS_REQUIRED_VALUE: 3
```

Seeded findings:

- blank `experimental_condition` at CSV row 3
- three-space `sample_preparation_batch` value at CSV row 5
- blank `protein_group_intensity_sum` at CSV row 7

The fixtures contain synthetic records. Fixture files retain their original bytes after each validation run.

## Report publication

The command creates a missing output parent directory. An existing report path blocks publication unless `--overwrite` is supplied.

```bash
proteomics-csv-validate \
  data/synthetic/required_value_missing_values.csv \
  --output reports/required_value_missing_values_report.md \
  --overwrite
```

The report records application, profile, and rule versions; input name; row count; summary counts; structured findings; technical interpretation; and scope boundaries. Reports omit absolute input and output paths.

## Module execution

```bash
python -m proteomics_csv_validation INPUT --output OUTPUT
```

## Exit codes

- `0`: validation and report publication completed
- `1`: unexpected internal failure
- `2`: invalid command-line usage
- `3`: input access failure or validation stopped after a fatal ingestion finding
- `4`: profile-definition failure
- `5`: report-publication failure

Findings from completed runs retain exit status `0`.

## Distribution build

Install the build frontend:

```bash
python -m pip install --upgrade build
```

Build the source distribution and wheel:

```bash
python -m build
```

The build writes archives to `dist/`.

Release audit checklist for version 0.2.0:

- source-distribution creation
- source-distribution test and fixture inclusion
- `py3-none-any` wheel creation
- package metadata version `0.2.0`
- built-in profile inclusion
- isolated wheel installation
- installed command execution
- full test execution from the source tree
- baseline fixture execution outside the repository
- seeded-error fixture execution outside the repository
- Required-value fixture execution outside the repository
- report path sanitization
- archive hashes

## Repository workflow

- repository visibility: private
- reviewed branch: `main`
- integrated development branch: `development`
- verified baseline tag: `v0.1.0`
- development target: `v0.2.0`
- hosted CI status: proposed
- continuous deployment status: excluded

The `v0.1.0` release records the verified initial validation baseline.

## Deferred modules

- batch and group distribution review
- quantitative datatype and range validation
- documented threshold validation
- outlier review
- PHI or PII-style field-name detection

Each deferred module requires a written scientific contract, direct tests, interaction tests, controlled fixtures, expected-result evidence, and documentation before integration.

## Automation status

GitHub is the repository platform. GitHub Actions has no active workflow in version 0.2.0. Local pytest execution is the automated test evidence. Continuous deployment and production deployment are outside the project scope.
