# Proteomics CSV Validation System

`proteomics-csv-validation` is a local Python validation system for processed-sample proteomics CSV files. The command-line interface (CLI) checks required columns, sample identifiers, required values, and configured header mappings. An optional browser application, served on loopback only, adds result and evidence review, history, comparison, and exact Result Bundle export. Findings identify structural conditions for review before downstream analysis.

The system was developed during an eight-week graduate capstone and reached application version `0.4.0` by the end of the project.

- **Author:** Joanne Y. Chan
- **Application version:** `0.4.0`
- **Default profile:** `0.2.0`
- **Reduced Metadata profile:** `0.3.0`
- **Repository regression suite:** 342 passing tests
- **Python:** `>=3.11`
- **Development status:** Alpha

## Quick start

Begin with the project files already available locally. Run the commands from the repository root, the folder containing `pyproject.toml` and `README.md`.

### Prerequisite

Python 3.11 or newer is required. Editable installation may contact a package index for build requirements and the optional development or browser dependencies selected below. The base command-line runtime uses only the Python standard library.

macOS or Linux:

```bash
python3 --version
```

Windows PowerShell:

```powershell
py --version
```

### Create an isolated environment and install the project

macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,web]"
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,web]"
```

`-e` installs the current project in editable mode. `.[dev]` adds pytest and httpx2 for repository verification, while `.[web]` adds the optional browser-application dependencies. The combined `.[dev,web]` installation supports the complete repository suite and the local browser application.

The base command-line runtime retains zero third-party dependencies. For an editable CLI-only installation, use `python -m pip install -e .`. Leave `.venv` active for the commands below.

### Verify the installed commands

```bash
proteomics-csv-validate --version
proteomics-csv-validate --help
proteomics-csv-app --version
proteomics-csv-app --help
```

Expected version output:

```text
proteomics-csv-validate 0.4.0
proteomics-csv-app 0.4.0
```

### Run the optional local browser application

```bash
proteomics-csv-app
```

`proteomics-csv-app` binds to loopback only (`127.0.0.1`) and uses port `8000` by default. Open `http://127.0.0.1:8000` in a browser. Use `proteomics-csv-app --port PORT` to select another local port from 1024 through 65535.

Default profile `0.2.0` applies to the commands below. A profile defines required fields, and a finding is one reported condition at a file or row location.

The examples exercise `schema` findings for missing required columns, `identifier` findings for blank or duplicate `sample_id`, and `missingness` findings for blank required values outside the `sample_id` key field. Console summaries also include `ingestion` for fatal input-processing findings. Strict mapping mode evaluates source headers as written.

### Run the valid baseline

Commands below are single-line commands compatible with macOS/Linux shells and Windows PowerShell after environment activation.

```text
proteomics-csv-validate data/synthetic/baseline_valid.csv --output reports/baseline_report.md --overwrite
```

Baseline execution processes eight records and reports zero findings. Expected output includes:

```text
status: completed
rows: 8
profile_version: 0.2.0
mapping_mode: strict
mapping_resolution: completed
mapped_columns: 0
total_findings: 0
```

`proteomics-csv-validate` writes the report to `reports/baseline_report.md` and preserves the input CSV. Each example includes `--overwrite` for repeat runs using the listed report paths; omit the flag to protect an existing report.

### Run seeded structural findings

```text
proteomics-csv-validate data/synthetic/seeded_errors.csv --output reports/seeded_errors_report.md --overwrite
```

Expected output includes:

```text
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

`seeded_errors.csv` contains one missing required column, two duplicate `sample_id` findings, and one blank `sample_id` finding.

### Run required-value missingness

```text
proteomics-csv-validate data/synthetic/required_value_missing_values.csv --output reports/required_value_missing_values_report.md --overwrite
```

Expected output includes:

```text
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

`required_value_missing_values.csv` contains three required non-key values classified as missing with default profile `0.2.0`. Across the three examples, outputs cover the zero-finding case plus schema, identifier, and missingness findings.

### Verify the repository suite

```bash
python -m pytest
```

Expected result: all tests pass.

For verified wheel installation and checksum procedures, see [LOCAL_WHEEL_DEPLOYMENT.md](docs/deployment/LOCAL_WHEEL_DEPLOYMENT.md).

## Input requirements

