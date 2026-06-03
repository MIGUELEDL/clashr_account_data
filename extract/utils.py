import logging
import re
from datetime import datetime, timezone

def formata_tag(tag: str) -> str:
    """
    Remove o # e coloca em uppercase.
    Exemplos:
        #2PQLY9  →  2PQLY9
        #2pqly9  →  2PQLY9
        2pqly9   →  2PQLY9
    """
    return re.sub(r"#", "", tag).upper().strip()

def get_data_atual() -> str:
    """
    Retorna a data atual no formato de partição do S3.
    Exemplo: 2025-01-15
    Sempre usa UTC para consistência independente do fuso horário da máquina.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def get_s3_path(endpoint: str, player_tag: str) -> str:
    """
    Monta o caminho completo do arquivo no S3.
    Exemplo:
        endpoint=battles, player_tag=2PQLY9
        → raw/battles/2PQLY9/2025-01-15/data.json
    """
    date_partition = get_data_atual()
    return f"raw/{endpoint}/{player_tag}/{date_partition}/data.json"

def setup_logging(name: str) -> logging.Logger:
    """
    Configura e retorna um logger padronizado para o projeto.
    Todos os logs seguem o mesmo formato para facilitar leitura no CloudWatch.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    return logging.getLogger(name)