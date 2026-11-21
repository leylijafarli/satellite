import json
import math
import random
from datetime import datetime, timedelta, timezone

EARTH_RADIUS_KM = 6371.0
ALTITUDE_KM = 550.0
STEP_SECONDS = 60
HOURS_TO_SIMULATE = 24
GRAVITY_STRENGTH = 398600.4418
INCLINATION_DEG = 53.0
EARTH_SPIN = 7.2921159e-5
SHADOW_START = 0.63
MIN_ELEVATION_DEG = 10.0


class Satellite:
    def __init__(self, name, start_time):
        self.name = name
        self.clock = start_time
        self.seconds = 0
        self.battery = 90.0
        self.temperature = 15.0
        self.packet_number = 0
        self.saved_packets = []

        radius = EARTH_RADIUS_KM + ALTITUDE_KM
        self.orbit_seconds = 2 * math.pi * math.sqrt(radius**3 / GRAVITY_STRENGTH)

    def position(self):
        angle = 2 * math.pi * (self.seconds / self.orbit_seconds)
        tilt = math.radians(INCLINATION_DEG)

        x = math.cos(angle)
        y = math.sin(angle) * math.cos(tilt)
        z = math.sin(angle) * math.sin(tilt)

        latitude = math.degrees(math.asin(z))
        longitude = math.degrees(math.atan2(y, x) - EARTH_SPIN * self.seconds)
        longitude = (longitude + 180) % 360 - 180
        return latitude, longitude

    def in_sunlight(self):
        progress = (self.seconds % self.orbit_seconds) / self.orbit_seconds
        return progress < SHADOW_START

    def step(self):
        self.seconds += STEP_SECONDS
        self.clock += timedelta(seconds=STEP_SECONDS)
        minutes = STEP_SECONDS / 60

        sunlit = self.in_sunlight()
        if sunlit:
            self.battery += 0.15 * minutes
            target_temperature = 40
        else:
            self.battery -= 0.25 * minutes
            target_temperature = -20

        self.battery = max(0, min(100, self.battery))
        self.temperature += (target_temperature - self.temperature) * 0.03 * minutes
        self.temperature += random.uniform(-0.3, 0.3)

        latitude, longitude = self.position()
        self.packet_number += 1
        packet = {
            "satellite": self.name,
            "packet_number": self.packet_number,
            "timestamp": self.clock.isoformat(),
            "battery_percent": round(self.battery, 2),
            "temperature_c": round(self.temperature, 2),
            "altitude_km": round(ALTITUDE_KM + random.uniform(-0.2, 0.2), 2),
            "latitude": round(latitude, 2),
            "longitude": round(longitude, 2),
            "in_sunlight": sunlit,
        }
        self.saved_packets.append(packet)

    def send_saved_packets(self):
        to_send = self.saved_packets
        self.saved_packets = []
        return to_send


class GroundStation:
    def __init__(self, name, latitude, longitude):
        self.name = name
        self.latitude = latitude
        self.longitude = longitude
        self.received = []

    def elevation_of(self, sat_latitude, sat_longitude):
        lat1 = math.radians(self.latitude)
        lon1 = math.radians(self.longitude)
        lat2 = math.radians(sat_latitude)
        lon2 = math.radians(sat_longitude)

        cos_gap = (
            math.sin(lat1) * math.sin(lat2)
            + math.cos(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
        )
        cos_gap = max(-1.0, min(1.0, cos_gap))
        sin_gap = math.sqrt(max(0.0, 1 - cos_gap**2))

        ratio = EARTH_RADIUS_KM / (EARTH_RADIUS_KM + ALTITUDE_KM)
        return math.degrees(math.atan2(cos_gap - ratio, sin_gap))

    def can_hear(self, sat_latitude, sat_longitude):
        return self.elevation_of(sat_latitude, sat_longitude) >= MIN_ELEVATION_DEG

    def receive(self, raw_message):
        packet = json.loads(raw_message)
        self.received.append(packet)
        return packet


def main():
    random.seed(1)
    start = datetime.now(timezone.utc).replace(microsecond=0)

    sat = Satellite("SAT-1", start)
    station = GroundStation("Ground-1", latitude=67.67, longitude=58.87)

    print(f"One orbit takes {sat.orbit_seconds / 60:.1f} minutes.\n")

    total_steps = int(HOURS_TO_SIMULATE * 3600 / STEP_SECONDS)
    in_contact = False
    contact_count = 0
    delivered_this_contact = 0

    for step_number in range(1, total_steps + 1):
        sat.step()
        lat, lon = sat.position()
        hearing = station.can_hear(lat, lon)

        if hearing:
            if not in_contact:
                in_contact = True
                contact_count += 1
                delivered_this_contact = 0
                print(f"--- CONTACT #{contact_count} STARTS at {sat.clock:%H:%M} UTC ---")
            for packet in sat.send_saved_packets():
                station.receive(json.dumps(packet))
                delivered_this_contact += 1
        elif in_contact:
            in_contact = False
            print(
                f"--- CONTACT ENDS at {sat.clock:%H:%M} UTC, "
                f"{delivered_this_contact} packets delivered ---\n"
            )

        if step_number % 60 == 0:
            sun = "sun" if sat.in_sunlight() else "shadow"
            print(
                f"{sat.clock:%H:%M} | pos ({lat:6.1f}, {lon:7.1f}) | {sun:6} | "
                f"battery {sat.battery:5.1f}% | temp {sat.temperature:5.1f}C | "
                f"waiting to send: {len(sat.saved_packets)}"
            )

    print(
        f"\nDone. {contact_count} contacts, "
        f"{len(station.received)} packets received, "
        f"{len(sat.saved_packets)} still waiting."
    )


if __name__ == "__main__":
    main()
