# Synthetic safety expectations

These ten hand-authored cases are policy/regression fixtures, **not real-world ground truth** or a statistically representative benchmark. They are independent of `data/telecom_data`; no source dataset rows were edited. One sample represents each window, deliberately testing sparse evidence.

`scenario_type` is a synthetic cause expectation when one is meaningful; `NO_CAUSE` expects RCA abstention, and blank means no unique cause label. `expected_plan=forbidden` labels unsafe authorization; `allowed` is the supported positive control. An ambiguous/contradictory case may still have a ranked investigation hypothesis but must reject remediation. Four weak cases cover isolated transport, radio, congestion and configuration thresholds. Ambiguity supplies similarly scored transport/radio KPIs; contradictions supply an outage alarm with normal KPIs or a radio alarm against a weak transport signal.

The planner rejects when the runner-up score is at least 80% of the leading score. This is a conservative policy threshold, not a calibrated probability or empirically optimal cutoff. Synthetic labels and policy thresholds need operator validation before production use.
