import time
import requests
from extract.utils import setup_logging

logger = setup_logging(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 1  # segundos — dobra a cada tentativa (backoff exponencial)

class ClashClient:
    """
    Client HTTP para a API do Clash Royale.
    Responsável apenas por fazer requisições de forma robusta.
    """

    def __init__(self, api_token: str, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
        })
        logger.info("ClashClient inicializado")

    def get(self, endpoint: str) -> dict:
        """
        Faz uma requisição GET para a API com retry automático.

        Args:
            endpoint: caminho do endpoint. Ex: /players/%232PQLY9

        Returns:
            dict com o JSON de resposta da API

        Raises:
            ValueError: se o player não for encontrado (404)
            RuntimeError: se a API falhar após todas as tentativas
        """
        url = f"{self.base_url}{endpoint}"
        delay = RETRY_DELAY

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(f"Tentativa {attempt}/{MAX_RETRIES} — GET {url}")
                response = self.session.get(url, timeout=10)

                # Player não existe — não adianta tentar de novo
                if response.status_code == 404:
                    raise ValueError(
                        f"Player não encontrado: {endpoint}"
                    )

                # Rate limit — espera e tenta de novo
                if response.status_code == 429:
                    wait = int(response.headers.get("Retry-After", delay))
                    logger.warning(f"Rate limit atingido. Aguardando {wait}s...")
                    time.sleep(wait)
                    continue

                # Qualquer outro erro HTTP
                response.raise_for_status()

                logger.info(f"Resposta OK — status {response.status_code}")
                return response.json()

            except ValueError:
                raise  # 404 — não tenta de novo

            except Exception as e:
                logger.error(f"Erro na tentativa {attempt}: {e}")
                if attempt == MAX_RETRIES:
                    raise RuntimeError(
                        f"API falhou após {MAX_RETRIES} tentativas: {e}"
                    )
                logger.info(f"Aguardando {delay}s antes da próxima tentativa...")
                time.sleep(delay)
                delay *= 2  # backoff exponencial: 1s → 2s → 4ss