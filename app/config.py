import os

class Config:
    def __init__(self):
        self.anexos_dir = "anexos"
        self.output_file = "boleto_data.json"
        self.max_workers: int = 4

        # Cria diretórios se não existirem
        os.makedirs(self.anexos_dir, exist_ok=True)