| Input property | Requirement |
|---|---|
| File | Accessible regular `.csv` file |
| Encoding | UTF-8 with an optional byte-order mark (BOM) |
| Header | Nonblank, with unique case-sensitive column names |
| Record layout | One logical data record per physical line |
| Maximum file size | 10,000,000 bytes |
| Maximum data records | 100,000 |
| Maximum columns | 1,000 |
| Column order | Any order |
| Additional columns | Accepted when column names are unique; validators inspect profile-defined fields |
| Input and output paths | Different files |

The selected profile determines required profile fields. Header mapping resolves supported source-header names to those fields.

## How to read the version and result numbers

| Term | Meaning in this project |
|---|---|
| **Application version** | Version embedded in the executable software, such as `0.4.0` |
| **Release tag** | Git tag identifying a release snapshot, such as `v0.4.0` |
| **Profile** | Versioned validation contract defining the processed-sample fields and which fields are required |
| **Record** | One processed sample-summary row in an input CSV |
| **Key field** | Record identifier field; `sample_id` is the key field in the built-in profiles |
| **Finding** | One rule-detected condition at one applicable file or row location; a record may produce more than one finding |

Application versions and profile versions advance independently. Release tag `v0.4.0` identifies application version `0.4.0`; profile `0.2.0` is the default, and `--profile-version 0.3.0` selects Reduced Metadata profile `0.3.0`.

## Release progression

| Release tag | Application version | Default profile | Profiles packaged | Principal application change | Regression tests at tag |
|---|---|---|---|---|---:|
| `v0.1.0` | `0.1.0` | `0.1.0` | `0.1.0` | Initial local validation workflow | 67 |
| `v0.2.0` | `0.2.0` | `0.1.0` | `0.1.0` | Required-value missingness validation | 75 |
| `v0.3.0` | `0.3.0` | `0.2.0` | `0.1.0`, `0.2.0` | Automatic and explicit column mapping | 98 |
| `v0.4.0` | `0.4.0` | `0.2.0` | `0.1.0`, `0.2.0`, `0.3.0` | Explicit profile selection and Reduced Metadata profile `0.3.0` | 111 |

`Profiles packaged` lists the profile resources included with each release. Application version `0.3.0` packaged profiles `0.1.0` and `0.2.0` but always loaded profile `0.2.0`. Release `v0.4.0` added `--profile-version` to select a registered profile. Omitting the option defaults to profile `0.2.0`; `--profile-version 0.3.0` selects the Reduced Metadata contract.

`v0.4.0` snapshot contains 111 regression tests. Subsequent tests-only ingestion hardening increased the maintained repository suite to 126 tests without changing application runtime source. The current repository includes the local browser review workflow while retaining application version `0.4.0`; the current regression count is summarized above. The release table therefore ends at `v0.4.0` until a newer release is created.

## Validation scope

When ingestion and header resolution complete, the application applies three structural validator groups:

- **Schema:** required profile columns missing from the CSV header
- **Identifier:** blank or duplicate `sample_id` values
- **Missingness:** blank required values in non-key fields whose columns are present in the CSV

Fatal ingestion findings are reported separately and stop downstream validation. Required-value missingness uses rule `missingness.required_value` version `1.0.0` and finding code `MISSINGNESS_REQUIRED_VALUE`.

### Out of scope

Excluded functions:

- raw LC-MS processing
- vendor-format, mzML, or mzXML processing
- protein inference
- imputation or normalization
- batch correction
- statistical analysis
- biological or clinical interpretation
- regulatory decisions
- repository-conformance assessment
- hosted-service operation
- cloud upload
- production deployment

## Processed-sample profiles

`proteomics_processed_sample_summary` is the built-in profile ID. Descriptor schema version `1.0.0` defines the JSON profile structure. `sample_id` is the exact, case-sensitive record key. Each record represents a processed sample-summary row, and each file represents a study.

### Profile evolution

Profile versions identify the record contract applied during validation.

| Profile | Role in application history | Required-field policy | What changed |
|---|---|---|---|
| `0.1.0` | Default in applications `0.1.0` and `0.2.0` | Six required fields | Original profile; descriptions identify synthetic one-study records |
| `0.2.0` | Default in applications `0.3.0` and `0.4.0` | Six required fields | Descriptions identify study-level records; validation requirements are unchanged from `0.1.0` |
| `0.3.0` | Introduced in application `0.4.0` as the Reduced Metadata option | Four required fields; condition and preparation batch optional | Adds two optional metadata fields |

### Exact profile `0.1.0` to `0.2.0` change

Profiles `0.1.0` and `0.2.0` have identical six-field validation requirements. Their JSON resources differ in three values: `profile_version` and two descriptions. Profile `0.2.0` uses study-level language in the two changed descriptions.

