import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import attack_demo
import config
import security
import simulation
from ground_station import (
    REASON_BAD_SEAL,
    REASON_DUPLICATE,
    REASON_MALFORMED,
    REASON_TOO_FAR_AHEAD,
    GroundStation,
)
from link import Link
from satellite import Satellite
from security import make_seal

KEY = b"k" * 32
OTHER_KEY = b"x" * 32
START = datetime(2026, 1, 1, tzinfo=timezone.utc)

BUSY_STATION = {"station_latitude": 40.41, "station_longitude": 49.87}


def make_pair(key=KEY, replay_window=config.REPLAY_WINDOW):
    sat = Satellite("SAT-1", START, key)
    station = GroundStation("Ground-1", 40.41, 49.87, key, replay_window=replay_window)
    return sat, station


def make_messages(count, key=KEY, replay_window=config.REPLAY_WINDOW):
    sat, station = make_pair(key, replay_window)
    for _ in range(count):
        sat.step()
    return sat, station, sat.send_saved_packets()


def quiet_run(**settings):
    """Run a short simulation with a fixed start time and no printing."""
    options = {"hours": 6, "verbose": False, "start_time": START, **BUSY_STATION}
    options.update(settings)
    return simulation.run_simulation(KEY, **options)


class SigningTests(unittest.TestCase):
    def test_same_packet_gives_same_seal(self):
        packet = {"a": 1, "b": 2}
        self.assertEqual(make_seal(packet, KEY), make_seal(packet, KEY))

    def test_field_order_does_not_matter(self):
        self.assertEqual(
            make_seal({"a": 1, "b": 2}, KEY),
            make_seal({"b": 2, "a": 1}, KEY),
        )

    def test_different_key_gives_different_seal(self):
        packet = {"a": 1}
        self.assertNotEqual(make_seal(packet, KEY), make_seal(packet, OTHER_KEY))

    def test_changing_the_packet_changes_the_seal(self):
        self.assertNotEqual(
            make_seal({"battery": 50}, KEY),
            make_seal({"battery": 51}, KEY),
        )


class AcceptanceTests(unittest.TestCase):
    def test_genuine_message_is_accepted(self):
        sat, station, messages = make_messages(1)
        self.assertEqual(station.receive(messages[0]), (True, "ok"))
        self.assertEqual(len(station.received), 1)

    def test_messages_in_order_are_all_accepted(self):
        sat, station, messages = make_messages(5)
        results = [station.receive(m)[0] for m in messages]
        self.assertEqual(results, [True] * 5)


class TamperingTests(unittest.TestCase):
    def test_changing_any_field_is_rejected(self):
        changes = {
            "battery_percent": 100.0,
            "temperature_c": 0.0,
            "latitude": 1.0,
            "packet_number": 999,
            "timestamp": "2030-01-01T00:00:00+00:00",
        }
        for field, new_value in changes.items():
            with self.subTest(field=field):
                sat, station, messages = make_messages(1)
                message = json.loads(messages[0])
                message["packet"][field] = new_value
                accepted, reason = station.receive(json.dumps(message))
                self.assertFalse(accepted)
                self.assertEqual(reason, REASON_BAD_SEAL)

    def test_message_sealed_with_wrong_key_is_rejected(self):
        _, station, _ = make_messages(1)
        _, _, forged_messages = make_messages(1, key=OTHER_KEY)
        accepted, reason = station.receive(forged_messages[0])
        self.assertFalse(accepted)
        self.assertEqual(reason, REASON_BAD_SEAL)

    def test_guessed_seal_is_rejected(self):
        sat, station, messages = make_messages(1)
        message = json.loads(messages[0])
        message["seal"] = "0" * 64
        accepted, _ = station.receive(json.dumps(message))
        self.assertFalse(accepted)

    def test_outer_satellite_name_not_matching_packet_is_rejected(self):
        sat, station, messages = make_messages(1)
        message = json.loads(messages[0])
        message["satellite"] = "SAT-EVIL"
        accepted, reason = station.receive(json.dumps(message))
        self.assertFalse(accepted)
        self.assertEqual(reason, REASON_MALFORMED)


