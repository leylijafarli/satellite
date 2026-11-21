import math
import random
import json
from datetime import datetime, timedelta

EARTH_RADIUS_KM = 6371.0
ALTITUDE_KM = 550.0
STEP_SECONDS = 60
HOURS_TO_SIMULATE = 24
GRAVITY_STRENGTH = 398600.4418
INCLINATION_DEG = 53.0  
EARTH_SPIN = 7.2921159e-5
SHADOW_START = 0.63 
STEP_SECONDS = 60 


class Satelite:
    def __init__(self, name, start_time):
        self.name = name
        self.clock = start_time 
        self.seconds = 0
        self.battery = 90.0
        self.temperature = 15.0
        self.packet_number = 0
        self.saved_packets = []

        radius = EARTH_RADIUS_KM + ALTITUDE_KM
        self.orbit_seconds = 2 * math.pi * math.sqrt(radius ** 3 / GRAVITY_STRENGTH)

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
        

class Battery:
    def __init__(self, capacity):
        self.capacity = capacity
        self.level = 100.0

    def discharge(self, amount):
        self.level = max(0, self.level - amount)

    def charge(self, amount):
        self.level = min(100, self.level + amount)
