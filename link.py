import random


class Link:
    def __init__(self, message_loss=0.0, ack_loss=0.0, seed=None):
        for name, value in (("message_loss", message_loss), ("ack_loss", ack_loss)):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1, got {value}")
        self.message_loss = message_loss
        self.ack_loss = ack_loss
        self.rng = random.Random(seed)
        self.messages_dropped = 0
        self.acks_dropped = 0

    def message_gets_through(self):
        if self.rng.random() < self.message_loss:
            self.messages_dropped += 1
            return False
        return True

    def ack_gets_through(self):
        if self.rng.random() < self.ack_loss:
            self.acks_dropped += 1
            return False
        return True