class MalformedMessageTests(unittest.TestCase):
    def test_garbage_is_rejected_without_crashing(self):
        _, station = make_pair()
        bad_messages = [
            "not json at all",
            "",
            "[]",
            "{}",
            json.dumps({"packet": {}, "seal": "x", "satellite": "SAT-1"}),
            json.dumps({"packet": {"satellite": "SAT-1", "packet_number": "7"},
                        "seal": "x", "satellite": "SAT-1"}),
            json.dumps({"packet": {"satellite": "SAT-1", "packet_number": 0},
                        "seal": "x", "satellite": "SAT-1"}),
            json.dumps({"packet": {"satellite": "SAT-1", "packet_number": -3},
                        "seal": "x", "satellite": "SAT-1"}),
        ]
        for text in bad_messages:
            with self.subTest(message=text):
                accepted, reason = station.receive(text)
                self.assertFalse(accepted)
                self.assertEqual(reason, REASON_MALFORMED)
        self.assertEqual(len(station.received), 0)


class ReplayWindowTests(unittest.TestCase):
    def test_resending_an_accepted_message_is_rejected_as_duplicate(self):
        sat, station, messages = make_messages(1)
        station.receive(messages[0])
        accepted, reason = station.receive(messages[0])
        self.assertFalse(accepted)
        self.assertEqual(reason, REASON_DUPLICATE)
        self.assertEqual(len(station.received), 1)

    def test_out_of_order_packets_are_accepted(self):
        sat, station, messages = make_messages(5)
        for index in (2, 0, 1, 4, 3):                 
            accepted, _ = station.receive(messages[index])
            self.assertTrue(accepted)
        self.assertEqual(len(station.received), 5)

    def test_early_packet_cannot_be_accepted_twice(self):
        sat, station, messages = make_messages(3)
        self.assertTrue(station.receive(messages[2])[0])     
        accepted, reason = station.receive(messages[2])
        self.assertFalse(accepted)
        self.assertEqual(reason, REASON_DUPLICATE)

    def test_old_packets_stay_blocked_after_many_newer_ones(self):
        sat, station, messages = make_messages(30, replay_window=4)
        for message in messages:
            self.assertTrue(station.receive(message)[0])
        accepted, reason = station.receive(messages[0])       
        self.assertFalse(accepted)
        self.assertEqual(reason, REASON_DUPLICATE)
        self.assertEqual(len(station.received), 30)

    def test_packet_too_far_ahead_is_rejected(self):
        sat, station, messages = make_messages(6, replay_window=4)
        accepted, reason = station.receive(messages[5])      
        self.assertFalse(accepted)
        self.assertEqual(reason, REASON_TOO_FAR_AHEAD)
        self.assertTrue(station.receive(messages[3])[0])      

    def test_window_moves_forward_when_gap_is_filled(self):
        sat, station, messages = make_messages(8, replay_window=4)
        self.assertEqual(station.receive(messages[4])[1], REASON_TOO_FAR_AHEAD)  
        for index in (3, 2, 1, 0):                            
            self.assertTrue(station.receive(messages[index])[0])
        self.assertTrue(station.receive(messages[4])[0])      
        self.assertTrue(station.receive(messages[7])[0])      

    def test_early_packets_waiting_stay_below_the_window_size(self):
        sat, station, messages = make_messages(20, replay_window=8)
        for message in reversed(messages):
            station.receive(message)
        self.assertLess(len(station.windows["SAT-1"]["ahead"]), 8)

    def test_normal_traffic_still_works_after_an_attack(self):
        sat, station, messages = make_messages(3)
        station.receive(messages[0])
        station.receive(messages[0])                          
        self.assertTrue(station.receive(messages[1])[0])
        self.assertTrue(station.receive(messages[2])[0])


class AcknowledgementTests(unittest.TestCase):
    def test_only_confirmed_packets_are_removed(self):
        sat, _, _ = make_messages(5)
        sat.acknowledge_packets([1, 2, 3])
        self.assertEqual([p["packet_number"] for p in sat.saved_packets], [4, 5])
        self.assertEqual(sat.confirmed_count, 3)

    def test_unknown_numbers_are_ignored(self):
        sat, _, _ = make_messages(2)
        sat.acknowledge_packets([99, 100])
        self.assertEqual(len(sat.saved_packets), 2)
        self.assertEqual(sat.confirmed_count, 0)

    def test_empty_acknowledgement_keeps_everything(self):
        sat, _, _ = make_messages(3)
        sat.acknowledge_packets([])
        self.assertEqual(len(sat.saved_packets), 3)

    def test_acknowledged_packets_are_not_sent_again(self):
        sat, station, messages = make_messages(3)
        for message in messages:
            station.receive(message)
        sat.acknowledge_packets([1, 2, 3])
        self.assertEqual(sat.send_saved_packets(), [])

    def test_unacknowledged_packets_are_sent_again(self):
        sat, _, _ = make_messages(2)
        self.assertEqual(len(sat.send_saved_packets()), 2)

    def test_send_limit_sends_the_oldest_packets_first(self):
        sat, _, _ = make_messages(5)
        before = sat.sent_count
        messages = sat.send_saved_packets(limit=2)
        numbers = [json.loads(m)["packet"]["packet_number"] for m in messages]
        self.assertEqual(numbers, [1, 2])
        self.assertEqual(sat.sent_count, before + 2)

    def test_lost_acknowledgement_is_fixed_by_resending(self):
        sat, station, messages = make_messages(1)
        self.assertTrue(station.receive(messages[0])[0])      
        self.assertEqual(len(sat.saved_packets), 1)
        accepted, reason = station.receive(sat.send_saved_packets()[0])
        self.assertFalse(accepted)
        self.assertEqual(reason, REASON_DUPLICATE)           
        self.assertEqual(len(station.received), 1)
        sat.acknowledge_packets([1])
        self.assertEqual(sat.saved_packets, [])


