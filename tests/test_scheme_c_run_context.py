from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

from gridform_core.builtin.scheme_c_1000twh.runtime_compat import config
from gridform_core.builtin.scheme_c_1000twh.scheme_c_context import (
    CONFIG_ATTRIBUTES,
    LegacyConfigSession,
    build_scheme_c_run_context,
    persist_or_verify_context,
    stage_reference_named_inputs,
)
from gridform_core.errors import CompatibilityError, DataError


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "data-packs/value-synthetic-contract-pack-v1"


class _ParameterAdapter:
    def __init__(self, bidding_factor: float) -> None:
        self.bidding_factor = bidding_factor

    def apply_config(self, module) -> None:
        module.simulation_parameters["bidding_factor"] = self.bidding_factor


def _config_snapshot() -> dict[str, object]:
    return {name: copy.deepcopy(getattr(config, name)) for name in CONFIG_ATTRIBUTES}


class SchemeCRunContextTests(unittest.TestCase):
    def _context(self, root: Path, label: str):
        output = root / label
        output.mkdir(parents=True, exist_ok=True)
        work = stage_reference_named_inputs(PACK, output)
        return build_scheme_c_run_context(
            run_id=f"run-{label}",
            project_id=f"project-{label}",
            start_year=2025,
            end_year=2026,
            periods=2,
            scenario_id="existing_decarb_base",
            pack_root=PACK,
            output_dir=output,
            reference_work_dir=work,
            module_ids={"psm": "value-bid-at-cost-psm"},
            scientific_parameters={"scenario.id": "existing_decarb_base"},
            runtime_options={"trace.level": "summary"},
            environment={"GRIDFORM_CONTEXT_TEST": label},
        )

    def test_context_is_immutable_and_hash_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            context = self._context(Path(folder), "a")
            repeated = self._context(Path(folder), "a")
            self.assertEqual(context.context_sha256, repeated.context_sha256)
            with self.assertRaises(TypeError):
                context.module_ids["psm"] = "other"  # type: ignore[index]

    def test_sessions_are_order_independent_and_restore_all_state(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            contexts = {key: self._context(root, key) for key in ("a", "b")}
            before_config = _config_snapshot()
            before_environment = os.environ.get("GRIDFORM_CONTEXT_TEST")
            before_cwd = Path.cwd()

            def observe(label: str) -> tuple[str, float, str, str]:
                context = contexts[label]
                factor = 1.25 if label == "a" else 2.5
                with LegacyConfigSession(context, _ParameterAdapter(factor), object()):
                    return (
                        os.environ["GRIDFORM_CONTEXT_TEST"],
                        config.simulation_parameters["bidding_factor"],
                        config.file_paths["solar_weather"],
                        str(Path.cwd()),
                    )

            forward = {label: observe(label) for label in ("a", "b")}
            reverse = {label: observe(label) for label in ("b", "a")}
            self.assertEqual(forward, reverse)
            self.assertEqual(_config_snapshot(), before_config)
            self.assertEqual(os.environ.get("GRIDFORM_CONTEXT_TEST"), before_environment)
            self.assertEqual(Path.cwd(), before_cwd)
            for context in contexts.values():
                evidence = json.loads(
                    (context.output_dir / "legacy-config-session.json").read_text(encoding="utf-8")
                )
                self.assertTrue(evidence["restored"])

    def test_failure_restores_state_and_concurrent_session_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            a = self._context(root, "a")
            b = self._context(root, "b")
            before_config = _config_snapshot()
            before_cwd = Path.cwd()
            with self.assertRaisesRegex(RuntimeError, "injected"):
                with LegacyConfigSession(a, _ParameterAdapter(1.2), object()):
                    raise RuntimeError("injected")
            self.assertEqual(_config_snapshot(), before_config)
            self.assertEqual(Path.cwd(), before_cwd)

            errors: list[BaseException] = []
            with LegacyConfigSession(a, _ParameterAdapter(1.2), object()):
                thread = threading.Thread(
                    target=lambda: self._attempt_session(b, errors), daemon=True
                )
                thread.start()
                thread.join(timeout=5)
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], CompatibilityError)

    @staticmethod
    def _attempt_session(context, errors: list[BaseException]) -> None:
        try:
            with LegacyConfigSession(context, _ParameterAdapter(2.0), object()):
                pass
        except BaseException as error:  # test captures the cross-thread result
            errors.append(error)

    def test_missing_weather_binding_fails_before_file_access(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            payload = json.loads((PACK / "manifest.json").read_text(encoding="utf-8"))
            payload["bindings"].pop("weather.wind")
            (root / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(DataError, "weather.wind"):
                build_scheme_c_run_context(
                    run_id="missing-weather",
                    project_id="test",
                    start_year=2025,
                    end_year=2025,
                    periods=2,
                    scenario_id="existing_decarb_base",
                    pack_root=root,
                    output_dir=root / "out",
                    reference_work_dir=root / "work",
                    module_ids={},
                    scientific_parameters={},
                    runtime_options={},
                    environment={},
                )

    def test_changed_context_is_rejected_on_resume(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            context = self._context(root, "resume")
            persist_or_verify_context(context)
            changed = build_scheme_c_run_context(
                run_id=context.run_id,
                project_id=context.project_id,
                start_year=context.start_year,
                end_year=context.end_year,
                periods=context.periods,
                scenario_id="governmental_target",
                pack_root=context.pack_root,
                output_dir=context.output_dir,
                reference_work_dir=context.reference_work_dir,
                module_ids=context.module_ids,
                scientific_parameters={"scenario.id": "governmental_target"},
                runtime_options=context.runtime_options,
                environment=context.environment,
            )
            with self.assertRaisesRegex(CompatibilityError, "context changed"):
                persist_or_verify_context(changed)


if __name__ == "__main__":
    unittest.main()