| JSON property | Profile `0.1.0` | Profile `0.2.0` |
|---|---|---|
| `profile_version` | `0.1.0` | `0.2.0` |
| Top-level `description` | `Synthetic one-study processed-sample records for local technical data-quality review.` | `One-study processed-sample records for local technical data-quality review.` |
| `study_id.description` | `Identifier for the synthetic study represented by the file.` | `Identifier for the study represented by the file.` |

Unchanged profile properties are descriptor schema version, profile ID, entity type, title, record grain, file grain, field order and names, logical types, required flags, missing-value policies, key/factor/batch field designations, quantitative metric definitions, and CSV-dialect settings.

### Required-field comparison

| Field | Profile `0.1.0` | Profile `0.2.0` | Profile `0.3.0` |
|---|---|---|---|
| `study_id` | Required | Required | Required |
| `sample_id` | Required | Required | Required |
| `experimental_condition` | Required | Required | Optional |
| `sample_preparation_batch` | Required | Required | Optional |
| `quantified_protein_group_count` | Required | Required | Required |
| `protein_group_intensity_sum` | Required | Required | Required |

Profile `0.3.0` changes requiredness for `experimental_condition` and `sample_preparation_batch`. With profile `0.3.0`, either metadata field may be supplied or omitted. Omission of either optional field yields zero schema and required-value missingness findings for that field. Schema and required-value missingness checks apply to the four required fields.

## Profile selection

`--profile-version` selects the validation contract. `--auto-map` and `--column-map` resolve source headers against that contract. Profile selection sets field requirements; mapping resolves header names.

In the usage examples, replace `input.csv`, `mapping.json`, and `report.md` with your local paths. Examples assume field names from the selected profile unless a mapping option is shown.

Omitting `--profile-version` defaults to profile `0.2.0`; `--profile-version 0.3.0` selects Reduced Metadata. Profile loading occurs before metadata validation. Source values are preserved; report metadata records the selected profile.

```text
proteomics-csv-validate input.csv --profile-version 0.3.0 --output report.md
```

## Column mapping

A canonical profile field is a field name defined by the selected profile, such as `sample_id`. Column mapping resolves source headers to canonical field names after profile loading and CSV ingestion, before validation. Mapping changes header interpretation and preserves source values and the source CSV. Findings report physical CSV row numbers.

### Strict mode

Strict mode uses source headers exactly as provided:

```text
proteomics-csv-validate input.csv --output report.md
```

### Automatic mapping

`--auto-map` resolves conservative header-name variants and exact profile field titles to canonical profile fields:

```text
proteomics-csv-validate input.csv --auto-map --output report.md
```

Dataset-specific labels or headers that automatic mapping cannot resolve unambiguously require an explicit mapping file.

### Explicit mapping

Explicit mapping reads a versioned JSON file. Mapping keys are canonical profile fields; mapping values are source headers. Save the JSON example as `mapping.json` in the repository root, or choose another path and pass that path to `--column-map`.

```json
{
  "mapping_specification_version": "1.0.0",
  "columns": {
    "sample_id": "Sample Name",
    "experimental_condition": "Condition"
  }
}
```

```text
proteomics-csv-validate input.csv --column-map mapping.json --output report.md
```

`--auto-map` and `--column-map` are mutually exclusive. Explicit mapping files specify mapping specification version `1.0.0`.

## Processing path

```text
CLI invocation
→ load selected or default profile
→ ingest CSV
→ resolve headers: strict, automatic, or explicit
→ schema validation
→ identifier validation
→ required-value missingness validation
→ finding aggregation
→ render Markdown report
→ publish report atomically
```

Atomic publication writes the complete report to a temporary file in the destination directory, then replaces the target.

## PXD060583 public-data structural evaluation

### Source and derivation

Evaluation of PXD060583 covered 42 processed-sample records derived from 42 MaxQuant label-free quantification (LFQ) experiment columns in the publicly deposited ProteomeXchange dataset `PXD060583`. In each derived record, `study_id` records the ProteomeXchange accession and `sample_id` records the MaxQuant experiment label. For each LFQ intensity column, `quantified_protein_group_count` counted supplied positive values and `protein_group_intensity_sum` summed those values.

Derived processed-sample CSV files were the application inputs. MaxQuant `proteinGroups.txt` supplied source material; the CLI input was the derived CSV files.

### Worked example: one record, two findings

Each finding represents one rule-detected condition at one location. Records can produce multiple findings.

