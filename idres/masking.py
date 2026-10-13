"""Column masking so a segment can be built without reading identifiers.

The access model: an analyst building an audience needs to filter on behaviour
and attributes. They do not need the email address, and the activation step
does not need it either — it needs a stable token it can hand to a channel.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

# Per-deployment salt. Without a salt, hashed emails are trivially reversible
# with a rainbow table, since the space of real email addresses is small and
# enumerable. The salt must live outside the data, or it travels with any copy
# of the table and protects nothing.
SALT = os.environ.get("IDRES_MASK_SALT", "dev-only-not-a-real-salt")

IDENTIFIER_COLUMNS = {"email", "phone", "legal_name"}


@dataclass
class MaskedProfile:
    entity_id: str
    token: str
    attributes: dict


def token_for(entity_id: str) -> str:
    """A stable, non-reversible token for one entity."""
    return hashlib.sha256(f"{SALT}|{entity_id}".encode()).hexdigest()[:24]


def mask(profile: dict, allow: set[str] | None = None) -> MaskedProfile:
    """Strip identifier columns, keeping analysable attributes.

    `allow` exists for the narrow case where a specific identifier is genuinely
    required, and every use of it should be justified in review. The default is
    to strip everything in IDENTIFIER_COLUMNS.
    """
    allowed = allow or set()
    attributes = {
        k: v for k, v in profile.items()
        if not k.startswith("_")
        and k != "entity_id"
        and (k not in IDENTIFIER_COLUMNS or k in allowed)
    }

    # Derived attributes let analysts segment WITHOUT the raw value. Domain is
    # useful for B2B targeting and reveals the company, not the person.
    email = profile.get("email")
    if email and "@" in str(email) and "email" not in allowed:
        attributes["email_domain"] = str(email).partition("@")[2]

    return MaskedProfile(
        entity_id=profile["entity_id"],
        token=token_for(profile["entity_id"]),
        attributes=attributes,
    )
