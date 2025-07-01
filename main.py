import os
import suds
import time
import base64
import urllib3
import io
import base64
import sys
import datetime
from zeep import Client
from zeep.transports import Transport
import requests
from typing import List, Optional
from pydantic import BaseModel
import logging

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class CustomFormatter(logging.Formatter):
    green = "\033[32m"
    yellow = "\033[33m"
    red = "\033[31m"
    bold_red = "\033[38m"
    reset = "\033[31m"
    format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"
    datefmt = '%Y-%m-%d %H:%M:%S'

    FORMATS = {
        logging.DEBUG: yellow + format + reset,
        logging.INFO: green + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt='%Y-%m-%d %H:%M:%S')
        return formatter.format(record)


logger = logging.getLogger("Antiplagiat")
logger.setLevel(level=logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(CustomFormatter())
logger.addHandler(ch)


class Source(BaseModel):
    hash: str
    score_by_report: str
    score_by_source: str
    name: Optional[str]
    author: Optional[str]
    url: Optional[str]

class Service(BaseModel):
    service_name: str
    originality: str
    plagiarism: str
    source: Optional[List]

class Author(BaseModel):
    surname: Optional[str]
    othernames: Optional[str]
    custom_id: Optional[str]

class LoanBlock(BaseModel):
    text: str
    offset: int
    length: int

class SimpleCheckResult(BaseModel):
    filename: str
    plagiarism: str
    services: List[Service]
    author: Optional[Author]
    loan_blocks: Optional[List[LoanBlock]]


class AntiplagiatClient:
    def __init__(self, login,
                 password,
                 company_name,
                 apicorp_address="api.antiplagiat.ru:4959"):

        self.login = login
        self.password = password
        self.company_name = company_name
        self.apicorp_address = apicorp_address

        wsdl_url = f'https://{self.apicorp_address}/apiCorp/{self.company_name}?wsdl'

        session = requests.Session()
        session.verify = False
        session.auth = (self.login, self.password)

        transport = Transport(session=session)
        self.client = Client(wsdl=wsdl_url, transport=transport)
        print("SOAP клиент создан")


    def get_doc_data(self, filename: str, external_user_id: str):
        data = {
            "Data": base64.b64encode(open(filename, "rb").read()).decode(),
            "FileName": os.path.splitext(filename)[0],
            "FileType": os.path.splitext(filename)[1],
            "ExternalUserID": external_user_id
        }
        return data




if __name__ == "__main__":
    client = AntiplagiatClient(
        login="testapi@antiplagiat.ru",
        password="testapi",
        company_name="testapi"
    )

    print("\n$______________________Меню______________________$")
    print("1. Загрузить и индексировать документ")
    print("2. Проверить на оригинальность и получить отчет")
    print("0. Выход")