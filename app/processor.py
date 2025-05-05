import os
import json
import pdfplumber
from app.models import BoletoData
from app.config import Config
import re
import logging
from typing import Dict, List, Optional, Set
from dataclasses import asdict
from concurrent.futures import ThreadPoolExecutor

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("boleto_processor")


class BoletoProcessor:

  # Compilar regex patterns uma vez só para melhor performance
    PATTERNS = {
        "codigo_barras": re.compile(r"(\d{5}\.\d{5}\s\d{5}\.\d{6}\s\d{5}\.\d{6}\s\d{1}\s\d{14})"),
        "vencimento": re.compile(r"(?:PAGAVEL EM QUALQUER BANCO ATE O VENCIMENTO|Valor Documento.*?\d{2}/\d{2}/\d{4}\s+\d{1,3}(?:\.\d{3})*,\d{2}\s+)(\d{2}/\d{2}/\d{4})"),
        "valor": re.compile(r"Valor do Documento\s*(\d{1,3}(?:\.\d{3})*,\d{2})"),
        "beneficiario": re.compile(r"Beneficiário\s+Agência / Código Beneficiário\s*([^\n]+)"),
        "pagador": re.compile(r"Pagador\s+[^\n]+\s*([^\n]+)"),
        "data_processamento": re.compile(r"Data Processamento\s*(\d{2}/\d{2}/\d{4})")
    }
    
    # Padrões alternativos
    ALT_PATTERNS = {
        "codigo_barras": re.compile(r"\d{3}-\d\s+(\d{5}\.\d{5}\s\d{5}\.\d{6}\s\d{5}\.\d{6}\s\d{1}\s\d{14})"),
        "vencimento": re.compile(r"Local de Pagamento\s+Vencimento\s+.*?\s+(\d{2}/\d{2}/\d{4})"),
        "valor": re.compile(r"Data VencimentoValor DocumentoNúmero da Proposta.*?\s*(\d{1,3}(?:\.\d{3})*,\d{2})"),
        "beneficiario": re.compile(r"Beneficiário:\s*([^\n]+)"),
        "pagador": re.compile(r"Pagador\s+CPF/CNPJ:.*?\s*([^\n]+)"),
        "data_processamento": re.compile(r"Data Documento\s*Número Documento\s*.*?\s*(\d{2}/\d{2}/\d{4})")
    }
    
    # Padrões adicionais (terceira chance de encontrar)
    EXTRA_PATTERNS = {
        "valor": re.compile(r"Valor Plano\s*(\d{1,3}(?:\.\d{3})*,\d{2})"),
        "data_processamento": re.compile(r"Aceite\s*Data Processamento\s*(\d{2}/\d{2}/\d{4})")
    }
    
    # Padrões específicos para boletos AMIL e outros planos de saúde
    HEALTH_PATTERNS = {
        "valor": [
            re.compile(r"Vencimento\s+Valor\s+(\d{1,3}(?:\.\d{3})*,\d{2})"),
            re.compile(r"Valor\s+R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})"),
            re.compile(r"Valor\s+a\s+pagar\s*R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})"),
            re.compile(r"Valor\s+do\s+Pagamento\s*R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})"),
            re.compile(r"VALOR\s+COBRADO\s*(\d{1,3}(?:\.\d{3})*,\d{2})"),
            # Padrão para extrair o valor a partir do código de barras (geralmente os últimos 10 dígitos)
            re.compile(r"\d{5}\.\d{5}\s\d{5}\.\d{6}\s\d{5}\.\d{6}\s\d{1}\s\d{4}(\d{10})"),
        ]
    }
    

    def __init__(self, config: Config):
        self.config = config
        print(f"Configuração: {self.config.__dict__}")
        self.boletos_extraidos = []

    def extract_value_from_barcode(self, codigo_barras):
        """
        Extrai valor do código de barras, quando presente nos últimos dígitos.
        Estratégia comum em boletos, onde os últimos 10 dígitos representam o valor
        multiplicado por 100.
        """
        if not codigo_barras or len(codigo_barras) < 10:
            return None

        # Tenta extrair os últimos 10 dígitos e converter para valor
        try:
            # Remove todos os pontos e espaços
            clean_code = codigo_barras.replace(".", "").replace(" ", "")

            # Os últimos 10 dígitos geralmente contêm o valor
            last_digits = clean_code[-10:]

            # Para boletos da AMIL, verificar se são dígitos significativos
            # Se começar com muitos zeros, pode ser o valor direto
            if last_digits.startswith("00001"):
                # Remover zeros à esquerda e dividir por 100
                value_str = last_digits.lstrip("0")
                if len(value_str) <= 2:  # Se ficou só centavos
                    value = float("0." + value_str.zfill(2))
                else:
                    # Insere a vírgula nas posições corretas (R$ x.xxx,xx)
                    reais = value_str[:-2]
                    centavos = value_str[-2:]
                    formatted_value = f"{reais},{centavos}"
                    logger.debug(
                        f"Valor formatado do código de barras AMIL: {formatted_value}"
                    )
                    return formatted_value

            # Procedimento padrão para outros boletos
            value = float(last_digits) / 100

            # Formata para o padrão brasileiro
            formatted_value = f"{value:.2f}".replace(".", ",")

            logger.debug(f"Valor extraído do código de barras: {formatted_value}")
            return formatted_value
        except Exception as e:
            logger.debug(
                f"Não foi possível extrair valor do código de barras: {str(e)}"
            )
            return None

    def extract_data_from_pdf(self, pdf_path: str) -> Optional[BoletoData]:
        """
        Extrai dados de um boleto em PDF.

        Args:
            pdf_path: Caminho do arquivo PDF

        Returns:
            Objeto BoletoData com os dados extraídos ou None se falhar
        """
        boleto = BoletoData(arquivo=pdf_path)

        try:
            with pdfplumber.open(pdf_path) as pdf:
                # Extrair todo o texto de todas as páginas
                all_text = ""
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    all_text += text + "\n"

                if not all_text.strip():
                    logger.warning(f"Nenhum texto extraído de {pdf_path}")
                    return None

                # Para depuração
                logger.debug(f"Texto extraído do PDF: {all_text[:500]}...")

                # Extrai dados usando padrões primários
                for field, pattern in self.PATTERNS.items():
                    if (
                        getattr(boleto, field) is None
                    ):  # Só busca se ainda não encontrou
                        match = pattern.search(all_text)
                        if match and match.group(1):
                            setattr(boleto, field, match.group(1).strip())
                            logger.debug(
                                f"Encontrado {field}: {match.group(1).strip()}"
                            )

                # Tenta padrões alternativos para campos não encontrados
                for field, pattern in self.ALT_PATTERNS.items():
                    if (
                        getattr(boleto, field) is None
                    ):  # Só busca se ainda não encontrou
                        match = pattern.search(all_text)
                        if match and match.group(1):
                            setattr(boleto, field, match.group(1).strip())
                            logger.debug(
                                f"Encontrado {field} (alt): {match.group(1).strip()}"
                            )

                # Tenta padrões extras para campos críticos
                for field, pattern in self.EXTRA_PATTERNS.items():
                    if (
                        getattr(boleto, field) is None
                    ):  # Só busca se ainda não encontrou
                        match = pattern.search(all_text)
                        if match and match.group(1):
                            setattr(boleto, field, match.group(1).strip())
                            logger.debug(
                                f"Encontrado {field} (extra): {match.group(1).strip()}"
                            )

                # Tenta padrões específicos para planos de saúde
                if (
                    boleto.valor is None
                    and hasattr(self, "HEALTH_PATTERNS")
                    and "valor" in self.HEALTH_PATTERNS
                ):
                    for pattern in self.HEALTH_PATTERNS["valor"]:
                        match = pattern.search(all_text)
                        if match and match.group(1):
                            boleto.valor = match.group(1).strip()
                            logger.debug(
                                f"Encontrado valor (health): {match.group(1).strip()}"
                            )
                            break

                # Tentar extrair o valor do código de barras - especialmente útil para boletos AMIL
                if boleto.codigo_barras:
                    extracted_value = self.extract_value_from_barcode(
                        boleto.codigo_barras
                    )
                    if extracted_value:
                        boleto.valor = extracted_value
                        logger.info(
                            f"Valor extraído do código de barras: {extracted_value}"
                        )

                # Tenta um método mais agressivo para encontrar valores - procurar por padrões de moeda
                if boleto.valor is None:
                    currency_patterns = [
                        re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})"),
                        re.compile(r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*R\$"),
                        re.compile(r"\(=\)\s*(\d{1,3}(?:\.\d{3})*,\d{2})"),
                        re.compile(
                            r"Total\s+a\s+pagar\s*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})"
                        ),
                    ]

                    for pattern in currency_patterns:
                        match = pattern.search(all_text)
                        if match and match.group(1):
                            boleto.valor = match.group(1).strip()
                            logger.debug(
                                f"Encontrado valor (currency): {match.group(1).strip()}"
                            )
                            break

            # Formata os dados extraídos
            boleto.format_data()

            # Verifica se foram extraídos dados suficientes
            if not boleto.is_valid():
                logger.warning(f"Dados insuficientes extraídos de {pdf_path}")
                return None

            return boleto

        except Exception as e:
            logger.error(f"Erro ao processar {pdf_path}: {str(e)}")
            return None

    def debug_extract_text(self, pdf_path: str) -> str:
        """
        Função de debug para extrair e retornar todo o texto de um PDF.
        Útil para analisar a estrutura do PDF e identificar novos padrões.
        """
        try:
            with pdfplumber.open(pdf_path) as pdf:
                all_text = ""
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    all_text += text + "\n"
                return all_text
        except Exception as e:
            logger.error(f"Erro ao extrair texto para debug de {pdf_path}: {str(e)}")
            return f"ERRO: {str(e)}"

    def load_processed_files(self) -> tuple[List[Dict], Set[str]]:
        """
        Carrega os boletos já processados do arquivo JSON.

        Returns:
            Tupla com a lista de boletos e conjunto de caminhos já processados
        """
        processed_data = []
        processed_files = set()
        
        if os.path.exists(self.config.output_file):
            try:
                with open(self.config.output_file, "r", encoding="utf-8") as f:
                    processed_data = json.load(f)
                    processed_files = {item["arquivo"] for item in processed_data}
                    logger.info(
                        f"Carregados {len(processed_data)} boletos já processados"
                    )
            except Exception as e:
                logger.error(f"Erro ao carregar arquivo JSON: {str(e)}")

        return processed_data, processed_files

    def save_data(self, data: List[Dict]) -> bool:
        """
        Salva os dados em um arquivo JSON.

        Args:
            data: Lista de dicionários com os dados dos boletos

        Returns:
            True se salvou com sucesso, False caso contrário
        """
        try:
            with open(self.config.output_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Dados salvos em '{self.config.output_file}'")
            return True
        except Exception as e:
            logger.error(f"Erro ao salvar dados: {str(e)}")
            return False

    def process_pdf(self, pdf_path: str, processed_files: Set[str]) -> Optional[Dict]:
        """
        Processa um único arquivo PDF se ainda não foi processado.

        Args:
            pdf_path: Caminho do arquivo PDF
            processed_files: Conjunto de arquivos já processados

        Returns:
            Dicionário com os dados do boleto ou None
        """
        if pdf_path in processed_files:
            logger.debug(f"Pulando: {pdf_path} (já processado)")
            return None

        logger.info(f"Processando: {os.path.basename(pdf_path)}")
        boleto = self.extract_data_from_pdf(pdf_path)

        if boleto:
            result = asdict(boleto)
            # Log dos dados extraídos
            logger.info(f"Dados extraídos do boleto: {os.path.basename(pdf_path)}")
            for key, value in result.items():
                if key != "arquivo":
                    logger.info(f"  - {key}: {value}")
            return result
        return None

    def process_all_boletos(self) -> List[Dict]:
        """
        Processa todos os PDFs na pasta de anexos, pulando boletos já processados.

        Returns:
            Lista de dicionários com os dados dos boletos processados
        """
        if not os.path.exists(self.config.anexos_dir):
            logger.error(f"Pasta '{self.config.anexos_dir}' não encontrada!")
            return []

        # Carrega dados já processados
        processed_data, processed_files = self.load_processed_files()

        # Lista todos os PDFs na pasta
        pdf_files = [
            os.path.join(self.config.anexos_dir, f)
            for f in os.listdir(self.config.anexos_dir)
            if f.lower().endswith(".pdf")
        ]

        if not pdf_files:
            logger.info("Nenhum arquivo PDF encontrado na pasta de anexos")
            return processed_data

        # Processa PDFs em paralelo
        new_data = []
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            results = executor.map(
                lambda pdf: self.process_pdf(pdf, processed_files), pdf_files
            )

            for result in results:
                if result:
                    new_data.append(result)

        if new_data:
            logger.info(f"Processados {len(new_data)} novos boletos")
            all_data = processed_data + new_data
            self.save_data(all_data)
            return all_data
        else:
            logger.info("Nenhum novo boleto processado")
            return processed_data

    def reprocess_specific_file(self, specific_pdf: str) -> Optional[Dict]:
        """
        Reprocessa um arquivo específico, mesmo que já tenha sido processado antes.
        Útil para debug ou após atualização de padrões de extração.

        Args:
            specific_pdf: Caminho completo para o arquivo a ser reprocessado

        Returns:
            Dicionário com os dados do boleto ou None
        """
        if not os.path.exists(specific_pdf):
            logger.error(f"Arquivo '{specific_pdf}' não encontrado!")
            return None

        logger.info(f"Reprocessando: {os.path.basename(specific_pdf)}")
        boleto = self.extract_data_from_pdf(specific_pdf)

        if boleto:
            result = asdict(boleto)
            logger.info(f"Dados extraídos do boleto: {os.path.basename(specific_pdf)}")
            for key, value in result.items():
                if key != "arquivo":
                    logger.info(f"  - {key}: {value}")
            return result
        return None
