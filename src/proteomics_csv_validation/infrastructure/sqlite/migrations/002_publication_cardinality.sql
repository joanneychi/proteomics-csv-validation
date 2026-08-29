CREATE UNIQUE INDEX run_artifact_one_result_bundle_per_run
ON run_artifact(run_id)
WHERE kind = 'RESULT_BUNDLE';

-- statement boundary --

CREATE UNIQUE INDEX run_artifact_one_per_export_attempt
ON run_artifact(export_attempt_id)
WHERE export_attempt_id IS NOT NULL;
