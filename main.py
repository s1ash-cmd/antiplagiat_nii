import os
import suds
import time
import base64
import urllib3
import io
import base64
import sys
import datetime
from suds.client import Client
import requests


from libs.schemas import SimpleCheckResult, Service, Source, Author, LoanBlock
from libs.logger import logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


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
                 apicorp_address="api.antiplagiat.ru:4959",
                 antiplagiat_uri="https://testapi.antiplagiat.ru"):

        self.antiplagiat_uri = antiplagiat_uri
        self.login = "testapi@antiplagiat.ru"
        self.password = "testapi"
        self.company_name = company_name
        self.apicorp_address = apicorp_address

        self.client = Client(f'https://{self.apicorp_address}/apiCorp/{self.company_name}?singleWsdl',
                                         username=self.login,
                                         password=self.password)
        print("SOAP клиент создан")

    def _get_doc_data(self, filename: str, external_user_id: str):
        data = self.client.factory.create("DocData")
        data.Data = base64.b64encode(open(filename, "rb").read()).decode()
        data.FileName = os.path.splitext(filename)[0]
        data.FileType = os.path.splitext(filename)[1]
        data.ExternalUserID = external_user_id
        return data

    def add_to_index(self, filename: str, author_surname='',
                     author_other_names='',
                     external_user_id='ivanov', custom_id='original'
                     ) -> SimpleCheckResult:
        logger.info("SimpleCheck filename=" + filename)

        data = self._get_doc_data(filename, external_user_id=external_user_id)

        docatr = self.client.factory.create("DocAttributes")
        personIds = self.client.factory.create("PersonIDs")
        personIds.CustomID = custom_id

        arr = self.client.factory.create("ArrayOfAuthorName")

        author = self.client.factory.create("AuthorName")
        author.OtherNames = author_other_names
        author.Surname = author_surname
        author.PersonIDs = personIds

        arr.AuthorName.append(author)

        docatr.DocumentDescription.Authors = arr
        # Загрузка файла
        try:
            uploadResult = self.client.service.UploadDocument(data, docatr)

        except Exception:
            raise

        # Идентификатор документа. Если загружается не архив, то список загруженных документов будет состоять из одного элемента.
        id = uploadResult.Uploaded[0].Id
        return id

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


    while True:

        print("\n$____________________Меню____________________$")
        print("1. Загрузить и индексировать документ;")
        print("2. Проверить на оригинальность и получить отчет;")
        print("0. Выход.")

        num = int(input("Введите пункт меню: "))

        if num == 1:
            filename = input("Введите название файла для индексации: ")
            id_index = AntiplagiatClient.add_to_index(client, filename)
            print("Идентификатор добавленного в индекс документа: " + str(id_index))

        elif num == 2:
            # filename =
            #
            # print("Отчет: " + str(id_index))
            print("Отчет:")

        elif num == 0:
            print("Выход.")

        else:
            print("Неверный запрос. Введите номер пункта из меню.")

    print("\n$______________________Меню______________________$")
    print("1. Загрузить и индексировать документ")
    print("2. Проверить на оригинальность и получить отчет")
    print("0. Выход")

