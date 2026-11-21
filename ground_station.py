import hmac
import json
import math
from collections import Counter

from config import ALTITUDE_KM, EARTH_RADIUS_KM, MIN_ELEVATION_DEG, REPLAY_WINDOW
from security import make_seal

REASON_OK = "ok"
REASON_MALFORMED = "badly formed message"
REASON_BAD_SEAL = "bad seal (changed or fake)"
REASON_DUPLICATE = "duplicate packet (already received)"
REASON_TOO_FAR_AHEAD = "packet number too far ahead (outside window)"


class GroundStation:
    def __init__(self, name, latitude, longitude, key, replay_window=REPLAY_WINDOW):
        self.name = name
        self.latitude = latitude
        self.longitude = longitude
        self.key = key
        self.replay_window = replay_window
        self.received = []
        self.rejected = []
        self.windows = {}

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

    def _reject(self, reason, raw_message):
        self.rejected.append({"reason": reason, "message": raw_message})
        return False, reason

    def rejection_counts(self):
        return Counter(item["reason"] for item in self.rejected)

    def receive(self, raw_message):
        try:
            message = json.loads(raw_message)
            packet = message["packet"]
            seal = message["seal"]
            satellite = message["satellite"]
            number = packet["packet_number"]
            if (packet["satellite"] != satellite
                    or not isinstance(number, int) or number < 1):
                raise ValueError("inconsistent packet fields")
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return self._reject(REASON_MALFORMED, raw_message)

      
        expected_seal = make_seal(packet, self.key)
        if not hmac.compare_digest(str(seal), expected_seal):
            return self._reject(REASON_BAD_SEAL, raw_message)

   
        state = self.windows.setdefault(satellite, {"next_expected": 1, "ahead": set()})
        next_expected = state["next_expected"]
        ahead = state["ahead"]

        if number < next_expected or number in ahead:
            return self._reject(REASON_DUPLICATE, raw_message)

 
        if number >= next_expected + self.replay_window:
            return self._reject(REASON_TOO_FAR_AHEAD, raw_message)

        if number == next_expected:
            next_expected += 1
            while next_expected in ahead:
                ahead.discard(next_expected)
                next_expected += 1
            state["next_expected"] = next_expected
        else:
            ahead.add(number)

        self.received.append(packet)
        return True, REASON_OK
