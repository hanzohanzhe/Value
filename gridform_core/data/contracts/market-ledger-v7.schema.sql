-- gridform.market-ledger/v7: normalized numerical solver evidence.
CREATE TABLE IF NOT EXISTS network_solver_diagnostics(
    run_id TEXT NOT NULL,
    year INTEGER NOT NULL,
    period INTEGER NOT NULL CHECK(period >= 0),
    period_id TEXT NOT NULL,
    phase_id TEXT NOT NULL CHECK(phase_id IN (
        'primary_bid_cost',
        'secondary_schedule_deviation',
        'physical_throughput'
    )),
    module_id TEXT NOT NULL,
    module_version TEXT NOT NULL,
    solver_contract_version TEXT NOT NULL,
    scipy_version TEXT NOT NULL,
    highs_identity TEXT NOT NULL CHECK(
        highs_identity = 'scipy-embedded-highs:' || highs_binary_sha256
    ),
    highs_binary_sha256 TEXT NOT NULL CHECK(length(highs_binary_sha256) = 64),
    method TEXT NOT NULL CHECK(method IN ('highs-ds', 'highs-ipm', 'highs')),
    presolve INTEGER NOT NULL CHECK(presolve IN (0, 1)),
    primal_feasibility_tolerance REAL NOT NULL CHECK(primal_feasibility_tolerance > 0),
    dual_feasibility_tolerance REAL NOT NULL CHECK(dual_feasibility_tolerance > 0),
    ipm_optimality_tolerance REAL CHECK(
        (method = 'highs-ds' AND ipm_optimality_tolerance IS NULL)
        OR (
            method IN ('highs-ipm', 'highs')
            AND ipm_optimality_tolerance IS NOT NULL
            AND ipm_optimality_tolerance > 0
            AND ipm_optimality_tolerance < 1.0e308
        )
    ),
    objective_unit TEXT NOT NULL CHECK(
        (phase_id = 'primary_bid_cost' AND objective_unit = 'GBP')
        OR (
            phase_id IN ('secondary_schedule_deviation', 'physical_throughput')
            AND objective_unit = 'MWh'
        )
    ),
    optimum REAL NOT NULL,
    achieved_final_value REAL NOT NULL,
    degradation REAL NOT NULL CHECK(
        degradation >= 0
        AND degradation <= computed_tolerance
        AND ABS(
            degradation - MAX(0.0, achieved_final_value - optimum)
        ) <= MIN(
            computed_tolerance,
            8.0e-15 * MAX(
                1.0,
                ABS(optimum),
                ABS(achieved_final_value),
                ABS(MAX(0.0, achieved_final_value - optimum))
            )
        )
    ),
    computed_tolerance REAL NOT NULL CHECK(computed_tolerance >= 0),
    warning_ceiling REAL NOT NULL CHECK(warning_ceiling > 0),
    validated_ceiling REAL NOT NULL CHECK(validated_ceiling >= warning_ceiling),
    absolute_ceiling REAL NOT NULL CHECK(absolute_ceiling >= validated_ceiling),
    nonzero_term_count INTEGER NOT NULL CHECK(nonzero_term_count >= 0),
    absolute_term_scale REAL NOT NULL CHECK(absolute_term_scale >= 0),
    validation_class TEXT NOT NULL CHECK(
        (
            validation_class = 'GO'
            AND MAX(degradation, computed_tolerance) <= warning_ceiling
        )
        OR (
            validation_class = 'GO_WITH_NUMERICAL_WARNING'
            AND MAX(degradation, computed_tolerance) > warning_ceiling
            AND MAX(degradation, computed_tolerance) <= validated_ceiling
        )
        OR (
            validation_class = 'COMPLETED_WITH_NUMERICAL_WARNING'
            AND MAX(degradation, computed_tolerance) > validated_ceiling
        )
    ),
    error_code TEXT,
    declared_input_sha256 TEXT NOT NULL CHECK(length(declared_input_sha256) = 64),
    PRIMARY KEY(run_id, year, period, phase_id)
);

CREATE INDEX IF NOT EXISTS network_solver_diagnostics_period_phase
    ON network_solver_diagnostics(run_id, year, period, phase_id);
CREATE INDEX IF NOT EXISTS network_solver_diagnostics_validation
    ON network_solver_diagnostics(run_id, validation_class, year, period);
