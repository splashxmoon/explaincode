import io
import json
import os
import contextlib
import tempfile
import unittest

import buildwatch


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = "wb" if isinstance(data, bytes) else "w"
    with open(path, mode) as f:
        f.write(data)


class BuildwatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.old = os.path.join(self.root, "v1")
        self.new = os.path.join(self.root, "v2")

    def tearDown(self):
        self.tmp.cleanup()

    def test_identical_builds_are_unchanged(self):
        write(f"{self.old}/app.bin", b"hello world binary \x00\x01")
        write(f"{self.new}/app.bin", b"hello world binary \x00\x01")
        report = buildwatch.compare(*buildwatch.load(self.old, self.new))
        self.assertEqual(report["unchanged"], 1)
        self.assertEqual(report["added"], [])
        self.assertEqual(report["removed"], [])
        self.assertEqual(report["changed"], {})

    def test_added_removed_and_changed(self):
        write(f"{self.old}/gone.txt", "bye")
        write(f"{self.old}/same/keep.txt", "keep this file")
        write(f"{self.old}/mod.bin", b"\x00version one string here\x00")
        write(f"{self.new}/same/keep.txt", "keep this file")
        write(f"{self.new}/new.txt", "fresh file")
        write(f"{self.new}/mod.bin", b"\x00version two string here\x00")
        report = buildwatch.compare(*buildwatch.load(self.old, self.new))
        self.assertEqual(report["added"], ["new.txt"])
        self.assertEqual(report["removed"], ["gone.txt"])
        self.assertEqual(report["unchanged"], 1)
        self.assertIn("mod.bin", report["changed"])
        self.assertIn("version two string here", report["changed"]["mod.bin"]["added_sample"])

    def test_new_endpoint_is_flagged(self):
        write(f"{self.old}/app.bin", b"\x00padding strings only\x00")
        write(f"{self.new}/app.bin", b"\x00padding strings only\x00https://telemetry.example.com/collect\x00")
        report = buildwatch.compare(*buildwatch.load(self.old, self.new))
        urls = [f for f in report["findings"] if f["category"] == "url"]
        self.assertEqual(len(urls), 1)
        self.assertEqual(urls[0]["value"], "https://telemetry.example.com/collect")

    def test_secret_values_are_redacted(self):
        write(f"{self.old}/config.txt", "nothing here at all")
        write(f"{self.new}/config.txt", "api_key = sk_live_SUPERSECRET123")
        report = buildwatch.compare(*buildwatch.load(self.old, self.new))
        secrets = [f for f in report["findings"] if f["category"] == "secret"]
        self.assertEqual(len(secrets), 1)
        self.assertNotIn("SUPERSECRET", json.dumps(report))
        self.assertTrue(secrets[0]["value"].startswith("api_"))

    def test_single_file_comparison(self):
        old_file = os.path.join(self.root, "a.bin")
        new_file = os.path.join(self.root, "b.bin")
        write(old_file, b"\x00old contents here\x00")
        write(new_file, b"\x00new contents here\x00")
        report = buildwatch.compare(*buildwatch.load(old_file, new_file))
        self.assertEqual(list(report["changed"]), ["b.bin"])

    def test_cli_fail_on_flags_exit_code(self):
        write(f"{self.old}/x.txt", "nothing")
        write(f"{self.new}/x.txt", "nothing\nhttp://10.0.0.1/admin padding")
        with contextlib.redirect_stdout(io.StringIO()):
            code = buildwatch.main([self.old, self.new, "--fail-on-flags"])
        self.assertEqual(code, 1)
        with contextlib.redirect_stdout(io.StringIO()):
            code = buildwatch.main([self.old, self.new])
        self.assertEqual(code, 0)

    def test_cli_json_output_is_valid(self):
        write(f"{self.old}/x.txt", "one")
        write(f"{self.new}/x.txt", "two two two")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            buildwatch.main([self.old, self.new, "--json"])
        data = json.loads(buf.getvalue())
        self.assertIn("changed", data)

    def test_mixed_file_and_dir_is_rejected(self):
        write(f"{self.old}/x.txt", "one")
        single = os.path.join(self.root, "single.txt")
        write(single, "two")
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                buildwatch.main([self.old, single])


if __name__ == "__main__":
    unittest.main()
