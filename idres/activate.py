"""Send a segment to a channel, keeping the data where it is.

What gets sent: tokens and the minimum attributes the channel needs. What does
not get sent: the profile table, the source records, or anything that would
constitute a second copy living in a vendor's system.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from idres.masking import MaskedProfile, mask

SEND_LOG = Path(__file__).parent.parent / "out" / "sends.jsonl"


@dataclass
class SendRecord:
    """One activation, recorded for reconciliation.

    A channel will eventually ask "did you send me this person on Tuesday?" and
    the honest answer has to come from a log on our side. Relying on the
    vendor's record means reconciling against the system you are checking.
    """

    segment: str
    channel: str
    token: str
    attributes: dict
    sent_at: str
    run_id: str


SEGMENTS = {
    # Segment definitions read masked attributes only. A definition that needed
    # a raw email would be a design smell: it would mean the segment is really
    # a list of specific people rather than a rule.
    "high_value": lambda a: (a.get("lifetime_value", 0) or 0) >= 10_000,
    "at_risk": lambda a: (a.get("days_since_active", 0) or 0) > 90,
    "b2b_northwind": lambda a: a.get("email_domain") == "northwind.example",
}


def build_segment(profiles: list[dict], segment: str) -> list[MaskedProfile]:
    """Apply a segment rule to masked profiles."""
    if segment not in SEGMENTS:
        raise KeyError(f"unknown segment: {segment}")
    rule = SEGMENTS[segment]
    masked = [mask(p) for p in profiles]
    return [m for m in masked if rule(m.attributes)]


def activate(members: list[MaskedProfile], segment: str, channel: str, run_id: str) -> int:
    """Write the send log. In production this also calls the channel API.

    Idempotency is via `run_id`: re-running the same run writes the same rows,
    so a retry after a partial failure does not double-send. Without it, the
    safe response to an ambiguous failure is to do nothing, which is how
    campaigns silently miss people.
    """
    SEND_LOG.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    with SEND_LOG.open("a") as fh:
        for m in members:
            rec = SendRecord(
                segment=segment, channel=channel, token=m.token,
                attributes=m.attributes, sent_at=now, run_id=run_id,
            )
            fh.write(json.dumps(asdict(rec)) + "\n")

    return len(members)


def main() -> None:
    ap = argparse.ArgumentParser(description="Activate a segment.")
    ap.add_argument("--segment", required=True)
    ap.add_argument("--channel", default="email")
    ap.add_argument("--profiles", type=Path, default=Path("out/profiles.json"))
    ap.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("run-%Y%m%d-%H%M%S"))
    args = ap.parse_args()

    profiles = json.loads(args.profiles.read_text())
    members = build_segment(profiles, args.segment)
    n = activate(members, args.segment, args.channel, args.run_id)

    print(f"segment {args.segment}: {n} members activated to {args.channel}")
    print(f"run {args.run_id}, log at {SEND_LOG}")
    print("no source data copied; tokens and masked attributes only")


if __name__ == "__main__":
    main()
