from pathlib import Path
import hashlib
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import core

class ArtifactContracts(unittest.TestCase):
    def test_source_and_artifact_digests(self):
        manifest = json.loads((ROOT / "results/manifest.json").read_text())
        for rel, digest in manifest["source_sha256"].items():
            self.assertEqual(hashlib.sha256((ROOT / rel).read_bytes()).hexdigest(), digest, rel)
        for rel, digest in manifest["artifact_sha256"].items():
            self.assertEqual(hashlib.sha256((ROOT / "results" / rel).read_bytes()).hexdigest(), digest, rel)

    def test_generator_reproduces_committed_inputs(self):
        self.assertEqual(core.generate(), json.loads((ROOT / "data/dataset.json").read_text()))

import copy

def tiny():
    return {"orders":[{"order_id":"a","accepted_at":0},{"order_id":"b","accepted_at":0},{"order_id":"new","accepted_at":9}],
      "payments":[{"event_id":"p1","order_id":"a","amount_cents":100,"observed_at":1}]*2 +
                 [{"event_id":"p2","order_id":"b","amount_cents":50,"observed_at":1}],
      "refunds":[{"event_id":"r1","order_id":"a","amount_cents":20,"observed_at":2},
                 {"event_id":"r2","order_id":"a","amount_cents":10,"observed_at":3}],
      "fulfillment":[{"event_id":"f1","order_id":"a","status":"delivered","observed_at":2}]*2+
                    [{"event_id":"f2","order_id":"b","status":"cancelled","observed_at":2}]}

class MetricContracts(unittest.TestCase):
    def test_known_integer_cent_answer(self):
        result, rows = core.metrics(tiny(),10,5)
        self.assertEqual(2,result["event_grain"]["denominator"])
        self.assertEqual(120,result["event_grain"]["net_cents"])
        self.assertEqual(.5,result["event_grain"]["completion_rate"])
        self.assertGreater(result["naive_join"]["denominator"],2)

    def test_future_event_cannot_enter_asof_metric(self):
        data=tiny(); data["refunds"][0]["observed_at"]=11
        result,_=core.metrics(data,10,5)
        self.assertEqual(140,result["event_grain"]["net_cents"])

    def test_empty_mature_population_has_no_division_artifact(self):
        result,_=core.metrics(tiny(),0,5)
        self.assertEqual(0,result["event_grain"]["denominator"])
        self.assertIsNone(result["event_grain"]["completion_rate"])

    def test_conflicting_duplicate_event_fails_closed(self):
        data=copy.deepcopy(tiny()); data["payments"][1]={**data["payments"][1],"amount_cents":101}
        with self.assertRaises(ValueError): core.metrics(data,10)

    def test_unknown_order_event_is_not_silently_dropped(self):
        data=tiny(); data["payments"].append({"event_id":"x","order_id":"absent","amount_cents":1,"observed_at":0})
        with self.assertRaises(ValueError): core.metrics(data,10)

    def test_money_and_time_reject_bool_float_and_nonfinite(self):
        for value in [True,-1,1.5,float("nan"),float("inf")]:
            with self.subTest(value=value), self.assertRaises(ValueError): core.metrics(tiny(),value)
        data=copy.deepcopy(tiny()); data["payments"][0]["amount_cents"]=-1
        with self.assertRaises(ValueError): core.metrics(data,10)

    def test_duplicate_orders_rejected(self):
        data=tiny(); data["orders"].append(data["orders"][0])
        with self.assertRaises(ValueError): core.metrics(data,10)

    def test_identity_types_and_ever_delivered_contract(self):
        for value in [None,"",True,7]:
            data=copy.deepcopy(tiny());data["orders"][0]["order_id"]=value
            with self.subTest(value=value),self.assertRaises(ValueError):core.metrics(data,10)
            data=copy.deepcopy(tiny());data["payments"][0]={**data["payments"][0],"event_id":value}
            with self.assertRaises(ValueError):core.metrics(data,10)
        data=tiny();data["fulfillment"].append({"event_id":"later","order_id":"a","status":"cancelled","observed_at":8})
        result,_=core.metrics(data,10,5)
        self.assertEqual(1,result["event_grain"]["delivered"])

    def test_order_audit_reconciles_totals(self):
        result, rows=core.metrics(core.generate(),100,5)
        self.assertEqual(sum(r["captured_cents"]-r["refunded_cents"] for r in rows),result["event_grain"]["net_cents"])
        self.assertEqual(sum(r["delivered"] for r in rows),result["event_grain"]["delivered"])
        self.assertEqual(len(rows),result["event_grain"]["denominator"])
