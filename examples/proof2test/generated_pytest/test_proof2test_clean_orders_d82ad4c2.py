"""Generated DataProof regression; set DATAPROOF_TARGET_SQL to the model SQL file."""

import os
from pathlib import Path

from dataproof_verifier.proof2test import assert_generated_case


def test_proof2test_clean_orders_d82ad4c2() -> None:
    target = os.environ.get("DATAPROOF_TARGET_SQL")
    assert target, "DATAPROOF_TARGET_SQL must name the implementation SQL file"
    assert_generated_case(
        Path(__file__).with_name("fixture.json"),
        Path(target),
        "d5b39ddcf8a9e2481fbfe7fd7dfd6aefb5a0307fb23d558fe192533145ea1dd8",
    )
