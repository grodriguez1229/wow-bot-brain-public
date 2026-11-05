from pydantic import BaseModel
from typing import Optional


class RecentLine(BaseModel):
    speaker: str
    text: str


class ChatRequest(BaseModel):
    bot_name: str
    player_name: str
    message: str
    channel: Optional[str] = "SAY"
    location: Optional[str] = None
    bot_in_group: Optional[bool] = False
    bot_guild: Optional[str] = None
    nearby_bots: Optional[list[str]] = None
    recent_lines: Optional[list[RecentLine]] = None


class TickRequest(BaseModel):
    bot_name: str
    location: Optional[str] = None
    nearby_players: Optional[list[str]] = None
    nearby_bots: Optional[list[str]] = None
    bot_in_group: Optional[bool] = False
    bot_guild: Optional[str] = None
    recent_lines: Optional[list[RecentLine]] = None
    subzone: Optional[str] = None
    activity: Optional[str] = None
    target: Optional[str] = None


class ActionItem(BaseModel):
    type: str  # invite, emote, trade, follow
    target: Optional[str] = None


class BotResponse(BaseModel):
    message: str
    channel: str
    emote: Optional[str] = None
    actions: Optional[list[ActionItem]] = None
    whisper_to: Optional[str] = None  # C++ honours this on any response


class EventRequest(BaseModel):
    type: str
    player: str
    level: Optional[int] = None
    faction: Optional[str] = None
    zone: Optional[str] = None
    instance: Optional[str] = None
    group: list[str] = []
    boss: Optional[str] = None
    who: Optional[str] = None


class WhisperOut(BaseModel):
    bot_name: str
    whisper_to: str
    message: str
    channel: str = "WHISPER"
    actions: list[ActionItem] = []
    delay_s: int


class EventResponse(BaseModel):
    whispers: list[WhisperOut] = []


class ReflectTurn(BaseModel):
    idx: int = 0
    speaker: str
    channel: str = "SAY"
    text: str
    actions: list = []

class ReflectScene(BaseModel):
    scene_id: str
    location: str = ""
    channel: str = "SAY"
    participants: list[str] = []
    turns: list[ReflectTurn] = []

class ReflectRequest(BaseModel):
    scene: ReflectScene
    bots: Optional[list[str]] = None


class HeardHearer(BaseModel):
    bot_name: str
    distance: float = 0.0
    same_party: bool = False
    same_guild: bool = False


class HeardRequest(BaseModel):
    speaker: str
    channel: str = "SAY"
    message: str
    location: Optional[str] = None
    hearers: list[HeardHearer] = []


class HeardReply(BotResponse):
    bot_name: str


class HeardResponse(BaseModel):
    responses: list[HeardReply]
