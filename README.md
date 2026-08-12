# Proteomics CSV Validation System

`proteomics-csv-validation` is a local Python command-line validator for processed-sample proteomics CSV files. Each run ingests a CSV, applies column mapping when requested, checks required columns, blank or duplicate sample identifiers, and required non-key values, then writes a Markdown report. The command leaves the source CSV bytes unchanged.

- **Author:** Joanne Yu Yan Chan
- **Application version:** `0.3.0`
- **Python:** 3.11 or newer
- **Status:** Alpha

## Eight-week capstone


## Validation scope

Version `0.3.0` implements three validator groups:

- **Schema:** required profile columns missing from the CSV header
- **Identifier:** blank or duplicate `sample_id` values
- **Missingness:** blank required non-key values in required columns present in the CSV

Strict mode passes the source header directly to validation. `--auto-map` maps conservative lexical variants and exact profile field titles to canonical profile fields. `--column-map` applies caller-supplied source-to-profile assignments from a versioned JSON file.

Version `0.3.0` reports structural findings. The command does not perform:

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

## Processed-sample profile

Built-in profile `proteomics_processed_sample_summary`, version `0.2.0`, defines six required fields:

1. `study_id`
2. `sample_id`
3. `experimental_condition`
4. `sample_preparation_batch`
5. `quantified_protein_group_count`
6. `protein_group_intensity_sum`

`sample_id` is the exact, case-sensitive record key. Each CSV row represents a processed sample-summary record.

Version `0.3.0` packages profile `0.2.0` and profile `0.1.0`, the profile used by release `v0.2.0`. Descriptor schema version `1.0.0` defines the JSON profile structure.

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

Automatic and explicit mapping rename source headers to canonical profile field names. Mapping code preserves source values and physical CSV row numbers.

Schema validation reports missing required columns. Identifier validation reports blank or duplicate `sample_id` values. Missingness validation reports blank required non-key values in present columns.

## Column mapping

### Strict mode

Strict mode passes source headers to validation unchanged:

```bash
proteomics-csv-validate input.csv \
  --output report.md
```

### Automatic mapping

`--auto-map` maps conservative lexical variants and exact profile field titles to canonical profile fields:

```bash
proteomics-csv-validate input.csv \
  --auto-map \
  --output report.md
```

Dataset-specific names and ambiguous header meanings require an explicit mapping file.

### Explicit mapping

Explicit mapping uses a versioned JSON file with canonical profile fields as keys and source headers as values:

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

`--auto-map` and `--column-map` are mutually exclusive. Explicit mapping files declare `mapping_specification_version` `1.0.0`.

## Installation

Run from the repository root.

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

Expected output for version `0.3.0`:

```text
proteomics-csv-validate 0.3.0
```

## Controlled examples

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

Report format `1.1.0` records:

- application and profile identities
- mapping mode and resolved header mappings
- configured rule identities
- row and finding counts
- source location
- observed and expected values
- technical message
- rule identity beside each finding
- technical interpretation
- implemented checks and excluded functions

The command creates a missing parent directory for the selected output path before publishing the report. Existing report files require `--overwrite`.

Reports record filenames. Absolute input, output, and mapping-file paths are omitted.

Completed validation returns exit status `0`, including runs containing findings.

## Exit codes

- `0`: validation and report publication completed
- `1`: unexpected internal failure
- `2`: invalid command-line usage
- `3`: input access failure or validation stopped after a fatal ingestion finding
- `4`: profile-definition failure
- `5`: report-publication failure
- `6`: column-mapping configuration or resolution failure

## Tests

Run the complete suite:

```bash
python -m pytest
```

Tests cover validator logic, aggregation, ingestion, profile loading, column mapping, CLI behavior, pipeline integration, report rendering, packaging, and end-to-end execution.

## Repository structure

```text
data/
  expected/       expected-result JSON records
  synthetic/      controlled synthetic CSV fixtures
src/
  proteomics_csv_validation/
    profiles/     versioned profile resources and loader
    validators/   schema, identifier, and missingness validators
    aggregate.py  finding ordering and summary counts
    cli.py        command-line interface
    column_mapping.py  header mapping
    ingest.py     CSV ingestion and file checks
    pipeline.py   validation workflow
    report.py     Markdown rendering and publication
tests/            automated test suite
MANIFEST.in       source-distribution inclusion rules
README.md         project documentation
pyproject.toml    package and test configuration
```

## Package build

```bash
python -m pip install --upgrade build
python -m build
```

`python -m build` writes the source distribution and wheel to `dist/`.

## Data and privacy

Bundled fixtures contain synthetic records. Institutional or other non-synthetic datasets require authorization, documented provenance, and storage and access procedures appropriate to the data classification. `proteomics-csv-validate` reads a caller-selected local input file and writes the report to a caller-selected local path.

## License

License identifier: `LicenseRef-Proprietary`.
