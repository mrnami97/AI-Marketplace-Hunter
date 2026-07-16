import unittest

from ai.schemas import (
    ListingAIAnalysis,
)


class GeminiSchemaTests(
    unittest.TestCase
):
    def test_analysis_schema(self):
        result = ListingAIAnalysis(
            is_relevant=True,
            category="phone",
            normalized_product_name=(
                "Apple iPhone 15 Pro"
            ),
            match_confidence=95,
            is_complete_item=True,
            condition="used",
            scam_risk="medium",
            deal_score=82,
            fair_price_low=2500,
            fair_price_high=3000,
            red_flags=[],
            positive_signals=[],
            seller_questions=[],
            negotiation_tip=(
                "Ask for battery health."
            ),
            summary=(
                "Relevant listing."
            ),
        )

        self.assertEqual(
            result.deal_score,
            82,
        )


if __name__ == "__main__":
    unittest.main()
