import json
import boto3
from datetime import datetime, timezone
from dataclasses import asdict
from extract.models import PlayerProfile, Battle
from extract.utils import setup_logging, get_s3_path, formata_tag

logger = setup_logging(__name__)

class S3Loader:
    """
    Responsável por salvar os dados extraídos no S3 (Bronze Layer).
    É a única parte do projeto que escreve na Bronze Layer.
    """
    
    def __init__(self, bucket_name: str, region: str):
        self.bucket = bucket_name
        self.s3 = boto3.client("s3", region_name=region)
        logger.info(f"S3Loader inicializado — bucket: {bucket_name}")

    def _upload(self, data: dict | list, s3_path: str) -> None:
        """
        Faz o upload de um objeto JSON para o S3.
        Método interno — não chamado diretamente de fora da classe.
        """
        body = json.dumps(data, ensure_ascii=False, indent=2)

        self.s3.put_object(
            Bucket=self.bucket,
            Key=s3_path,
            Body=body.encode("utf-8"),
            ContentType="application/json",
            Metadata={
                "ingested_at": datetime.now(timezone.utc).isoformat(),
                "source": "clashroyale-api",
                "pipeline_version": "1.0",
            },
        )
        logger.info(f"Upload concluído: s3://{self.bucket}/{s3_path}")

    def save_profile(self, profile: PlayerProfile) -> str:
        """
        Salva o perfil do player na Bronze Layer.

        Args:
            profile: PlayerProfile extraído da API

        Returns:
            Caminho completo do arquivo no S3
        """
        tag = formata_tag(profile.tag)
        s3_path = get_s3_path("profile", tag)

        logger.info(f"Salvando perfil de {tag} em {s3_path}")
        self._upload(asdict(profile), s3_path)

        return s3_path

    def save_battles(self, battles: list[Battle], player_tag: str) -> str:
        """
        Salva o histórico de batalhas do player na Bronze Layer.

        Args:
            battles: lista de Battle extraída da API
            player_tag: tag do player

        Returns:
            Caminho completo do arquivo no S3
        """
        tag = formata_tag(player_tag)
        s3_path = get_s3_path("battles", tag)

        logger.info(f"Salvando {len(battles)} batalhas de {tag} em {s3_path}")
        self._upload([asdict(b) for b in battles], s3_path)

        return s3_path