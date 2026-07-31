import unittest

from scripts import prove_pios_starter_capability_lifecycle as proof


class StarterCapabilityLifecycleProofTests(unittest.TestCase):
    def test_generated_fixture_contains_empty_state_and_capability_markers(self) -> None:
        user_data = proof.build_capability_user_data(
            owner_id="owner_synthetic_b6_test",
            owner_slug="synthetic-b6-test",
            env_name="proof",
        )
        for marker in (
            proof.CAPABILITY_PROOF_START,
            proof.CAPABILITY_EMPTY_STATE_OK,
            proof.CAPABILITY_LIFECYCLE_PASSED,
            proof.CAPABILITY_PROOF_DONE,
        ):
            self.assertIn(marker, user_data)
        self.assertIn("test ! -e /var/lib/pios-core", user_data)
        self.assertIn("OriginalByteCaptureTemplate", user_data)
        self.assertIn("LocalSyntheticApprovalHarness", user_data)
        self.assertIn("boundary_health", user_data)
        self.assertIn("PYTHONPATH=/opt/pios-core", user_data)

    def test_generated_fixture_contains_no_transport_client_import(self) -> None:
        fixture = proof.capability_fixture_script()
        for forbidden in (
            "import socket",
            "import urllib",
            "import requests",
            "import http",
            "import subprocess",
        ):
            self.assertNotIn(forbidden, fixture)


if __name__ == "__main__":
    unittest.main()