Review of the public source material left `experimental_condition` and `sample_preparation_batch` unresolved. One source-derived record illustrates how the two current profile contracts classify those fields.

| Field | Source-derived state | Profile `0.2.0` | Profile `0.3.0` |
|---|---|---|---|
| `study_id` | Present | Required → 0 findings | Required → 0 findings |
| `sample_id` | Present | Required → 0 findings | Required → 0 findings |
| `experimental_condition` | Unresolved from reviewed public source material; blank in the six-field representation | Required → **1 finding** | Optional → 0 findings |
| `sample_preparation_batch` | Unresolved from reviewed public source material; blank in the six-field representation | Required → **1 finding** | Optional → 0 findings |
| `quantified_protein_group_count` | Present | Required → 0 findings | Required → 0 findings |
| `protein_group_intensity_sum` | Present | Required → 0 findings | Required → 0 findings |

Execution with profile `0.2.0` covered six columns with the two metadata values blank and produced two `MISSINGNESS_REQUIRED_VALUE` findings for the record. Execution with profile `0.3.0` covered four columns, omitted those optional metadata fields, and produced zero findings for those fields. Evaluation preserved the derived input metadata values.

Across all 42 records:

**42 records × 2 missing required values per record = 84 findings with profile `0.2.0`.**

`42` counts **records**; `84` counts **field-level findings**: 42 for `experimental_condition` plus 42 for `sample_preparation_batch`.

### Application and profile comparison

All three rows cover 42 source-derived processed-sample records.

| Application version | Selected profile | Records | Findings | Interpretation |
|---|---|---:|---:|---|
| `0.3.0` | default `0.2.0` | 42 | 84 | Six-field profile requires condition and batch |
| `0.4.0` | default `0.2.0` | 42 | 84 | Application `0.4.0` also reports 84 with the default profile |
| `0.4.0` | selected `0.3.0` | 42 | 0 | Result changes when the Reduced Metadata contract is selected |

Application version `0.4.0` produces 84 findings with default profile `0.2.0` and zero with selected profile `0.3.0`, where the two unresolved metadata fields are optional. Mapping resolves headers, and the selected profile defines requiredness. PXD060583 source-derived metadata values are preserved.

### Controls and interpretation

Applying default profile `0.2.0` to a four-column PXD060583 representation reported two missing required columns: `experimental_condition` and `sample_preparation_batch`. Applying profile `0.3.0` to a six-column control produced zero findings when those optional fields were blank. Blanking required `quantified_protein_group_count` in the negative control produced one `MISSINGNESS_REQUIRED_VALUE` finding with profile `0.3.0`. Across the PXD060583 inputs, strict, automatic, and explicit mapping produced identical finding totals for each selected profile.

Zero findings means the implemented structural rules emitted zero findings for the executed input with the selected profile and options. PRIDE/SDRF conformance, repository acceptance, normalization quality, scientific validity, and biological interpretation require dedicated evidence.

CLI input is a processed-sample CSV. PRIDE archives, MaxQuant `proteinGroups.txt` files, Excel workbook files, and raw LC-MS files fall outside the CLI input type.

## Example fixtures

Bundled fixture records are synthetic with fixed expected finding counts. `Rows` is the number of data records. Fixture descriptions use physical CSV row numbers, with the header at row 1.

| Fixture | Rows | Expected findings |
|---|---:|---:|
| `baseline_valid.csv` | 8 | 0 |
| `seeded_errors.csv` | 8 | 4 |
| `required_value_missing_values.csv` | 8 | 3 |

`seeded_errors.csv` omits required `study_id` from the header, repeats `sample_id` value `S003` at CSV rows 4 and 5, and contains a blank `sample_id` at row 9.

`required_value_missing_values.csv` contains a blank `experimental_condition` at CSV row 3, a whitespace-only `sample_preparation_batch` at row 5, and a blank `protein_group_intensity_sum` at row 7.

## Reports

Report format `1.1.0` records:

- application and profile identities
- mapping mode and resolved header mappings
- configured rule identities
- row and finding counts
- input filename
- observed and expected values
- technical message
- finding-level rule identity
- technical interpretation
- implemented checks and excluded functions

A missing output parent directory is created before report writing. Report publication is atomic: the application writes the completed report to a temporary file in the destination directory, then replaces the target. Existing report files require `--overwrite`.

Reports record filenames. Absolute input, output, and mapping-file paths are omitted.

## Exit codes

