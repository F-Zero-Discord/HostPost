

class TemplateMap():
    def __init__(self):
        self.schedule: str | None = None
        self.custom_text: str | None = None
        self.start_time_short: str | None = None
        self.start_time_relative: str | None = None
        self.start_time_long: str | None = None
        self.tickets_number: int | None = None
        self.tickets_emoji: str | None = None
        self.role_ping: str | None = None
        self.channel_score: str | None = None
        self.channel_score: str | None = None


    @property
    def mapping(self) -> dict[str | None]:
        return {
            "schedule": rf"{self.schedule}",
            "custom_text": rf"{self.custom_text}",
            "start_time_short": rf"self.start_time_short",
            "start_time_relative": self.start_time_relative,
            "start_time_long": self.start_time_long,
            "tickets_number": self.tickets_number,
            "tickets_emoji": rf"self.tickets_emoji",
            "role_ping": self.role_ping,
            "channel_score": self.channel_score,
            "channel_post": self.channel_score,
        }