class LinkTests(unittest.TestCase):
    def test_no_loss_never_drops_anything(self):
        link = Link(0.0, 0.0, seed=1)
        self.assertTrue(all(link.message_gets_through() for _ in range(200)))
        self.assertTrue(all(link.ack_gets_through() for _ in range(200)))
        self.assertEqual((link.messages_dropped, link.acks_dropped), (0, 0))

    def test_total_loss_always_drops(self):
        link = Link(1.0, 1.0, seed=1)
        self.assertFalse(any(link.message_gets_through() for _ in range(50)))
        self.assertFalse(any(link.ack_gets_through() for _ in range(50)))
        self.assertEqual((link.messages_dropped, link.acks_dropped), (50, 50))

    def test_same_seed_gives_same_losses(self):
        link_a, link_b = Link(0.5, 0.5, seed=7), Link(0.5, 0.5, seed=7)
        pattern_a = [link_a.message_gets_through() for _ in range(100)]
        pattern_b = [link_b.message_gets_through() for _ in range(100)]
        self.assertEqual(pattern_a, pattern_b)

    def test_loss_rate_is_roughly_right(self):
        link = Link(0.3, 0.0, seed=3)
        for _ in range(5000):
            link.message_gets_through()
        self.assertAlmostEqual(link.messages_dropped / 5000, 0.3, delta=0.03)

    def test_invalid_probability_is_rejected(self):
        for bad in (-0.1, 1.5):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    Link(message_loss=bad)
                with self.assertRaises(ValueError):
                    Link(ack_loss=bad)


class KeyConfigTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.key_file = Path(self.folder.name) / "shared_key.hex"

    def load(self, **env):
        with patch.dict(os.environ, env):
            if security.KEY_ENV_VAR not in env:
                os.environ.pop(security.KEY_ENV_VAR, None)  
            with contextlib.redirect_stdout(io.StringIO()):
                return security.load_shared_key(self.key_file)

    def test_new_key_is_created_and_saved(self):
        key = self.load()
        self.assertEqual(len(key), 32)
        self.assertTrue(self.key_file.exists())

    def test_same_key_is_loaded_every_time(self):
        self.assertEqual(self.load(), self.load())

    def test_environment_variable_wins_over_file(self):
        self.load()                                           
        key = self.load(**{security.KEY_ENV_VAR: "ab" * 32})
        self.assertEqual(key, bytes.fromhex("ab" * 32))

    def test_existing_key_file_is_used(self):
        self.key_file.write_text("cd" * 32 + "\n")
        self.assertEqual(self.load(), bytes.fromhex("cd" * 32))

    def test_bad_hex_is_rejected(self):
        with self.assertRaises(ValueError):
            self.load(**{security.KEY_ENV_VAR: "not-hex-at-all"})

    def test_too_short_key_is_rejected(self):
        with self.assertRaises(ValueError):
            self.load(**{security.KEY_ENV_VAR: "abcd"})

    def test_satellite_and_station_with_loaded_key_agree(self):
        key = self.load()
        sat, station = make_pair(key)
        sat.step()
        self.assertTrue(station.receive(sat.send_saved_packets()[0])[0])


