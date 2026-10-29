"""Real SQLite SDK timing integration belongs to the training package."""
import hashlib
from pathlib import Path
import socket
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from bench.sql_reuse_timing import Timer

class RealSDKTests(unittest.TestCase):
    def test_existing_file_sdk_real_sqlite_semantics(self):
        from bench.task import SqlTask
        from train import sql_capture as capture
        from train import sql_episodes as evidence
        from train import sql_pilot_assets as assets
        from train import sql_skill_eval as evaluator
        from train import sql_skill_workflow as sdk

        with tempfile.TemporaryDirectory(
            prefix="co-train-reuse-timing-", dir=Path(tempfile.gettempdir()).resolve(),
        ) as work, patch.object(
            socket, "socket", side_effect=AssertionError("socket forbidden")
        ):
            root = Path(work)

            def ids(label, split):
                return evidence.EpisodeIds("timing-fixture", split, "local-run", label,
                                           "trusted-local-caller", "v1")

            def task(label, rows):
                path = root / (label + ".sqlite")
                with closing(sqlite3.connect(path)) as db, db:
                    db.execute("CREATE TABLE items (n INTEGER)")
                    db.executemany("INSERT INTO items VALUES (?)", [(n,) for n in range(rows)])
                return SqlTask(label, "Count local fixture rows.", "", "SELECT COUNT(*) FROM items",
                               label, str(path), "simple", "derived", "count", "aggregate", "fixture")

            source_task = task("origin", 2)
            source_ids = ids("source", "origin")
            source = capture.start_capture(
                source_task, ids=source_ids, allow_execution=True,
            ).finish("SELECT -1")
            self.assertTrue(source.result.valid)
            self.assertEqual(source.result.score, 0)
            source_path = root / "source.json"
            assets.write_new(source_path, capture.encode_capture(source))
            timer = Timer()
            holder = {}

            def prepare():
                path = sdk.create_candidate_file(
                    source, source_task=source_task, source_ids=source_ids,
                    skill_id="fixture-count-v1", program="print('FINAL_SQL:SELECT COUNT(*) FROM items')",
                    output_dir=root / "candidate",
                )
                holder["raw"] = assets.read_file(path)
                return path

            candidate_path = timer.run("candidate_prepare", prepare, allow_execution=True)
            self.assertEqual(holder["raw"], assets.read_file(candidate_path))
            cases = tuple(evaluator.SkillCase("qualification", task("q" + str(n), n + 3),
                          ids("q" + str(n), "qualification")) for n in range(4))
            approval_ids = ids("fixture-receipt", "approval")
            qualified = timer.run("qualification", lambda: sdk.qualify_candidate_files(
                candidate_path, source_path,
                expected_source_capture_sha256=hashlib.sha256(assets.read_file(source_path)).hexdigest(),
                source_case=evaluator.SkillCase("source_failure", source_task, source_ids),
                qualification_cases=cases, ids=approval_ids, output_dir=root / "qualified",
                allow_execution=True,
            ), allow_execution=True)
            self.assertIsNotNone(qualified.promotion_path)
            self.assertEqual(len(qualified.capture_paths), 4)
            for path in qualified.capture_paths:
                actual = capture.decode_capture(assets.read_file(path))
                self.assertTrue(actual.result.valid)
                self.assertEqual(actual.result.score, 1)
            receipt = qualified.promotion_path
            # Fixture caller explicitly supplies the locally retained pin. No auth claim.
            receipt_pin = hashlib.sha256(assets.read_file(receipt)).hexdigest()
            case = evaluator.SkillCase("reuse", task("reuse", 11), ids("reuse", "reuse"))
            reused_path = timer.run("reuse", lambda: sdk.reuse_approved_files(
                candidate_path, receipt, case, expected_promotion_sha256=receipt_pin,
                ids=approval_ids, output_dir=root / "reused", allow_execution=True,
            ), allow_execution=True)
            actual = capture.decode_capture(assets.read_file(reused_path))
            self.assertTrue(actual.result.valid)
            self.assertEqual(actual.result.score, 1)
            self.assertEqual(tuple(s.kind for s in timer.observations),
                             ("candidate_prepare", "qualification", "reuse"))
            self.assertTrue(all(s.completed and s.clock_valid and s.elapsed_ns > 0
                                for s in timer.observations))


if __name__ == "__main__":
    unittest.main()
