from dataclasses import dataclass, field
from typing import Optional

@dataclass
class Card:
    """
    Representa uma carta da coleção do player.
    """
    id: int
    name: str
    level: int
    max_level: int
    rarity: str
    elixir_cost: int
    count: int

@dataclass
class Battle:
    """
    Representa uma batalha do histórico do player.
    """
    battle_time: str
    battle_type: str
    result: str
    player_tag: str
    player_trophies: int
    player_deck: list[str]
    player_elixir_avg: float
    crowns_player: int
    crowns_opponent: int
    opponent_tag: str
    opponent_deck: list[str]

@dataclass
class PlayerProfile:
    """
    Representa o perfil completo de um player.
    """
    tag: str
    name: str
    level: int
    trophies: int
    best_trophies: int
    wins: int
    losses: int
    battle_count: int
    cards: list[Card] = field(default_factory=list)
    clan_name: Optional[str] = None
    clan_tag: Optional[str] = None