import imaplib
import email
from email.header import decode_header
import os
import time
from datetime import datetime
from app.core.settings import settings

def conectar_imap():
    mail = imaplib.IMAP4_SSL(settings.SERVER_IMAP)
    mail.login(settings.EMAIL, settings.SENHA)
    mail.select("INBOX")
    return mail

def processar_email(mensagem):
    assunto, encoding = decode_header(mensagem["Subject"])[0]
    if isinstance(assunto, bytes):
        assunto = assunto.decode(encoding or "utf-8")
    remetente, encoding = decode_header(mensagem.get("From"))[0]
    if isinstance(remetente, bytes):
        remetente = remetente.decode(encoding or "utf-8")

    # print(f"\nE-mail filtrado (Boleto): {remetente}")
    # print(f"Assunto: {assunto}")

    # Processar corpo e anexos (mesma lógica do código anterior)
    if mensagem.is_multipart():
        for part in mensagem.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            
            #if content_type in ["text/plain", "text/html"]:
                #corpo = part.get_payload(decode=True).decode()
                #print(f"\nCorpo do e-mail:\n{corpo[:500]}...")  # Exibe parte do texto
            
            if "attachment" in content_disposition:
                nome_arquivo = part.get_filename()
                if nome_arquivo:
                    caminho = os.path.join(settings.PASTA_ANEXOS, nome_arquivo)
                    with open(caminho, "wb") as f:
                        f.write(part.get_payload(decode=True))
                    print(f"Anexo salvo: {caminho}")

def monitorar_emails():
    # Criar pasta para anexos
    if not os.path.exists(settings.PASTA_ANEXOS):
        os.makedirs(settings.PASTA_ANEXOS)

    while True:
        print(f"\nVerificando e-mails com assunto 'Boleto' em: {datetime.now().strftime('%H:%M:%S')}")
        mail = conectar_imap()
        
        # Buscar e-mails NÃO LIDOS com assunto "Boleto" (case-insensitive)
        status, mensagens = mail.search(None, '(UNSEEN SUBJECT "Boleto")')
        
        if status == "OK":
            ids = mensagens[0].split()
            for id_email in ids:
                status, dados = mail.fetch(id_email, "(RFC822)")
                if status == "OK":
                    mensagem = email.message_from_bytes(dados[0][1])
                    processar_email(mensagem)
                    # Marcar como lido (opcional)
                    mail.store(id_email, "+FLAGS", "\\Seen")
        
        mail.close()
        mail.logout()
        sleep_time = settings.EMAIL_CHECK_INTERVAL
        print(f"Esperando {sleep_time} minutos para verificar novamente...")
        time.sleep(sleep_time)  # Espera por XX minutos