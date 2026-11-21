import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone

from config import (
    ACK_LOSS_PROBABILITY,
    HOURS_TO_SIMULATE,
    MAX_MESSAGES_PER_STEP,
    MESSAGE_LOSS_PROBABILITY,
    STATION_LATITUDE,
    STATION_LONGITUDE,
    STEP_SECONDS,
)
from ground_station import REASON_DUPLICATE, GroundStation
from link import Link
from satellite import Satellite
from security import load_shared_key


@dataclass
class SimulationResult:
    satellite: Satellite
    station: GroundStation
    link: Link
    contacts: int


def exchange_packets(sat, station, link, limit=MAX_MESSAGES_PER_STEP):
    new_packets = 0
    confirmed_numbers = []
    for message in sat.send_saved_packets(limit=limit):
        if not link.message_gets_through():
            continue                          # lost on the way down
        accepted, reason = station.receive(message)
        if accepted:
            new_packets += 1
        if accepted or reason == REASON_DUPLICATE:
            if link.ack_gets_through():       
                number = json.loads(message)["packet"]["packet_number"]
                confirmed_numbers.append(number)
    sat.acknowledge_packets(confirmed_numbers)
    return new_packets


def run_simulation(key, hours=HOURS_TO_SIMULATE,
                   station_latitude=STATION_LATITUDE,
                   station_longitude=STATION_LONGITUDE,
                   verbose=True, seed=1, start_time=None,
                   message_loss=MESSAGE_LOSS_PROBABILITY,
                   ack_loss=ACK_LOSS_PROBABILITY):
    
    if seed is not None:
        random.seed(seed)
    if start_time is None:
        start_time = datetime.now(timezone.utc).replace(microsecond=0)

    sat = Satellite("SAT-1", start_time, key)
    station = GroundStation("Ground-1", station_latitude, station_longitude, key)
    link = Link(message_loss, ack_loss, seed=seed)
    if verbose:
        print(f"One orbit takes {sat.orbit_seconds / 60:.1f} minutes.\n")

    total_steps = int(hours * 3600 / STEP_SECONDS)
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
                if verbose:
                    print(f"--- CONTACT #{contact_count} STARTS at {sat.clock:%H:%M} UTC ---")

            delivered_this_contact += exchange_packets(sat, station, link)
        elif in_contact:
            in_contact = False
            if verbose:
                print(
                    f"--- CONTACT ENDS at {sat.clock:%H:%M} UTC, "
                    f"{delivered_this_contact} new packets delivered ---\n"
                )

        if verbose and step_number % 60 == 0:
            sun = "sun" if sat.in_sunlight() else "shadow"
            print(
                f"{sat.clock:%H:%M} | pos ({lat:6.1f}, {lon:7.1f}) | {sun:6} | "
                f"battery {sat.battery:5.1f}% | temp {sat.temperature:5.1f}C | "
                f"waiting to send: {len(sat.saved_packets)}"
            )

    return SimulationResult(sat, station, link, contact_count)


def delivery_summary(result):
    """The key delivery numbers, as a dictionary."""
    sat, station, link = result.satellite, result.station, result.link
    return {
        "contacts": result.contacts,
        "generated": sat.packet_number,          
        "transmitted": sat.sent_count,            
        "dropped_messages": link.messages_dropped,  
        "accepted": len(station.received),       
        "rejected": len(station.rejected),        
        "dropped_acks": link.acks_dropped,        
        "acknowledged": sat.confirmed_count,      
        "queued": len(sat.saved_packets),         
        "missing_at_ground": sat.packet_number - len(station.received),
    }


def print_summary(result):
    summary = delivery_summary(result)
    print("\nDelivery summary")
    print(f"  contacts:                  {summary['contacts']}")
    print(f"  packets generated:         {summary['generated']}")
    print(f"  messages sent:             {summary['transmitted']}")
    print(f"    lost on the way down:    {summary['dropped_messages']}")
    print(f"    accepted (new packets):  {summary['accepted']}")
    print(f"    rejected:                {summary['rejected']}")
    for reason, count in result.station.rejection_counts().items():
        print(f"      {reason}: {count}")
    print(f"  confirmations lost:        {summary['dropped_acks']}")
    print(f"  confirmed on satellite:    {summary['acknowledged']}")
    print(f"  still kept on satellite:   {summary['queued']}")
    print(f"  not yet at ground station: {summary['missing_at_ground']}")


def main():
    key = load_shared_key()
    result = run_simulation(key)
    print_summary(result)


if __name__ == "__main__":
    main()
