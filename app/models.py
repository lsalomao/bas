from dataclasses import dataclass
from typing import Optional
from datetime import datetime
import re

@dataclass
class BoletoData:
    """Classe para armazenar os dados extraídos de um boleto."""
    arquivo: str
    codigo_barras: Optional[str] = None
    vencimento: Optional[str] = None
    valor: Optional[str] = None
    beneficiario: Optional[str] = None
    pagador: Optional[str] = None
    data_processamento: Optional[str] = None

    def is_valid(self) -> bool:
        """Verifica se os dados mínimos do boleto foram extraídos."""
        return bool(self.codigo_barras or self.vencimento)  # Pelo menos um dos dois deve existir
    
    def format_data(self) -> None:
        """Formata os dados extraídos."""
        if self.valor and isinstance(self.valor, str):
            # Converte o valor para float
            self.valor = self.valor.replace(".", "").replace(",", ".")
        
        if self.beneficiario:
            self.beneficiario = self.beneficiario.upper().strip()
        
        if self.pagador:
            # Remove o valor que aparece junto com o nome do pagador
            self.pagador = re.sub(r'\s+\d{1,3}(?:\.\d{3})*,\d{2}$', '', self.pagador).upper().strip()
        
        if self.codigo_barras:
            self.codigo_barras = self.codigo_barras.replace(" ", "")
        
        # Converte datas para formato ISO
        if self.vencimento:
            try:
                date_obj = datetime.strptime(self.vencimento, "%d/%m/%Y")
                self.vencimento = date_obj.strftime("%Y-%m-%d")
            except ValueError:
                pass
        
        if self.data_processamento:
            try:
                date_obj = datetime.strptime(self.data_processamento, "%d/%m/%Y")
                self.data_processamento = date_obj.strftime("%Y-%m-%d")
            except ValueError:
                pass
