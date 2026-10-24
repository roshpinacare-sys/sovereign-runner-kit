#!/usr/bin/env python3
# fleet-receipts-guard-core.test.py — TDD suite BEFORE logic (sovereign-lane wave 19.85, trace 1a16ecaa3e014051).
# Deterministic, offline, stdlib-only. The guard protects the fleet-economy receipts rail
# (the settlement plane directive §2 depends on) against the measured ours-merge wipe class.
# Hostile fixtures: absence, garbage drift, unknown adoption, tampered receipt chain.
import json, sys, unittest, importlib.util, os

HERE = os.path.dirname(os.path.abspath(__file__))
CORE_PATH = os.path.join(HERE, "fleet-receipts-guard-core.py")

def load_core():
    spec = importlib.util.spec_from_file_location("frg_core", CORE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

CORE = load_core()

A = "lib/receipt-sign.ts"
B = "tests/receipt-sign.test.ts"
C = "state/audit/verify_signatures.py"
D = "state/audit/receipt-2026-10-23-wave1980.json"
RAIL = [A, B, C, D]
SHA = {p: ("a%02d" % i) * 20 for i, p in enumerate(RAIL)}

class TestDetect(unittest.TestCase):
    def test_all_present_zero_swallows(self):
        tree = dict(SHA)
        adopted = dict(SHA)
        out = CORE.detect(tree, adopted)
        self.assertEqual(out["swallows"], [])
        self.assertEqual(out["plan"], [])
        self.assertIsNone(out["planError"])
        self.assertEqual(out["alerts"], [])

    def test_absence_produces_reland_plan(self):
        tree = dict(SHA); tree[B] = ""
        adopted = dict(SHA)
        out = CORE.detect(tree, adopted)
        self.assertEqual(out["swallows"], [B])
        self.assertEqual(out["plan"], [{"path": B, "from": "blob:" + SHA[B]}])
        self.assertIsNone(out["planError"])

    def test_missing_path_key_counts_as_absent(self):
        tree = {k: v for k, v in SHA.items() if k != D}
        adopted = dict(SHA)
        out = CORE.detect(tree, adopted)
        self.assertEqual(out["swallows"], [D])
        self.assertEqual(len(out["plan"]), 1)

    def test_absent_without_adopted_source_fails_closed(self):
        tree = dict(SHA); tree[A] = ""
        adopted = {p: s for p, s in SHA.items() if p != A}
        out = CORE.detect(tree, adopted)
        self.assertEqual(out["plan"], [])
        self.assertIsNotNone(out["planError"])
        self.assertIn("fail-closed", out["planError"])
        self.assertIn(A, out["planError"])

    def test_content_drift_is_alert_only(self):
        tree = dict(SHA); tree[C] = "f" * 40  # legitimate evolution upstream
        adopted = dict(SHA)
        out = CORE.detect(tree, adopted)
        self.assertEqual(out["swallows"], [])
        self.assertEqual(out["alerts"], [C])
        self.assertEqual(out["plan"], [])

    def test_mixed_absence_and_drift(self):
        tree = dict(SHA); tree[B] = ""; tree[C] = "e" * 40
        adopted = dict(SHA)
        out = CORE.detect(tree, adopted)
        self.assertEqual(out["plan"], [{"path": B, "from": "blob:" + SHA[B]}])
        self.assertEqual(out["alerts"], [C])

    def test_adoption_of_unknown_path_is_ignored(self):
        tree = dict(SHA)
        adopted = dict(SHA); adopted["etc/rogue.ts"] = "b" * 40
        out = CORE.detect(tree, adopted)
        self.assertEqual(out["swallows"], [])
        self.assertEqual(out["plan"], [])

    def test_plan_determinism(self):
        tree = dict(SHA); tree[A] = ""; tree[D] = ""
        adopted = dict(SHA)
        o1 = json.dumps(CORE.detect(tree, adopted), sort_keys=True)
        o2 = json.dumps(CORE.detect(tree, adopted), sort_keys=True)
        self.assertEqual(o1, o2)

class TestReceiptChain(unittest.TestCase):
    def test_chain_build_and_verify(self):
        receipts = []
        prev = None
        for i in range(3):
            r = CORE.build_receipt(prev, "2026-10-24T17:00:0%dZ" % i, {"cycle": i, "verdict": "RESCUED"})
            receipts.append(r)
            prev = r["hash"]
        ok, bad = CORE.verify_chain(receipts)
        self.assertTrue(ok)
        self.assertIsNone(bad)

    def test_tampered_payload_detected(self):
        r0 = CORE.build_receipt(None, "t0", {"cycle": 0})
        r1 = CORE.build_receipt(r0["hash"], "t1", {"cycle": 1})
        r1["payload"]["cycle"] = 999  # tamper
        ok, bad = CORE.verify_chain([r0, r1])
        self.assertFalse(ok)
        self.assertEqual(bad, 1)

    def test_broken_prev_link_detected(self):
        r0 = CORE.build_receipt(None, "t0", {"cycle": 0})
        r1 = CORE.build_receipt("deadbeef", "t1", {"cycle": 1})
        ok, bad = CORE.verify_chain([r0, r1])
        self.assertFalse(ok)
        self.assertEqual(bad, 1)

    def test_empty_chain_trivially_ok(self):
        ok, bad = CORE.verify_chain([])
        self.assertTrue(ok)
        self.assertIsNone(bad)

    def test_receipt_shape(self):
        r = CORE.build_receipt(None, "t0", {"k": "v"})
        self.assertEqual(r["mode"], "receipt")
        self.assertEqual(r["at"], "t0")
        self.assertIsNone(r["prevHash"])
        self.assertEqual(len(r["hash"]), 64)

if __name__ == "__main__":
    unittest.main(verbosity=2)
