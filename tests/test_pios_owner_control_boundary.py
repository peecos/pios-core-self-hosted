import json
import unittest
from pathlib import Path

from scripts import pios_owner_control_boundary as boundary


class OwnerControlBoundaryTests(unittest.TestCase):
    def test_neutral_configuration_health_is_explicitly_safe_disabled(self) -> None:
        health = boundary.boundary_health()
        self.assertEqual(health["status"], "passed")
        self.assertEqual(health["capability_state"], boundary.DISABLED_STATUS)
        self.assertEqual(health["owner_bind_state"], "missing")
        self.assertFalse(health["service_enabled"])
        self.assertFalse(health["listener_enabled"])
        self.assertFalse(health["topology"]["private_core_public_ip"])
        self.assertFalse(health["topology"]["public_edge_deployed"])
        self.assertEqual(len(health["required_owner_bind_inputs"]), 6)

    def test_configuration_rejects_enablement_or_owner_bind_values(self) -> None:
        enabled = boundary.neutral_configuration()
        enabled["service"]["enabled"] = True
        with self.assertRaises(boundary.OwnerControlConfigurationError):
            boundary.boundary_health(enabled)
        owner_bound = boundary.neutral_configuration()
        owner_bound["owner_bind_value"] = "not-permitted-in-neutral-image"
        with self.assertRaises(boundary.OwnerControlConfigurationError):
            boundary.validate_neutral_configuration(owner_bound)

    def test_unconfigured_interfaces_cannot_authenticate_step_up_or_recover(self) -> None:
        authentication = boundary.UnconfiguredAuthenticationAdapter()
        webauthn = boundary.UnconfiguredWebAuthnCapability()
        recovery = boundary.UnconfiguredRecoveryFlow()
        self.assertEqual(authentication.health()["status"], boundary.DISABLED_STATUS)
        self.assertEqual(webauthn.health()["status"], boundary.DISABLED_STATUS)
        self.assertEqual(recovery.health()["status"], boundary.DISABLED_STATUS)
        with self.assertRaises(boundary.OwnerBindRequired):
            authentication.authorize("export_projection")
        with self.assertRaises(boundary.OwnerBindRequired):
            webauthn.require_step_up("export_projection")
        with self.assertRaises(boundary.OwnerBindRequired):
            recovery.begin_recovery()

    def test_private_core_public_edge_template_is_not_a_deployment(self) -> None:
        template = boundary.private_core_public_edge_template()
        self.assertEqual(template["template_state"], "not_deployed")
        self.assertFalse(template["private_core"]["public_ip"])
        self.assertFalse(template["private_core"]["public_listener"])
        self.assertFalse(template["public_edge"]["deployment_authorized"])
        self.assertFalse(template["public_edge"]["configured"])
        self.assertFalse(template["public_edge"]["private_core_route_configured"])

    def test_schema_describes_only_the_neutral_disabled_shape(self) -> None:
        schema_path = (
            Path(__file__).resolve().parents[1]
            / "schemas/configs/pios_owner_control_boundary.schema.json"
        )
        schema = json.loads(schema_path.read_text())
        self.assertFalse(schema["properties"]["service"]["properties"]["enabled"]["const"])
        self.assertFalse(
            schema["properties"]["service"]["properties"]["listener_enabled"]["const"]
        )
        self.assertEqual(schema["properties"]["owner_bind_state"]["const"], "missing")
        self.assertFalse(
            schema["properties"]["topology"]["properties"]["private_core_public_ip"]["const"]
        )

    def test_module_has_no_transport_or_service_runtime_imports(self) -> None:
        source = Path(boundary.__file__).read_text()
        for forbidden in (
            "import socket",
            "import urllib",
            "import requests",
            "import http",
            "import subprocess",
            "import asyncio",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
