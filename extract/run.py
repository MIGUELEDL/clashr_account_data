import os
import sys
from datetime import datetime
from extract.client import ClashClient
from extract.extractor import ClashExtractor
from extract.loader import S3Loader
from extract.utils import setup_logging

logger = setup_logging(__name__)

def main():
    api_key = os.environ.get('CLASH_API_KEY')
    bucket = os.environ.get('S3_BUCKET_NAME')
    player_tag = os.environ.get('PLAYER_TAG', '').replace('#', '')
    region = os.environ.get('AWS_REGION', 'us-east-2')

    if not api_key:
        logger.error("CLASH_API_KEY não configurada")
        sys.exit(1)

    logger.info(f"Iniciando extração para o player {player_tag}")

    client = ClashClient(api_token=api_key, base_url='https://api.clashroyale.com/v1')
    extractor = ClashExtractor(client)
    loader = S3Loader(bucket_name=bucket, region=region)

    # Extrai e salva perfil
    profile = extractor.get_player_profile(player_tag)
    profile_path = loader.save_profile(profile)
    logger.info(f"Perfil salvo em: {profile_path}")

    # Extrai e salva batalhas
    battles = extractor.get_battle_log(player_tag)
    battles_path = loader.save_battles(battles, player_tag)
    logger.info(f"Batalhas salvas em: {battles_path}")

    logger.info("Extração concluída com sucesso!")

if __name__ == '__main__':
    main()