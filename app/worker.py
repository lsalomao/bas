import time
import os
from app.getemails import monitorar_emails
from app.core.settings import settings

def start_worker():
    intervalo = settings.EMAIL_CHECK_INTERVAL  # segundos

    print(f"[Worker] Iniciando com intervalo de {intervalo} segundos")
    while True:
        try:
            print("[Worker] Verificando novos e-mails...")
            monitorar_emails()
        except Exception as e:
            print(f"[Worker] Erro: {e}")
        time.sleep(intervalo)
