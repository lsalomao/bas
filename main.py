from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import os
import shutil
from app.processor import BoletoProcessor
from app.config import Config

app = FastAPI()
config = Config()
processor = BoletoProcessor(config)

@app.post("/upload/")
async def upload_boleto(file: UploadFile = File(...)):
    filename = file.filename
    save_path = os.path.join(config.anexos_dir, filename)

    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    data = processor.reprocess_specific_file(save_path)
    if data:
        return data
    return JSONResponse(status_code=400, content={"error": "Falha ao extrair dados."})

@app.get("/processar-todos/")
def processar_todos():
    return processor.process_all_boletos()

@app.get("/reprocessar/")
def reprocessar(arquivo: str):
    path = os.path.join(config.anexos_dir, arquivo)
    result = processor.reprocess_specific_file(path)
    if result:
        return result
    return JSONResponse(status_code=404, content={"error": "Arquivo não encontrado."})

@app.get("/debug-texto/")
def debug_texto(arquivo: str):
    path = os.path.join(config.anexos_dir, arquivo)
    return {"texto": processor.debug_extract_text(path)}

@app.get("/")
def inicio():    
    return {"texto ": "API de processamento de boletos."}
