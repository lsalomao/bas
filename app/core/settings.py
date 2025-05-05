import os
from dotenv import load_dotenv
from pathlib import Path

# Carrega o .env que está na pasta app
env_path = Path(__file__).parent / ".env"
print(f"Carregando variáveis de ambiente do arquivo: {env_path}")
load_dotenv(dotenv_path=env_path)

class Settings:
    # Configurações de ambiente
    PRODUCTION = os.environ.get('PRODUCTION', 'False') == 'True'

    # Configurações
    EMAIL = os.environ.get('LOGIN_APP_EMAIL')
    SENHA = os.environ.get('PASS_APP_EMAIL')
    SERVER_IMAP = os.environ.get('SERVER_IMAP')
    EMAIL_CHECK_INTERVAL = int(os.environ.get('EMAIL_CHECK_INTERVAL', 60))  # segundos
    PASTA_ANEXOS = "anexos"

settings = Settings()