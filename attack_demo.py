import json
import secrets
import sys
from datetime import datetime, timezone

from ground_station import GroundStation
from satellite import Satellite


def show(title, accepted, reason, should_accept):
    worked = (accepted == should_accept)
    outcome = "accepted" if accepted else "rejected"
    verdict = "PASS" if worked else "FAIL"
    print(f"[{verdict}] {title}\n        ground station {outcome}: {reason}\n")
    return worked


def main():
    """Runs every scenario. Returns True only if all of them behaved correctly."""
    key = secrets.token_bytes(32)    # the attacker never gets to see this
    start = datetime.now(timezone.utc).replace(microsecond=0)
    sat = Satellite("SAT-1", start, key)
    station = GroundStation("Ground-1", latitude=40.41, longitude=49.87, key=key)

    for _ in range(5):
        sat.step()
    m1, m2, m3, m4, m5 = sat.send_saved_packets()

    results = []

    accepted, reason = station.receive(m1)
    results.append(show("Normal message from the satellite", accepted, reason, True))

    # Attack 1: 
    tampered = json.loads(m2)
    tampered["packet"]["battery_percent"] = 100.0
    accepted, reason = station.receive(json.dumps(tampered))
    results.append(show("Attack 1: changed the battery to 100%", accepted, reason, False))

    # Attack 2: 
    fake = {
        "satellite": "SAT-1",
        "packet": {
            "satellite": "SAT-1",
            "packet_number": 999,
            "timestamp": start.isoformat(),
            "battery_percent": 1.0,
            "temperature_c": 200.0,
            "altitude_km": 550.0,
            "latitude": 0.0,
            "longitude": 0.0,
            "in_sunlight": True,
        },
        "seal": "0" * 64,    
    }
    accepted, reason = station.receive(json.dumps(fake))
    results.append(show("Attack 2: invented a fake packet", accepted, reason, False))

    # Attack 3: 
    accepted, reason = station.receive(m1)
    results.append(show("Attack 3: re-sent a message right away", accepted, reason, False))

   
    accepted, reason = station.receive(m4)
    results.append(show("Genuine packet 4 arrives early", accepted, reason, True))
    accepted, reason = station.receive(m2)
    results.append(show("Genuine packet 2 arrives late", accepted, reason, True))
    accepted, reason = station.receive(m3)
    results.append(show("Genuine packet 3 arrives late", accepted, reason, True))

    # Attack 4:
    accepted, reason = station.receive(m1)
    results.append(show("Attack 4: re-sent the oldest message later", accepted, reason, False))

   
    accepted, reason = station.receive(m5)
    results.append(show("Next normal message afterwards", accepted, reason, True))

    print(f"{sum(results)} of {len(results)} checks passed.")
    return all(results)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