Findings are review results. Completed validation returns exit status `0` even when findings are reported.

CLI process exit codes:

- `0`: validation and report writing completed
- `1`: unexpected internal failure
- `2`: invalid command-line usage
- `3`: input access failure or fatal ingestion finding stopped validation
- `4`: profile-definition failure
- `5`: report-writing failure
- `6`: column-mapping configuration or resolution failure

## Tests and continuous integration (CI)

Run the complete suite:

```bash
python -m pytest
```

The complete repository suite covers both command-line and browser workflows. `tests/test_ingest.py` contains 20 ingestion regression tests; the `v0.4.0` tagged snapshot contained 5. Fifteen added ingestion tests exercise existing ingestion behavior involving argument types, CSV-extension checks, file access, UTF-8 byte-order-mark (BOM) and NUL-byte handling, parser failures, header validation, byte, row, and column limits, blank records, and record width.

The suite exercises validator logic, aggregation, ingestion, profile loading, profile selection, column mapping, CLI behavior, browser review, durable run lifecycle, Result, History, Compare, and Export workflows, security boundaries, pipeline integration, report rendering, packaging, and end-to-end execution.

GitHub Actions runs seven jobs for pull requests targeting `main` and for pushes to `main`: six test environments and a build-artifacts job. Six test environments cover Ubuntu with Python 3.11, 3.12, 3.13, and 3.14; Windows with Python 3.14; and macOS with Python 3.14. Manual dispatch is also available. Release publication is outside the workflow.

## Repository structure

```text
.github/
  workflows/
    cross-platform.yml
data/
  expected/       expected-result JSON records
  synthetic/      synthetic CSV fixtures
docs/
  deployment/
    LOCAL_WHEEL_DEPLOYMENT.md
src/
  proteomics_csv_validation/
    application/  browser-review application services
    domain/       run-lifecycle and evidence domain records
    infrastructure/  SQLite ledger and result-artifact persistence
    profiles/     versioned profile resources and loader
    validators/   schema, identifier, and missingness validators
    web/          loopback browser routes, templates, static assets, and security
    aggregate.py  finding ordering and summary counts
    cli.py        command-line interface
    column_mapping.py  header mapping
    ingest.py     CSV ingestion and file checks
    pipeline.py   validation workflow
    report.py     Markdown rendering and atomic report publication
tests/            automated test suite
MANIFEST.in       source-distribution inclusion rules
README.md         project documentation
pyproject.toml    package and test configuration
```

## Optional: build distribution artifacts

Building distribution artifacts is optional for local validation. To build a source distribution and wheel from the repository root:

```bash
python -m pip install build
python -m build
```

`python -m build` writes the source distribution and wheel to `dist/`.

## Help and local troubleshooting

Show all CLI options:

```bash
proteomics-csv-validate --help
```

Verify the active installation:

```bash
proteomics-csv-validate --version
```

Common local setup conditions:

| Condition | Action |
|---|---|
| CLI command unavailable after installation | Confirm that `.venv` is active, then rerun the version check |
| Browser application reports missing web dependencies | Reinstall the editable project with `.[web]` or `.[dev,web]` |
| Python version below 3.11 | Switch to a supported interpreter |
| Report path already exists | Add `--overwrite` when replacement is intended |

If Windows PowerShell blocks `Activate.ps1`, run the virtual-environment executables directly and leave the system execution policy unchanged. From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,web]"
.\.venv\Scripts\proteomics-csv-validate.exe --version
.\.venv\Scripts\proteomics-csv-app.exe --version
```

For the PowerShell fallback, run `.\.venv\Scripts\proteomics-csv-validate.exe` for CLI commands, `.\.venv\Scripts\proteomics-csv-app.exe` for the local browser application, and `.\.venv\Scripts\python.exe` for Python commands.

For the detailed wheel-installation, checksum, smoke-test, and rollback procedure, see [LOCAL_WHEEL_DEPLOYMENT.md](docs/deployment/LOCAL_WHEEL_DEPLOYMENT.md).

## Data and privacy

Bundled fixtures are synthetic. PXD060583 supplies the public source for the 42-record processed-sample evaluation inputs. Institutional, proprietary, or restricted datasets require the applicable authorization and storage/access controls. Both interfaces operate locally. CLI execution reads a selected local CSV and writes the report to a selected local path. The optional browser application is served on loopback only, records run state in a local SQLite ledger, and stores Result Bundle artifacts on the local filesystem.

## License

Proprietary software. License identifier: `LicenseRef-Proprietary`.
