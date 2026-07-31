"""Neutral, safe-disabled owner-control capability boundary for PIOS Starter.

This module provides configuration and interface shapes only. It has no
listener, network transport, authentication implementation, identity-provider
configuration, passkey enrollment, or action execution path.
"""
from __future__ import annotations

from typing import Any, Mapping, Protocol

from scripts import pios_canonical_source_primitives as primitives

CONFIG_SCHEMA = "pios_owner_control_boundary_config_v1"
HEALTH_SCHEMA = "pios_owner_control_boundary_health_v1"
TOPOLOGY_TEMPLATE_SCHEMA = "pios_private_core_public_edge_template_v1"
DISABLED_STATUS = "disabled_unconfigured"


class OwnerBindRequired(ValueError):
    """Raised when a neutral Starter boundary is asked to act before Owner Bind."""


class OwnerControlConfigurationError(ValueError):
    """Raised when configuration differs from the strict neutral disabled shape."""


class AuthenticationAdapter(Protocol):
    """Future authentication adapter boundary; no configured adapter is included."""

    def health(self) -> dict[str, Any]:
        """Return a capability-state record without authenticating anyone."""

    def authorize(self, action: str) -> None:
        """Authorize an action only after a future Owner Bind implementation exists."""


class WebAuthnCapabilityBoundary(Protocol):
    """Future WebAuthn boundary; this Starter includes no relying-party values."""

    def health(self) -> dict[str, Any]:
        """Return an unconfigured capability-state record."""

    def require_step_up(self, action: str) -> None:
        """Require a future configured step-up mechanism."""


class RecoveryFlow(Protocol):
    """Future recovery boundary; this Starter includes no recovery factor."""

    def health(self) -> dict[str, Any]:
        """Return an unconfigured recovery-state record."""

    def begin_recovery(self) -> None:
        """Begin recovery only after a future Owner Bind implementation exists."""


def neutral_configuration() -> dict[str, Any]:
    """Return the only configuration shape accepted in a neutral Starter image."""
    return {
        "schema_version": CONFIG_SCHEMA,
        "owner_bind_state": "missing",
        "service": {"enabled": False, "listener_enabled": False},
        "authentication": {"adapter_state": "unconfigured"},
        "webauthn": {"capability_state": "unconfigured"},
        "recovery": {"flow_state": "unconfigured"},
        "topology": {"private_core_public_ip": False, "public_edge_deployed": False},
    }


def required_owner_bind_inputs() -> tuple[str, ...]:
    """Name neutral categories that remain absent from the reusable image."""
    return (
        "stable_https_origin",
        "authentication_adapter_configuration",
        "webauthn_relying_party_binding",
        "recovery_flow_configuration",
        "session_csrf_secret_material",
        "edge_to_private_core_access_policy",
    )


def validate_neutral_configuration(configuration: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed unless every Owner Bind-dependent capability stays disabled."""
    if not isinstance(configuration, Mapping):
        raise OwnerControlConfigurationError("owner-control configuration must be an object")
    normalized = primitives.canonical_json_value(configuration)
    expected = neutral_configuration()
    if normalized != expected:
        raise OwnerControlConfigurationError(
            "neutral Starter accepts only the all-disabled, unconfigured boundary shape"
        )
    return expected


class UnconfiguredAuthenticationAdapter:
    """Safe placeholder that never authenticates or authorizes an action."""

    def health(self) -> dict[str, Any]:
        return {"status": DISABLED_STATUS, "adapter_state": "unconfigured"}

    def authorize(self, action: str) -> None:
        raise OwnerBindRequired("authentication adapter is unavailable until Owner Bind")


class UnconfiguredWebAuthnCapability:
    """Safe placeholder with no relying-party, credential, or enrollment data."""

    def health(self) -> dict[str, Any]:
        return {"status": DISABLED_STATUS, "capability_state": "unconfigured"}

    def require_step_up(self, action: str) -> None:
        raise OwnerBindRequired("step-up capability is unavailable until Owner Bind")


class UnconfiguredRecoveryFlow:
    """Safe placeholder with no recovery factor or recovery operation."""

    def health(self) -> dict[str, Any]:
        return {"status": DISABLED_STATUS, "flow_state": "unconfigured"}

    def begin_recovery(self) -> None:
        raise OwnerBindRequired("recovery flow is unavailable until Owner Bind")


def private_core_public_edge_template() -> dict[str, Any]:
    """Return a non-deployment template for the future private-Core/edge split."""
    return {
        "schema_version": TOPOLOGY_TEMPLATE_SCHEMA,
        "template_state": "not_deployed",
        "private_core": {
            "public_ip": False,
            "public_listener": False,
            "operator_access": "separate_private_control_plane",
        },
        "public_edge": {
            "deployment_authorized": False,
            "configured": False,
            "private_core_route_configured": False,
        },
        "owner_bind_required_inputs": list(required_owner_bind_inputs()),
    }


def boundary_health(configuration: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return passed health only for the safe disabled, unconfigured baseline."""
    config = neutral_configuration() if configuration is None else configuration
    validate_neutral_configuration(config)
    authentication = UnconfiguredAuthenticationAdapter().health()
    webauthn = UnconfiguredWebAuthnCapability().health()
    recovery = UnconfiguredRecoveryFlow().health()
    topology = private_core_public_edge_template()
    return {
        "schema_version": HEALTH_SCHEMA,
        "status": "passed",
        "capability_state": DISABLED_STATUS,
        "owner_bind_state": "missing",
        "service_enabled": False,
        "listener_enabled": False,
        "authentication": authentication,
        "webauthn": webauthn,
        "recovery": recovery,
        "topology": {
            "private_core_public_ip": topology["private_core"]["public_ip"],
            "public_edge_deployed": topology["public_edge"]["configured"],
        },
        "required_owner_bind_inputs": list(required_owner_bind_inputs()),
    }
