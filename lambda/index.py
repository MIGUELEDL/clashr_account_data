import json
import os
import sys
from datetime import datetime
from typing import Dict, Any

# Add parent directory para Lambda conseguir importar extract/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')

# Importar scripts de autenticação, extração, loader e scripts de utilidade geral
from extract.client import ClashClient
from extract.extractor import ClashExtractor
from extract.loader import S3Loader
from extract.utils import setup_logging, formata_tag

logger = setup_logging(__name__)

def lambda_handler(event, context):
    """
    AWS Lambda handler - acionado diariamente por eventos do CloudWatch
    
    Fluxo:
      1. ClashClient: faz requisições à API (HTTP)
      2. ClashExtractor: orquestra client + models (lógica)
      3. S3Loader: salva em S3 (persistência)
    
    Args:
        event: CloudWatch Events payload
        context: Lambda context (request_id, timeout, memory, etc)
    
    Returns:
        dict com statusCode e body (JSON)
    """

    execution_id = context.request_id if context else 'test'
    timestamp = datetime.utcnow().isoformat()
    
    print("="*70)
    print(f"extract iniciado")
    print(f"Timestamp: {timestamp}")
    print(f"Execution ID: {execution_id}")
    print("="*70)
    
    try:
        # carregar variaveis de ambiente
        api_key = os.environ.get('CLASH_API_KEY')
        bucket = os.environ.get('S3_BUCKET_NAME')
        region = os.environ.get('AWS_REGION')
        player_tag = os.environ.get('PLAYER_TAG')
        
        if not api_key:
            raise ValueError("CLASH_API_KEY não está configurada")
        
        logger.info(f"Configuração carregada:")
        logger.info(f"Bucket: {bucket}")
        logger.info(f"Region: {region}")
        logger.info(f"Player Tag: {player_tag}")
        
        # ClashClient - faz requisições HTTP
        client = ClashClient(
            api_token=api_key,
            base_url='https://api.clashroyale.com/v1'
        )
        
        # ClashExtractor - orquestra client + models
        extractor = ClashExtractor(client)
        
        # caminho do S3
        loader = S3Loader(
            bucket_name=bucket,
            region=region
        )
        
        # carregando profile
        logger.info("Extraindo player profile...")
        profile = extractor.get_player_profile(player_tag)
        logger.info(f"Profile extraido: {profile.name}")
        
        # carregando battles
        logger.info("Extraindo battles...")
        battles = extractor.get_battle_log(player_tag)
        logger.info(f"{len(battles)} battles extraidas!")
    
        # Salvando no S3
        logger.info("Salvando...")
        
        profile_path = loader.save_profile(profile)
        logger.info(f"Profile salvo: {profile_path}")
        
        battles_path = loader.save_battles(battles, player_tag)
        logger.info(f"Battles salvo: {battles_path}")
        
        response_body = {
            'status': 'success',
            'timestamp': timestamp,
            'execution_id': execution_id,
            'data': {
                'player_tag': player_tag,
                'player_name': profile.name,
                'profile': {
                    'extracted': True,
                    'trophies': profile.trophies,
                    'level': profile.level,
                    's3_path': profile_path,
                },
                'battles': {
                    'extracted': True,
                    'count': len(battles),
                    's3_path': battles_path,
                },
            },
            'errors': None,
        }
        
        print("="*70)
        print(f"Extração concluida!")
        print(f"Profile: {profile.name} ({profile.trophies} trophies)")
        print(f"Battles: {len(battles)} extracted")
        print(f"S3: {profile_path}")
        print("="*70)
        
        return {
            'statusCode': 200,
            'body': json.dumps(response_body, indent=2, default=str)
        }
    
    except ValueError as e:
        print("="*70)
        print(f"Erro na configuração")
        print(f"{str(e)}")
        print("="*70)
        
        return {
            'statusCode': 400,
            'body': json.dumps({
                'status': 'error',
                'timestamp': timestamp,
                'execution_id': execution_id,
                'error': str(e),
                'error_type': 'ConfigurationError',
            }, indent=2)
        }
    
    except Exception as e:
        print("="*70)
        print(f"Falha na extração!")
        print(f"Error: {str(e)}")
        print(f"Type: {type(e).__name__}")
        print("="*70)
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'status': 'error',
                'timestamp': timestamp,
                'execution_id': execution_id,
                'error': str(e),
                'error_type': type(e).__name__,
            }, indent=2)
        }

# LOCAL TESTE (run with: python lambda/index.py)

if __name__ == '__main__':
    from unittest.mock import Mock
    
    print("Iniciando teste do lambda...\n")
    
    # Checando .envs
    api_key = os.getenv('CLASH_API_KEY')
    if not api_key:
        print("CLASH_API_KEY não foi setada!")
        print("importe sua CLASH_API_KEY='sua_key'")
        exit(1)
    
    # Mock context
    mock_context = Mock()
    mock_context.request_id = 'local-test-' + datetime.now().strftime('%Y%m%d-%H%M%S')
    
    # Call handler
    result = lambda_handler({}, mock_context)
    
    # Print result
    print("\nResponse:")
    print(result['body'])
    
    # Exit with status code
    exit(result['statusCode'] // 100 - 2)  # 200 → 0, 500 → 3