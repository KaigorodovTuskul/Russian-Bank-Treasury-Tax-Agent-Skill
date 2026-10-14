import sys
import unittest
from decimal import Decimal as D
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from bond_engine import (EvidenceRequired, amortization_allocations, clean_price_result,
                         coupon_nkd, fifo_disposal, fx_sale_result, indexed_principal,
                         rate_effect, refuse_complex_event, rule_gate, split_issue_discount)


class BondEngineGoldenTests(unittest.TestCase):
    def test_T01_nkd_and_sale(self):
        self.assertEqual(coupon_nkd(60,30,12),D("42"))
        self.assertEqual(clean_price_result(980,990),D("10"))
        self.assertEqual(rate_effect(42,20)+rate_effect(10,25),D("10.9"))

    def test_T02_floating_coupon(self):
        self.assertEqual(rate_effect(coupon_nkd(40,0),20),D("8"))

    def test_T03_eligible_corporate(self):
        self.assertEqual(rate_effect(60,20)+rate_effect(40,25),D("22"))
        self.assertEqual(rule_gate("BND-CORP-RUB-INT-20","2026-03-31")["status"],
                         "UNVERIFIED_LEGAL_EDITION")

    def test_T04_nontraded(self):
        self.assertEqual(rate_effect(60,25)+rate_effect(40,25),D("25"))

    def test_T05_municipal_loss(self):
        self.assertEqual(rate_effect(40,20)+rate_effect(-50,25,loss_usable=True),D("-4.5"))
        with self.assertRaises(EvidenceRequired):
            rate_effect(-50,25)

    def test_T06_original_issue_discount(self):
        result=split_issue_discount(1000,920,900)
        self.assertEqual(result["issue_interest"],D("80"))
        self.assertEqual(result["other_redemption_result"],D("20"))
        self.assertEqual(rate_effect(80,20)+rate_effect(20,25),D("21"))

    def test_T07_market_discount_and_premium(self):
        self.assertEqual(rate_effect(clean_price_result(900,1000),25)+rate_effect(50,20),D("35"))
        self.assertEqual(rate_effect(clean_price_result(1040,1000),25,loss_usable=True)+rate_effect(60,20),D("2"))

    def test_T08_amortization(self):
        result=amortization_allocations(960,1000,[400,600])
        self.assertEqual(result["cost_allocations"],[D("384"),D("576")])
        self.assertEqual(result["realized_gains"],[D("16"),D("24")])
        self.assertEqual(result["remaining_cost"],D("0"))

    def test_T09_indexed_principal(self):
        x=indexed_principal(1000,1020,20,1000,1020,20)
        self.assertEqual(x["economic_profit"],D("40"))
        self.assertEqual(x["taxable_price_gain"],D("0"))
        with self.assertRaises(EvidenceRequired):
            indexed_principal(1000,990,0,1000,990,-10)

    def test_T10_fx_sale(self):
        x=fx_sale_result(1000,90,1000,100)
        self.assertEqual(x["realized_result_rub"],D("10000"))
        self.assertEqual(x["monthly_bond_fx_revaluation_rub"],D("0"))

    def test_T11_replacement_stop(self):
        with self.assertRaises(EvidenceRequired):
            refuse_complex_event("replacement")

    def test_T12_fifo(self):
        x=fifo_disposal([(10,940),(10,980)],10,970)
        self.assertEqual(x["cost"],D("9400"))
        self.assertEqual(x["gain"],D("300"))

    def test_T13_nontraded_loss_stop(self):
        with self.assertRaises(EvidenceRequired):
            refuse_complex_event("nontraded_loss")

    def test_T14_cancelled_coupon_stop(self):
        with self.assertRaises(EvidenceRequired):
            refuse_complex_event("cancelled_coupon")

    def test_T15_write_down_stop(self):
        with self.assertRaises(EvidenceRequired):
            refuse_complex_event("subordinated_write_down")

    def test_T16_withholding_stop(self):
        with self.assertRaises(EvidenceRequired):
            refuse_complex_event("cross_border_nkd")

    def test_rule_gate_never_approves(self):
        x=rule_gate("BND-OFZ-INT-20","2026-10-14",
                    source_edition_verified=True,predicates_verified=True)
        self.assertEqual(x["status"],"PROVISIONAL_PENDING_HUMAN_REVIEW")
        self.assertIsNone(x["approved_tax_amount"])
        self.assertEqual(rule_gate("BND-GEN-25","2024-01-01")["status"],
                         "HISTORICAL_EDITION_REQUIRED")
        self.assertEqual(rule_gate("BND-WRITEDOWN-CONVERSION","2026-10-14")["status"],
                         "BLOCKED_COMPLEX_LEGAL_EVENT")

    def test_bad_inputs(self):
        with self.assertRaises(ValueError): fifo_disposal([(10,940)],11,970)
        with self.assertRaises(ValueError): amortization_allocations(960,1000,[700,400])
        with self.assertRaises(ValueError): coupon_nkd(10,20)
        with self.assertRaises(ValueError): rate_effect(10,120)


if __name__ == "__main__":
    unittest.main()