class SimulationTests(unittest.TestCase):
    def test_without_loss_the_numbers_are_simple(self):
        result = quiet_run(message_loss=0.0, ack_loss=0.0)
        summary = simulation.delivery_summary(result)
        self.assertGreaterEqual(summary["contacts"], 1)
        self.assertEqual(summary["rejected"], 0)
        self.assertEqual(summary["dropped_messages"], 0)
        self.assertEqual(summary["dropped_acks"], 0)
        self.assertEqual(summary["accepted"], summary["acknowledged"])
        self.assertEqual(summary["accepted"] + summary["queued"], summary["generated"])

    def test_rejection_reasons_are_counted(self):
        sat, station, messages = make_messages(1)
        station.receive(messages[0])
        station.receive(messages[0])
        station.receive("garbage")
        counts = station.rejection_counts()
        self.assertEqual(counts[REASON_DUPLICATE], 1)
        self.assertEqual(counts[REASON_MALFORMED], 1)

    def check_nothing_is_lost(self, result):
        summary = simulation.delivery_summary(result)
        sat, station = result.satellite, result.station

        self.assertEqual(
            summary["transmitted"],
            summary["dropped_messages"] + summary["accepted"] + summary["rejected"],
        )
        self.assertEqual(summary["generated"], summary["acknowledged"] + summary["queued"])
        numbers = [p["packet_number"] for p in station.received]
        self.assertEqual(len(numbers), len(set(numbers)))
        still_kept = {p["packet_number"] for p in sat.saved_packets}
        missing = set(range(1, summary["generated"] + 1)) - set(numbers)
        self.assertTrue(missing <= still_kept)
        self.assertGreaterEqual(summary["accepted"], summary["acknowledged"])

    def test_no_packet_is_lost_with_moderate_loss(self):
        result = quiet_run(message_loss=0.2, ack_loss=0.2)
        summary = simulation.delivery_summary(result)
        self.assertGreater(summary["dropped_messages"], 0)
        self.assertGreater(summary["dropped_acks"], 0)
        self.check_nothing_is_lost(result)

    def test_no_packet_is_lost_with_heavy_loss(self):
        result = quiet_run(hours=12, message_loss=0.5, ack_loss=0.5)
        self.check_nothing_is_lost(result)

    def test_lost_confirmations_cause_duplicates_that_are_rejected(self):
        result = quiet_run(message_loss=0.0, ack_loss=0.5)
        counts = result.station.rejection_counts()
        self.assertGreater(counts[REASON_DUPLICATE], 0)
        self.check_nothing_is_lost(result)

    def test_when_every_confirmation_is_lost_the_satellite_keeps_everything(self):
        result = quiet_run(message_loss=0.0, ack_loss=1.0)
        summary = simulation.delivery_summary(result)
        self.assertEqual(summary["acknowledged"], 0)
        self.assertEqual(summary["queued"], summary["generated"])
        self.assertGreater(summary["accepted"], 0)
        self.check_nothing_is_lost(result)

    def test_retrying_delivers_everything_even_when_messages_are_lost(self):
        self.assert_everything_arrives_eventually(message_loss=0.5, ack_loss=0.0)

    def test_retrying_delivers_everything_even_when_confirmations_are_lost(self):
        self.assert_everything_arrives_eventually(message_loss=0.0, ack_loss=0.5)

    def test_retrying_delivers_everything_when_both_are_lost(self):
        self.assert_everything_arrives_eventually(message_loss=0.5, ack_loss=0.5)

    def assert_everything_arrives_eventually(self, message_loss, ack_loss):
        sat, station = make_pair()
        for _ in range(10):
            sat.step()
        link = Link(message_loss, ack_loss, seed=1)
        for _ in range(200):                     
            simulation.exchange_packets(sat, station, link)
            if not sat.saved_packets:
                break
        self.assertEqual(sat.saved_packets, [])   
        numbers = sorted(p["packet_number"] for p in station.received)
        self.assertEqual(numbers, list(range(1, 11)))   

    def test_same_seed_and_start_time_give_identical_runs(self):
        first = quiet_run(seed=5)
        second = quiet_run(seed=5)
        self.assertEqual(first.station.received, second.station.received)
        self.assertEqual(simulation.delivery_summary(first),
                         simulation.delivery_summary(second))

    def test_different_seed_gives_a_different_run(self):
        first = quiet_run(seed=5)
        second = quiet_run(seed=6)
        self.assertNotEqual(first.station.received, second.station.received)

    def test_start_time_is_used_for_timestamps(self):
        result = quiet_run(message_loss=0.0, ack_loss=0.0)
        first_packet = result.station.received[0]
        self.assertTrue(first_packet["timestamp"].startswith("2026-01-01T00:"))


class AttackDemoTests(unittest.TestCase):
    def test_demo_passes_when_security_works(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(attack_demo.main())

    def test_a_wrong_outcome_counts_as_failure(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(attack_demo.show("test", True, "ok", False))
            self.assertTrue(attack_demo.show("test", False, "no", False))


if __name__ == "__main__":
    unittest.main()
