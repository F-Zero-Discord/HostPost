from dataclasses import dataclass


@dataclass
class TemplateMap:
    """The `str.format` fields of the 1hr, 10min and results templates in
    `event_messages`. Filled by `build_posts` before `mapping` is read."""

    event_name: str = ""
    schedule: str = ""
    custom_text: str = ""
    start_time_short: str = ""
    start_time_relative: str = ""
    start_time_long: str = ""
    tickets_number: int = 0
    tickets_emoji: str = ""
    tickets_word: str = ""
    role_ping: str = ""
    channel_score: str = ""

    @property
    def mapping(self) -> dict[str, str]:
        return {
            "event_name": self.event_name,
            "event_name_upper": self.event_name.upper(),
            "schedule": self.schedule,
            "custom_text": self.custom_text,
            "start_time_short": self.start_time_short,
            "start_time_relative": self.start_time_relative,
            "start_time_long": self.start_time_long,
            "tickets_number": str(self.tickets_number),
            "tickets_emoji": self.tickets_emoji,
            "tickets_word": self.tickets_word,
            "role_ping": self.role_ping,
            "channel_score": self.channel_score,
            "channel_post": self.channel_score,
        }
