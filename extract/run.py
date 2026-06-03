import os
from dotenv import load_dotenv
from extract.client import ClashClient
from extract.extractor import ClashExtractor
from extract.loader import S3Loader
from extract.utils import setup_logging, formata_tag

load_dotenv()
logger = setup_logging("run")

def main():
    # Carrega variáveis do .env
    api_token = os.getenv("API_TOKEN")
    base_url = os.getenv("CLASH_API_BASE_URL")
    player_tag = os.getenv("PLAYER_TAG")
    bucket = os.getenv("S3_BUCKET_NAME")
    region = os.getenv("AWS_REGION")

    # Valida que todas as variáveis estão presentes
    required = {
        "API_TOKEN": api_token,
        "CLASH_API_BASE_URL": base_url,
        "PLAYER_TAG": player_tag,
        "S3_BUCKET_NAME": bucket,
        "AWS_REGION": region,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise EnvironmentError(
            f"Variáveis de ambiente faltando: {', '.join(missing)}"
        )

    logger.info(f"Iniciando extração para o player {formata_tag(player_tag)}")

    # Inicializa os componentes
    client = ClashClient(api_token=api_token, base_url=base_url)
    extractor = ClashExtractor(client=client)
    loader = S3Loader(bucket_name=bucket, region=region)

    # Extrai e salva o perfil
    profile = extractor.get_player_profile(player_tag)
    profile_path = loader.save_profile(profile)
    logger.info(f"Perfil salvo em: {profile_path}")

    # Extrai e salva as batalhas
    battles = extractor.get_battle_log(player_tag)
    battles_path = loader.save_battles(battles, player_tag)
    logger.info(f"Batalhas salvas em: {battles_path}")

    logger.info("Extração concluída com sucesso!")

if __name__ == "__main__":
    main()