# Proteomics CSV Validation System

`proteomics-csv-validation` is a local Python command-line validator for processed-sample proteomics CSV files. The CLI resolves source headers to canonical profile fields when mapping is requested, checks required columns, sample identifiers, and required values, and writes a Markdown technical review report. Validation does not modify the source CSV.

- **Author:** Joanne Yu Yan Chan
- **Application version:** `0.4.0`
- **Default profile:** `0.2.0`
- **Reduced Metadata profile:** `0.3.0`
- **Regression suite:** 126 passing tests
- **Python:** `>=3.11`
- **Status:** Alpha

## Release progression

Application version `0.4.0` identifies the CLI package. Profile `0.3.0` identifies the Reduced Metadata validation contract introduced in `v0.4.0`. Profile `0.2.0` is the default validation contract.

| Application release | Principal change | Tests at tag |
|---|---|---:|
| `v0.1.0` | Initial local validation workflow | 67 |
| `v0.2.0` | Required-value missingness validation | 75 |
| `v0.3.0` | Automatic and explicit column mapping | 98 |
| `v0.4.0` | Explicit profile selection and Reduced Metadata profile `0.3.0` | 111 |

The repository test suite passes 126 tests. `tests/test_ingest.py` contains 20 tests; the `v0.4.0` tag contains 5. Application source files under `src/proteomics_csv_validation/` are byte-identical to the `v0.4.0` tag.

## Validation scope

The application reports three structural finding groups:

- **Schema:** required profile columns missing from the CSV header
- **Identifier:** blank or duplicate `sample_id` values
- **Missingness:** blank required non-key values in required columns present in the CSV

Required-value missingness uses rule `missingness.required_value` version `1.0.0` and finding code `MISSINGNESS_REQUIRED_VALUE`.

Column mapping precedes validation when `--auto-map` or `--column-map` is selected. Strict mode validates source headers unchanged.

### Out of scope

The application does not perform:

- raw LC-MS processing
- vendor-format, mzML, or mzXML processing
- protein inference
- imputation or normalization
- batch correction
- statistical analysis
- biological or clinical interpretation
- regulatory decisions
- repository-conformance assessment
- database or hosted-service operation
- cloud upload
- production deployment

## Processed-sample profiles

`proteomics_processed_sample_summary` is the built-in profile ID. Descriptor schema version `1.0.0` defines the JSON profile structure. `sample_id` is the exact, case-sensitive record key. The record grain is a processed sample-summary row; the file grain is a study.

### Profile `0.2.0`: Default

Profile `0.2.0` requires six fields:

1. `study_id`
2. `sample_id`
3. `experimental_condition`
4. `sample_preparation_batch`
5. `quantified_protein_group_count`
6. `protein_group_intensity_sum`

### Profile `0.3.0`: Reduced Metadata

Profile `0.3.0` requires four fields:

1. `study_id`
2. `sample_id`
3. `quantified_protein_group_count`
4. `protein_group_intensity_sum`

Under profile `0.3.0`, `experimental_condition` and `sample_preparation_batch` are optional. Supplied values are preserved. Omitted optional fields produce no schema or required-value missingness finding. Schema and required-value missingness checks apply to the four required fields.

Application version `0.4.0` packages profiles `0.3.0`, `0.2.0`, and `0.1.0`. Application release `v0.2.0` used profile `0.1.0`.

## Processing path

```text
CSV input
→ ingestion
→ optional column mapping
→ schema validation
→ identifier validation
→ required-value missingness validation
→ finding aggregation
→ Markdown report
```

Automatic and explicit mapping resolve source headers to canonical profile fields. Source values and physical CSV row numbers are preserved.

## Column mapping

### Strict mode

Strict mode sends source headers to validation unchanged:

```bash
proteomics-csv-validate input.csv \
  --output report.md
```

### Automatic mapping

`--auto-map` resolves conservative lexical variants and profile field titles to canonical profile fields:

```bash
proteomics-csv-validate input.csv \
  --auto-map \
  --output report.md
```

Dataset-specific labels and ambiguous headers require an explicit mapping file.

### Explicit mapping

Explicit mapping uses a versioned JSON file. Mapping keys are canonical profile fields; mapping values are source headers.

```json
{
  "mapping_specification_version": "1.0.0",
  "columns": {
    "sample_id": "Sample Name",
    "experimental_condition": "Condition"
  }
}
```

```bash
proteomics-csv-validate input.csv \
  --column-map mapping.json \
  --output report.md
```

`--auto-map` and `--column-map` are mutually exclusive. Explicit mapping files use mapping specification version `1.0.0`.

## Profile selection

Header mapping and profile selection are independent. `--auto-map` and `--column-map` resolve headers. `--profile-version` selects the validation contract.

Omitting `--profile-version` uses profile `0.2.0`. `--profile-version 0.3.0` selects Reduced Metadata. Missing metadata does not select profile `0.3.0` automatically, and the application does not infer omitted values.

```bash
proteomics-csv-validate input.csv \
  --profile-version 0.3.0 \
  --auto-map \
  --output report.md
```

## PXD060583 evaluation

