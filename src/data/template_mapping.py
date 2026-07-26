

class TemplateMap():
    def __init__(self):
        self.event_name: str | None = None
        self.schedule: str | None = None
        self.custom_text: str | None = None
        self.start_time_short: str | None = None
        self.start_time_relative: str | None = None
        self.start_time_long: str | None = None
        self.tickets_number: int | None = None
        self.tickets_emoji: str | None = None
        self.tickets_word: str | None = None
        self.role_ping: str | None = None
        self.channel_score: str | None = None
        self.channel_score: str | None = None


    @property
    def mapping(self) -> dict[str | None]:
        return {
            "event_name": rf"{self.event_name}",
            "event_name_upper": rf"{self.event_name.upper()}",
            "schedule": rf"{self.schedule}",
            "custom_text": rf"{self.custom_text}",
            "start_time_short": rf"{self.start_time_short}",
            "start_time_relative": rf"{self.start_time_relative}",
            "start_time_long": rf"{self.start_time_long}",
            "tickets_number": str(self.tickets_number),
            "tickets_emoji": rf"{self.tickets_emoji}",
            "tickets_word": rf"{self.tickets_word}",
            "role_ping": self.role_ping,
            "channel_score": self.channel_score,
            "channel_post": self.channel_score,
        }