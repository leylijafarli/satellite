import json
import math
import random
from datetime import timedelta

from config import (
    ALTITUDE_KM,
    EARTH_RADIUS_KM,
    EARTH_SPIN,
    GRAVITY_STRENGTH,
    INCLINATION_DEG,
    SHADOW_START,
    STEP_SECONDS,
)
from security import make_seal


class Satellite:
    def __init__(self, name, start_time, key):
        self.name = name
        self.clock = start_time
        self.seconds = 0
        self.battery = 90.0
        self.temperature = 15.0
        self.packet_number = 0
        self.key = key
        self.saved_packets = []
        self.sent_count = 0         
        self.confirmed_count = 0    

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
        self.saved_packets.append({
            "satellite": self.name,
            "packet_number": self.packet_number,
            "timestamp": self.clock.isoformat(),
            "battery_percent": round(self.battery, 2),
            "temperature_c": round(self.temperature, 2),
            "altitude_km": round(ALTITUDE_KM + random.uniform(-0.2, 0.2), 2),
            "latitude": round(latitude, 2),
            "longitude": round(longitude, 2),
            "in_sunlight": sunlit,
        })

    def send_saved_packets(self, limit=None):
        """Seal and return the oldest saved packets (all of them if limit is None)."""
        to_send = self.saved_packets if limit is None else self.saved_packets[:limit]
        messages = []
        for packet in to_send:
            envelope = {
                "satellite": self.name,
                "packet": packet,
                "seal": make_seal(packet, self.key),
            }
            messages.append(json.dumps(envelope))
        self.sent_count += len(messages)
        return messages

    def acknowledge_packets(self, delivered_numbers):
        """Forget the packets the ground station has confirmed."""
        delivered_numbers = set(delivered_numbers)
        before = len(self.saved_packets)
        self.saved_packets = [
            packet
            for packet in self.saved_packets
            if packet["packet_number"] not in delivered_numbers
        ]
        self.confirmed_count += before - len(self.saved_packets)
