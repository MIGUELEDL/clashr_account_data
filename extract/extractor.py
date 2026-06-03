from extract.client import ClashClient
from extract.models import PlayerProfile, Battle, Card
from extract.utils import setup_logging, formata_tag

logger = setup_logging(__name__)

class ClashExtractor:
    """
    Sabe o que perguntar para a API do Clash Royale.
    Usa o ClashClient para fazer as requisições e converte
    os dados brutos da API para os modelos definidos em models.py
    """

    def __init__(self, client: ClashClient):
        self.client = client

    def get_player_profile(self, tag: str) -> PlayerProfile:
        """
        Busca o perfil completo de um player.

        Args:
            tag: tag do player com ou sem #. Ex: #2PQLY9 ou 2PQLY9

        Returns:
            PlayerProfile com os dados do player
        """
        tag = formata_tag(tag)
        logger.info(f"Buscando perfil do player {tag}")

        data = self.client.get(f"/players/%23{tag}")

        cards = [
            Card(
                id=card["id"],
                name=card["name"],
                level=card["level"],
                max_level=card["maxLevel"],
                rarity=card["rarity"],
                elixir_cost=card.get("elixirCost", 0),
                count=card.get("count", 0),
            )
            for card in data.get("cards", [])
        ]

        clan = data.get("clan")

        profile = PlayerProfile(
            tag=data["tag"].replace("#", ""),
            name=data["name"],
            level=data["expLevel"],
            trophies=data["trophies"],
            best_trophies=data["bestTrophies"],
            wins=data["wins"],
            losses=data["losses"],
            battle_count=data["battleCount"],
            cards=cards,
            clan_name=clan["name"] if clan else None,
            clan_tag=clan["tag"].replace("#", "") if clan else None,
        )

        logger.info(
            f"Perfil extraído: {profile.name} | "
            f"Troféus: {profile.trophies} | "
            f"Batalhas: {profile.battle_count}"
        )
        return profile

    def get_battle_log(self, tag: str) -> list[Battle]:
        """
        Busca o histórico de batalhas de um player.

        Args:
            tag: tag do player com ou sem #

        Returns:
            Lista de Battle com as últimas batalhas
        """
        tag = formata_tag(tag)
        logger.info(f"Buscando batalhas do player {tag}")

        data = self.client.get(f"/players/%23{tag}/battlelog")
        battles = []

        for item in data:
            try:
                player_team = item["team"][0]
                opponent_team = item["opponent"][0]

                player_deck = [
                    card["name"]
                    for card in player_team.get("cards", [])
                ]
                opponent_deck = [
                    card["name"]
                    for card in opponent_team.get("cards", [])
                ]

                # Determina o resultado da batalha comparando coroas
                # Logo, quem destruiu mais coroas na batalha foi o vencedor (win)
                crowns_player = player_team.get("crowns", 0)
                crowns_opponent = opponent_team.get("crowns", 0)

                if crowns_player > crowns_opponent:
                    result = "win"
                elif crowns_player < crowns_opponent:
                    result = "loss"
                else:
                    result = "draw"

                battle = Battle(
                    battle_time=item["battleTime"],
                    battle_type=item.get("type", "unknown"),
                    result=result,
                    player_tag=tag,
                    player_trophies=player_team.get("startingTrophies", 0),
                    player_deck=player_deck,
                    player_elixir_avg=player_team.get("elixirLeaked", 0.0),
                    crowns_player=crowns_player,
                    crowns_opponent=crowns_opponent,
                    opponent_tag=opponent_team.get("tag", "").replace("#", ""),
                    opponent_deck=opponent_deck,
                )
                battles.append(battle)

            except (KeyError, IndexError) as e:
                logger.warning(f"Batalha ignorada por dados incompletos: {e}")
                continue

        logger.info(f"{len(battles)} batalhas extraídas para {tag}")
        return battles