# Satellite Telemetry Security Simulation

A small, dependency-free Python project that simulates a low Earth orbit satellite sending telemetry to a ground station over an unreliable radio link. It demonstrates packet authentication, replay protection, retransmission after packet or acknowledgement loss, and basic link and delivery metrics.

> **Educational simulation:** the orbit, sunlight, power, temperature, and radio-link models are intentionally simplified. This project is not flight software and should not be used to design or operate a real spacecraft or communications system.

## What it demonstrates

- A satellite generates telemetry once per simulation step and stores packets until delivery is confirmed.
- A ground station can receive packets only during simulated visibility windows.
- The link can independently drop downlink messages and acknowledgements.
- The satellite retries unconfirmed packets. The ground station identifies duplicates so a lost acknowledgement does not create a second accepted copy.
- HMAC-SHA-256 seals detect packet changes and packets created without the shared key.
- A bounded replay window rejects duplicates and stale packets while allowing packets to arrive out of order within the window.
- A separate attack demo exercises normal traffic, tampering, forgery, replay, and out-of-order delivery.

**Integrity is not encryption.** HMAC authenticates a packet and detects changes; the JSON telemetry remains readable. The simulation also gives the satellite and ground station the same shared key, which is a teaching convenience rather than a complete key-management design.

## Requirements

- Python 3.10 or newer
- No third-party packages

## Run it

Open a terminal in this folder and start the 24-hour simulation:

```bash
python3 simulation.py
```

The first run creates `shared_key.hex` beside the source files and reuses it on later runs. The file is created with owner-only permissions and is listed in `.gitignore`. Keep it private; anyone with this key can create packets that pass the simulation's HMAC check.

To supply a key instead, set `TELEMETRY_SHARED_KEY` to at least 32 hexadecimal characters (16 bytes):

```bash
export TELEMETRY_SHARED_KEY="replace-with-at-least-32-hex-characters"
python3 simulation.py
```

The environment variable takes precedence over `shared_key.hex`. Do not commit real secrets or paste them into source code.

Run the security scenarios:

```bash
python3 attack_demo.py
```

The demo prints PASS/FAIL for each scenario and exits with status `0` if all expected outcomes occur, or `1` if any scenario fails.

Run the test suite:

```bash
python3 -m unittest -v test_telemetry
```

The tests use Python's standard library and do not need the generated shared-key file; they use temporary keys and temporary files.

## Configuration

Simulation defaults live in `config.py`:

| Setting | Default | Meaning |
| --- | ---: | --- |
| `ALTITUDE_KM` | 550 km | Simplified circular orbit altitude |
| `INCLINATION_DEG` | 53° | Orbit inclination used by the position model |
| `STEP_SECONDS` | 60 s | Time advanced per simulation step |
| `HOURS_TO_SIMULATE` | 24 h | Default simulation duration |
| `MIN_ELEVATION_DEG` | 10° | Minimum elevation for ground-station contact |
| `MESSAGE_LOSS_PROBABILITY` | 0.10 | Chance a downlink message is dropped |
| `ACK_LOSS_PROBABILITY` | 0.10 | Chance a delivery acknowledgement is dropped |
| `MAX_MESSAGES_PER_STEP` | 128 | Maximum queued packets attempted per step |
| `REPLAY_WINDOW` | 256 packets | Maximum sequence-number distance accepted ahead of the next expected packet |

`run_simulation()` in `simulation.py` accepts options for duration, station coordinates, verbosity, random seed, start time, and both loss probabilities. This makes shorter and repeatable runs convenient from Python:

```python
from datetime import datetime, timezone

from security import load_shared_key
from simulation import delivery_summary, run_simulation

result = run_simulation(
    load_shared_key(),
    hours=6,
    seed=7,
    start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
    message_loss=0.2,
    ack_loss=0.1,
    verbose=False,
)
print(delivery_summary(result))
```

A fixed seed and start time make the pseudo-random simulation repeatable with the same Python implementation and configuration.

## Reading the delivery summary

At the end of a run, the simulation reports contacts, packets generated and transmitted, downlink losses, accepted packets, rejected packets grouped by reason, lost acknowledgements, confirmed packets, queued packets, and packets not yet received by the ground station.

A packet can be received by the ground station but remain queued on the satellite if its acknowledgement is lost. It will be retransmitted; the ground station rejects that retry as a duplicate and confirms it again. This is expected behavior in the simulation.

## Project structure

| File | Responsibility |
| --- | --- |
| `config.py` | Orbit, station, timing, link-loss, and replay-window defaults |
| `satellite.py` | Satellite position, telemetry generation, queueing, sealing, and acknowledgements |
| `ground_station.py` | Visibility calculation, HMAC verification, replay-window checks, and rejection counts |
| `security.py` | Canonical packet serialization, HMAC-SHA-256 seals, and shared-key loading |
| `link.py` | Seedable simulation of dropped messages and acknowledgements |
| `simulation.py` | Main simulation loop, retransmission exchange, and delivery summary |
| `attack_demo.py` | Runnable examples of tampering, forgery, replay, and valid out-of-order traffic |
| `test_telemetry.py` | Unit tests for security, replay handling, retries, key loading, and simulation accounting |
| `firstsmth.py` | Earlier standalone prototype; the modular entry point is `simulation.py` |

## Model and security limits

This project is designed to make core ideas visible, not to model a real satellite link precisely:

- The orbit is represented with a simplified circular trajectory and Earth rotation; it does not use a full orbital propagator or real ephemeris data.
- Sunlight is approximated as a fixed fraction of each orbit. Battery and temperature changes are illustrative values, not validated spacecraft thermal or power models.
- Link losses are independent random events, not a detailed radio, antenna, weather, or interference model.
- HMAC provides integrity and shared-key authentication, but does not hide telemetry. The demonstration does not model key rotation, per-satellite key provisioning, secure hardware, or a real acknowledgement channel.
- Replay state is held in memory and resets when the ground-station process restarts.

These boundaries make the code suitable for learning and experimentation while keeping its claims clear.
