"""Verify identity-correction recovery without detectors, models or GPU work."""
import hashlib
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

from identity_belt import BeltError, FaceRecord, IdentityBelt


PNG = b"\x89PNG\r\n\x1a\nmock candidate"


class FakeComfy:
    def __init__(self):
        self.calls = []
        self.before_request = None
        self.history_errors = []

    def request(self, endpoint, payload=None, binary=False):
        self.calls.append(endpoint)
        if self.before_request:
            self.before_request(endpoint, payload)
        if endpoint == "/prompt":
            return {"prompt_id": "existing-prompt"}
        if endpoint.startswith("/history/"):
            if self.history_errors:
                raise self.history_errors.pop(0)
            return {"existing-prompt": {"status": {"completed": True}, "outputs": {
                "save1": {"images": [{"filename": "direct.png", "type": "output"}]},
                "save2": {"images": [{"filename": "restored.png", "type": "output"}]},
            }}}
        if endpoint.startswith("/view?"):
            return PNG
        raise AssertionError(endpoint)


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = self.root / "target.png"
        self.reference = self.root / "reference.png"
        self.target.write_bytes(b"original target")
        self.reference.write_bytes(b"original reference")
        self.client = FakeComfy()
        self.belt = IdentityBelt({"comfy_dir": str(self.root / "comfy"),
                                  "output_dir": str(self.root / "outputs")}, self.client)
        self.belt.inspect = Mock(side_effect=lambda path: FaceRecord(
            Path(path), 100, 100, (10, 10, 90, 90), None, {}))
        self.belt._similarity = Mock(return_value=0.9)
        self.belt._geometry = Mock(return_value={
            "face_outline_error": 0.0, "hairline_y_ratio": 0.0,
            "forehead_within_gate": True, "hair_within_gate": True,
            "outline_within_gate": True,
        })
        renderer = ModuleType("render_belt_report")
        def render(path):
            analysis = Path(path).with_name("mock-analysis.png")
            analysis.write_bytes(PNG)
            return analysis
        renderer.render = render
        self.addCleanup(patch.stopall)
        patch.dict(sys.modules, {"render_belt_report": renderer}).start()
        patch("identity_belt.time.sleep").start()

    @property
    def manifest(self):
        return self.belt.output_dir / "belt-stable-run.submission.json"

    def run_belt(self, **kwargs):
        return self.belt.run(self.target, self.reference, run_id="stable-run", **kwargs)

    def test_workflow_sources_and_prompt_are_saved_before_waiting(self):
        observed = []
        def check_request(endpoint, payload):
            card = json.loads(self.manifest.read_text())
            if endpoint == "/prompt":
                self.assertEqual(card["state"], "submitting")
                self.assertEqual(card["workflow"], payload["prompt"])
                self.assertEqual(card["target_sha256"], hashlib.sha256(self.target.read_bytes()).hexdigest())
                self.assertEqual(card["reference_sha256"], hashlib.sha256(self.reference.read_bytes()).hexdigest())
                self.assertEqual(card["save_nodes"], {"direct": "save1", "restored": "save2"})
            elif endpoint.startswith("/history/"):
                self.assertEqual(card["prompt_id"], "existing-prompt")
                self.assertEqual(observed, ["existing-prompt"])
        self.client.before_request = check_request
        result = self.run_belt(submitted=observed.append)
        self.assertEqual(result["prompt_id"], "existing-prompt")
        self.assertTrue(result["review_required"])
        self.assertEqual(json.loads(self.manifest.read_text())["state"], "collected")
        self.assertTrue((self.belt.output_dir / result["report"]).is_file())

    def test_resume_reuses_saved_workflow_and_never_submits_again(self):
        first = self.run_belt()
        self.client.calls.clear()
        self.belt._graph = Mock(side_effect=AssertionError("Rebuilding a resumed workflow"))
        self.belt._input_copy = Mock(side_effect=AssertionError("Recopying resumed sources"))
        callback = Mock()
        resumed = self.run_belt(resume_prompt_id="existing-prompt", submitted=callback)
        self.assertNotIn("/prompt", self.client.calls)
        self.assertEqual(first["workflow"], resumed["workflow"])
        callback.assert_called_once_with("existing-prompt")

    def test_saved_prompt_is_adopted_after_callback_or_database_interruption(self):
        callback = Mock(side_effect=RuntimeError("SQLite interruption"))
        with self.assertRaisesRegex(RuntimeError, "SQLite interruption"):
            self.run_belt(submitted=callback)
        self.client.calls.clear()
        self.assertEqual(self.run_belt()["prompt_id"], "existing-prompt")
        self.assertNotIn("/prompt", self.client.calls)

    def test_changed_target_or_reference_prevents_resume_before_examination(self):
        self.run_belt()
        for source in (self.target, self.reference):
            with self.subTest(source=source.name):
                original = source.read_bytes()
                source.write_bytes(b"changed source")
                self.client.calls.clear()
                self.belt.inspect.reset_mock()
                with self.assertRaisesRegex(BeltError, "source changed"):
                    self.run_belt(resume_prompt_id="existing-prompt")
                self.assertEqual(self.client.calls, [])
                self.belt.inspect.assert_not_called()
                source.write_bytes(original)

    def test_transient_history_timeout_keeps_one_submission(self):
        self.client.history_errors = [TimeoutError("observation timed out"),
                                      RuntimeError("Cannot reach local ComfyUI: timed out")]
        self.run_belt()
        self.assertEqual(self.client.calls.count("/prompt"), 1)
        self.assertEqual(self.client.calls.count("/history/existing-prompt"), 3)

    def test_stop_keeps_submission_for_later_resume(self):
        stop = threading.Event()
        def submitted(prompt_id):
            self.assertEqual(prompt_id, "existing-prompt")
            stop.set()
        with self.assertRaisesRegex(BeltError, "Studio stopped"):
            self.run_belt(stop=stop, submitted=submitted)
        self.assertEqual(json.loads(self.manifest.read_text())["prompt_id"], "existing-prompt")
        self.assertNotIn("/history/existing-prompt", self.client.calls)
        self.client.calls.clear()
        self.run_belt(resume_prompt_id="existing-prompt")
        self.assertNotIn("/prompt", self.client.calls)

    def test_ambiguous_post_timeout_is_not_retried_blindly(self):
        def timeout(endpoint, payload):
            if endpoint == "/prompt":
                raise TimeoutError("POST observation timed out")
        self.client.before_request = timeout
        with self.assertRaises(TimeoutError):
            self.run_belt()
        self.assertEqual(json.loads(self.manifest.read_text())["state"], "submitting")
        self.client.before_request = None
        self.client.calls.clear()
        with self.assertRaisesRegex(BeltError, "ambiguous"):
            self.run_belt()
        self.assertEqual(self.client.calls, [])

    def test_missing_workflow_or_mismatched_prompt_cannot_resubmit(self):
        with self.assertRaisesRegex(BeltError, "workflow is missing"):
            self.run_belt(resume_prompt_id="existing-prompt")
        self.run_belt()
        self.client.calls.clear()
        with self.assertRaisesRegex(BeltError, "does not match"):
            self.run_belt(resume_prompt_id="different-prompt")
        card = json.loads(self.manifest.read_text())
        card["workflow"]["target"]["inputs"]["image"] = "changed.png"
        self.manifest.write_text(json.dumps(card))
        with self.assertRaisesRegex(BeltError, "workflow is missing or changed"):
            self.run_belt(resume_prompt_id="existing-prompt")
        self.assertEqual(self.client.calls, [])

    def test_unsafe_run_id_is_rejected(self):
        with self.assertRaisesRegex(BeltError, "run ID"):
            self.belt.run(self.target, self.reference, run_id="../outside")
        self.assertEqual(self.client.calls, [])

    def test_changed_candidate_mapping_cannot_collect_another_output(self):
        self.run_belt()
        card = json.loads(self.manifest.read_text())
        card["save_nodes"]["direct"] = "save2"
        self.manifest.write_text(json.dumps(card))
        self.client.calls.clear()
        with self.assertRaisesRegex(BeltError, "workflow is missing or changed"):
            self.run_belt(resume_prompt_id="existing-prompt")
        self.assertEqual(self.client.calls, [])


if __name__ == "__main__":
    unittest.main()