The PXD060583 evaluation derived 42 processed-sample rows from 42 MaxQuant LFQ experiment columns in the publicly deposited ProteomeXchange dataset `PXD060583`. `study_id` used the ProteomeXchange accession, `sample_id` used the MaxQuant experiment label, `quantified_protein_group_count` counted supplied positive values in the selected quantitative column, and `protein_group_intensity_sum` summed those values. The derived CSV was the application input; `proteinGroups.txt` supplied source material.

The reviewed source material did not establish unambiguous values for `experimental_condition` or `sample_preparation_batch`. Application `v0.3.0` with profile `0.2.0` produced 84 findings across the 42 rows when those fields were blank. Application `v0.4.0` with profile `0.3.0` produced zero findings for the 42 rows. Strict, automatic, and explicit mapping produced identical finding totals for a given profile.

A negative-control copy omitted a required quantitative value and produced a `MISSINGNESS_REQUIRED_VALUE` finding.

The evaluation covered structural behavior of the derived CSV. The CLI accepts processed-sample CSV input. PRIDE archives, MaxQuant `proteinGroups.txt` files, spreadsheets, and raw LC-MS files are not CLI inputs. PRIDE/SDRF conformance, repository acceptance, normalization quality, scientific validity, and biological interpretation were outside the evaluation.

## Installation

For a release wheel, follow `docs/deployment/LOCAL_WHEEL_DEPLOYMENT.md`. For source checkout and local verification, use the editable installation below.

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

Runtime code uses the Python standard library. Installing `.[dev]` adds pytest.

## Version check

```bash
proteomics-csv-validate --version
```

Expected output:

```text
proteomics-csv-validate 0.4.0
```

## Example fixtures

Bundled fixtures use fixed expected finding counts:

| Fixture | Rows | Expected findings |
|---|---:|---:|
| `baseline_valid.csv` | 8 | 0 |
| `seeded_errors.csv` | 8 | 4 |
| `required_value_missing_values.csv` | 8 | 3 |

`seeded_errors.csv` omits required `study_id` from the header, repeats `sample_id` value `S003` at CSV rows 4 and 5, and contains a blank `sample_id` at row 9.

`required_value_missing_values.csv` contains a blank `experimental_condition` at CSV row 3, a whitespace-only `sample_preparation_batch` at row 5, and a blank `protein_group_intensity_sum` at row 7.

Bundled fixture records are synthetic.

### Run a fixture

```bash
proteomics-csv-validate \
  data/synthetic/baseline_valid.csv \
  --output reports/baseline_report.md
```

When the target report already exists, add `--overwrite`:

```bash
proteomics-csv-validate \
  data/synthetic/baseline_valid.csv \
  --output reports/baseline_report.md \
  --overwrite
```

## Reports

Report format `1.1.0` records the following information:

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

The command adds a missing parent directory for the selected output path, then writes the report. Existing report files require `--overwrite`.

Reports record filenames. Absolute input, output, and mapping-file paths are omitted.

Completed validation returns exit status `0`, including runs containing findings.

## Exit codes

The CLI uses the following process exit codes:

- `0`: validation and report writing completed
- `1`: unexpected internal failure
- `2`: invalid command-line usage
- `3`: input access failure or fatal ingestion finding stopped validation
- `4`: profile-definition failure
- `5`: report-writing failure
- `6`: column-mapping configuration or resolution failure

## Tests and CI

Run the complete suite:

```bash
python -m pytest
```

The complete suite passes 126 tests. `tests/test_ingest.py` contains 20 ingestion tests; the `v0.4.0` tag contains 5. The 15 added tests cover argument types, CSV-extension checks, file access, UTF-8/BOM/NUL handling, parser failures, header validation, byte, row, and column limits, blank records, and record width.

The full suite covers validator logic, aggregation, ingestion, profile loading, profile selection, column mapping, CLI behavior, pipeline integration, report rendering, packaging, and end-to-end execution.

GitHub Actions runs seven jobs for pull requests targeting `main` and pushes to `main`: six test environments and a build-artifacts job. The test environments are Ubuntu with Python 3.11, 3.12, 3.13, and 3.14; Windows with Python 3.14; and macOS with Python 3.14. The workflow supports manual dispatch and stops at build artifacts.

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
    profiles/     versioned profile resources and loader
    validators/   schema, identifier, and missingness validators
    aggregate.py  finding ordering and summary counts
    cli.py        command-line interface
    column_mapping.py  header mapping
    ingest.py     CSV ingestion and file checks
    pipeline.py   validation workflow
    report.py     Markdown rendering and file writing
tests/            automated test suite
MANIFEST.in       source-distribution inclusion rules
README.md         project documentation
pyproject.toml    package and test configuration
```

## Package build

Build the source distribution and wheel from the repository root:

```bash
python -m pip install --upgrade build
python -m build
```

`python -m build` writes the source distribution and wheel to `dist/`.

## Data and privacy

Bundled fixtures are synthetic. The PXD060583 evaluation documents the public source used to derive the 42-row CSV. Institutional, proprietary, or restricted datasets require authorization plus storage and access controls appropriate to their classification. The CLI reads a selected local CSV and writes the report to a selected local path.

## License

License identifier: `LicenseRef-Proprietary`.
