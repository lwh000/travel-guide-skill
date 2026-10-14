#!/usr/bin/env python3
"""Offline release-key gate regressions. Uses synthetic values only."""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch

import release
import security_check as gate


LEGACY = "SYNTHETIC_LEGACY_KEY_123456"
EXTERNAL = "SYNTHETIC_EXTERNAL_KEY_654321"
CREDENTIAL_ID = "SYNTHETIC_CREDENTIAL_ID_789012"


def example(js_key: str = "", credential_id: str = "") -> dict:
    return {
        "amap": {"jsKey": js_key, "securityJsCode": "", "webKey": ""},
        "qweather": {"key": "", "host": "", "credentialId": credential_id},
    }


class SecurityGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "skill"
        self.root.mkdir()
        (self.root / "SKILL.md").write_text("---\nname: fixture\n---\n", encoding="utf-8")
        (self.root / gate.EXAMPLE_NAME).write_text(json.dumps(example()), encoding="utf-8")

    def config(self, path: Path, key: str) -> None:
        path.write_text(json.dumps({"amap": {"jsKey": key}, "qweather": {}}), encoding="utf-8")

    @unittest.skipUnless(shutil.which("git"), "git is required for repository gate regression")
    def test_git_tracked_files_are_scanned_without_decoding_error_or_secret_echo(self) -> None:
        (self.root / "tracked.txt").write_text(EXTERNAL, encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "init", "-q"], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(self.root), "add", "--", "SKILL.md", "tracked.txt"],
            check=True, capture_output=True,
        )
        self.assertEqual(set(gate.git_tracked(self.root) or []), {"SKILL.md", "tracked.txt"})

        report = gate.Report()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            gate.scan_git(self.root, [("amap.jsKey", EXTERNAL)], report)
        self.assertEqual(len(report.fails), 1)
        self.assertIn("git:tracked.txt", output.getvalue())
        self.assertNotIn(EXTERNAL, output.getvalue())

    def test_external_and_legacy_values_are_both_scanned_without_echo(self) -> None:
        external_file = self.base / "external.json"
        self.config(self.root / gate.PRIVATE_NAME, LEGACY)
        self.config(external_file, EXTERNAL)
        (self.root / "probe.py").write_text("token = " + repr(LEGACY), encoding="utf-8")
        (self.root / "probe.yml").write_text("token: " + EXTERNAL, encoding="utf-8")
        with patch.dict(os.environ, {"TRAVEL_GUIDE_KEYS_FILE": str(external_file)}):
            fields = gate.load_secret_fields(self.root)
            self.assertEqual({value for _, value in fields}, {LEGACY, EXTERNAL})
            report = gate.Report()
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                gate.scan_root(self.root, fields, report)
        self.assertEqual(len(report.fails), 2)
        self.assertNotIn(LEGACY, output.getvalue())
        self.assertNotIn(EXTERNAL, output.getvalue())

    def test_missing_invalid_and_blank_explicit_override_fail_closed(self) -> None:
        path = self.base / "external.json"
        self.config(self.root / gate.PRIVATE_NAME, LEGACY)
        for content in (None, "not-json", "{}", '{"amap": 3}', '{"amap": {"jsKey": {"nested": "synthetic"}}}'):
            if content is not None:
                path.write_text(content, encoding="utf-8")
            with patch.dict(os.environ, {"TRAVEL_GUIDE_KEYS_FILE": str(path)}):
                with self.assertRaises(gate.KeyConfigError):
                    gate.load_secret_fields(self.root)
        with patch.dict(os.environ, {"TRAVEL_GUIDE_KEYS_FILE": "  "}):
            with self.assertRaises(gate.KeyConfigError):
                gate.load_secret_fields(self.root)
        (self.root / gate.PRIVATE_NAME).unlink()
        with patch.dict(os.environ, {"TRAVEL_GUIDE_KEYS_FILE": str(self.root / gate.PRIVATE_NAME)}):
            with self.assertRaises(gate.KeyConfigError):
                gate.load_secret_fields(self.root)

    def test_main_exits_nonzero_for_missing_external_file_without_echo(self) -> None:
        missing = self.base / "missing.json"
        output = io.StringIO()
        with patch.dict(os.environ, {"TRAVEL_GUIDE_KEYS_FILE": str(missing)}), \
                patch.object(sys, "argv", ["security_check.py", "--root", str(self.root)]), \
                contextlib.redirect_stdout(output):
            result = gate.main()
        self.assertEqual(result, 1)
        self.assertIn("外置钥匙配置缺失", output.getvalue())
        self.assertNotIn(LEGACY, output.getvalue())
        self.assertNotIn(EXTERNAL, output.getvalue())

    def test_unset_override_uses_legacy_file(self) -> None:
        self.config(self.root / gate.PRIVATE_NAME, LEGACY)
        with patch.dict(os.environ, {}, clear=True):
            fields = gate.load_secret_fields(self.root)
        self.assertEqual({value for _, value in fields}, {LEGACY})

    def test_credential_id_is_optional_typed_and_scanned_without_echo(self) -> None:
        config = {"amap": {}, "qweather": {"credentialId": CREDENTIAL_ID}}
        (self.root / gate.PRIVATE_NAME).write_text(json.dumps(config), encoding="utf-8")
        with patch.dict(os.environ, {}, clear=True):
            fields = gate.load_secret_fields(self.root)
        self.assertIn(("qweather.credentialId", CREDENTIAL_ID), fields)
        (self.root / "probe.txt").write_text(CREDENTIAL_ID, encoding="utf-8")
        report = gate.Report()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            gate.scan_root(self.root, fields, report)
        self.assertEqual(len(report.fails), 1)
        self.assertNotIn(CREDENTIAL_ID, output.getvalue())

        config["qweather"]["credentialId"] = 123
        (self.root / gate.PRIVATE_NAME).write_text(json.dumps(config), encoding="utf-8")
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(gate.KeyConfigError):
            gate.load_secret_fields(self.root)

    def test_example_rejects_unknown_value_and_extra_fields(self) -> None:
        report = gate.Report()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            gate.check_example_json(json.dumps(example("YOUR_JS_KEY")).encode(), "example", report)
        self.assertFalse(report.fails)

        report = gate.Report()
        with contextlib.redirect_stdout(io.StringIO()):
            gate.check_example_json(
                json.dumps(example(credential_id="YOUR_QWEATHER_CREDENTIAL_ID")).encode(),
                "example", report,
            )
        self.assertFalse(report.fails)

        report = gate.Report()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            gate.check_example_json(
                json.dumps(example(credential_id=CREDENTIAL_ID)).encode(), "example", report,
            )
        self.assertEqual(len(report.fails), 1)
        self.assertNotIn(CREDENTIAL_ID, output.getvalue())

        report = gate.Report()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            gate.check_example_json(json.dumps(example(EXTERNAL)).encode(), "example", report)
        self.assertEqual(len(report.fails), 1)
        self.assertNotIn(EXTERNAL, output.getvalue())

        bad = example()
        bad["amap"]["unknown"] = EXTERNAL
        report = gate.Report()
        with contextlib.redirect_stdout(io.StringIO()):
            gate.check_example_json(json.dumps(bad).encode(), "example", report)
        self.assertEqual(len(report.fails), 1)

        (self.root / gate.EXAMPLE_NAME).write_text(json.dumps(example(EXTERNAL)), encoding="utf-8")
        report = gate.Report()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            gate.scan_root(self.root, [], report)
        self.assertEqual(len(report.fails), 1)
        self.assertNotIn(EXTERNAL, output.getvalue())

    def test_zip_example_is_checked_even_without_known_keys(self) -> None:
        archive = self.base / "fixture.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("travel-guide/local-keys.example.json", json.dumps(example(EXTERNAL)))
        report = gate.Report()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            gate.scan_zip(archive, [], report)
        self.assertEqual(len(report.fails), 1)
        self.assertNotIn(EXTERNAL, output.getvalue())

        legacy_example = example()
        del legacy_example["qweather"]["credentialId"]
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("travel-guide/local-keys.example.json", json.dumps(legacy_example))
        report = gate.Report()
        with contextlib.redirect_stdout(io.StringIO()):
            gate.scan_zip(archive, [], report)
        self.assertFalse(report.fails)

    def test_private_zip_allows_only_one_selected_config_and_scans_other_members(self) -> None:
        archive = self.base / "private.zip"
        private_config = json.dumps({
            "amap": {"jsKey": EXTERNAL},
            "qweather": {"credentialId": CREDENTIAL_ID},
        })
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr(gate.PRIVATE_MEMBER, private_config)
            z.writestr("travel-guide/SKILL.md", "generic fixture")
        report = gate.Report()
        with contextlib.redirect_stdout(io.StringIO()):
            gate.scan_zip(archive, [], report, allow_private_config=True)
        self.assertFalse(report.fails)

        report = gate.Report()
        with contextlib.redirect_stdout(io.StringIO()):
            gate.scan_zip(archive, [], report)
        self.assertTrue(report.fails)

        with zipfile.ZipFile(archive, "w") as z:
            z.writestr(gate.PRIVATE_MEMBER, private_config)
            z.writestr("travel-guide/SKILL.md", "leaked = " + EXTERNAL)
        report = gate.Report()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            gate.scan_zip(archive, [], report, allow_private_config=True)
        self.assertEqual(len(report.fails), 1)
        self.assertNotIn(EXTERNAL, output.getvalue())

        with zipfile.ZipFile(archive, "w") as z:
            z.writestr(gate.PRIVATE_MEMBER, private_config)
            z.writestr("travel-guide/SKILL.md", "credential = " + CREDENTIAL_ID)
        report = gate.Report()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            gate.scan_zip(archive, [], report, allow_private_config=True)
        self.assertEqual(len(report.fails), 1)
        self.assertNotIn(CREDENTIAL_ID, output.getvalue())

        with zipfile.ZipFile(archive, "w") as z:
            z.writestr(gate.PRIVATE_MEMBER, private_config)
            z.writestr("travel-guide/assets/icon.svg", EXTERNAL.encode("utf-16-le"))
        report = gate.Report()
        with contextlib.redirect_stdout(io.StringIO()):
            gate.scan_zip(archive, [], report, allow_private_config=True)
        self.assertEqual(len(report.fails), 1)

    def test_private_zip_rejects_missing_extra_and_duplicate_private_members(self) -> None:
        archive = self.base / "private.zip"
        config = json.dumps({"amap": {"jsKey": EXTERNAL}, "qweather": {}})
        for entries in (
            [("travel-guide/SKILL.md", "fixture")],
            [(gate.PRIVATE_MEMBER, config), ("other/local-keys.json", config)],
            [(gate.PRIVATE_MEMBER, config), (gate.PRIVATE_MEMBER, config)],
        ):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(archive, "w") as z:
                    for name, content in entries:
                        z.writestr(name, content)
            report = gate.Report()
            with contextlib.redirect_stdout(io.StringIO()):
                gate.scan_zip(archive, [], report, allow_private_config=True)
            self.assertTrue(report.fails)

    def test_private_zip_cli_gate_uses_synthetic_external_config(self) -> None:
        external_file = self.base / "external.json"
        self.config(external_file, EXTERNAL)
        archive = self.base / "private.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr(gate.PRIVATE_MEMBER, external_file.read_bytes())
            z.writestr("travel-guide/SKILL.md", "generic fixture")
        output = io.StringIO()
        with patch.dict(os.environ, {"TRAVEL_GUIDE_KEYS_FILE": str(external_file)}), \
                patch.object(sys, "argv", ["security_check.py", "--root", str(self.root),
                                           "--zip", str(archive), "--private"]), \
                contextlib.redirect_stdout(output):
            result = gate.main()
        self.assertEqual(result, 0)
        self.assertNotIn(EXTERNAL, output.getvalue())

    def test_release_private_zip_selects_external_fixture_and_stays_outside_skill(self) -> None:
        for _, rel in release.iter_files(Path(__file__).resolve().parent.parent):
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture", encoding="utf-8")
        (self.root / gate.EXAMPLE_NAME).write_text(json.dumps(example()), encoding="utf-8")
        self.config(self.root / gate.PRIVATE_NAME, LEGACY)
        external_file = self.base / "external.json"
        self.config(external_file, EXTERNAL)
        output_dir = self.base / "output"
        output_dir.mkdir()

        with patch.dict(os.environ, {"TRAVEL_GUIDE_KEYS_FILE": str(external_file)}), \
                patch.object(release, "run", return_value=True) as checked_run, \
                contextlib.redirect_stdout(io.StringIO()):
            private_zip = release.make_zip(self.root, "fixture", output_dir, private=True)
            normal_zip = release.make_zip(self.root, "fixture", output_dir)
        zip_checks = [call.args[0] for call in checked_run.call_args_list if "--zip" in call.args[0]]
        self.assertEqual(len(zip_checks), 2)
        self.assertEqual(sum("--private" in command for command in zip_checks), 1)
        self.assertTrue(private_zip.name.endswith("-private.zip"))
        with zipfile.ZipFile(private_zip) as z:
            self.assertEqual(z.read(gate.PRIVATE_MEMBER), external_file.read_bytes())
            self.assertEqual(z.namelist().count(gate.PRIVATE_MEMBER), 1)
        with zipfile.ZipFile(normal_zip) as z:
            self.assertNotIn(gate.PRIVATE_MEMBER, z.namelist())
        report = gate.Report()
        with contextlib.redirect_stdout(io.StringIO()):
            gate.scan_zip(private_zip, [], report, allow_private_config=True)
        self.assertFalse(report.fails)
        with self.assertRaises(SystemExit):
            release.check_private_output(self.root, self.root / "nested")
        with self.assertRaises(SystemExit):
            release.make_zip(self.root, "fixture", self.root, private=True)
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(release.selected_private_config(self.root), self.root / gate.PRIVATE_NAME)


if __name__ == "__main__":
    unittest.main()
