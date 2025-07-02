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

    def simple_check(self, filename: str, author_surname='',
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

        try:
            # Отправить на проверку с использованием всех подключеных компании модулей поиска
            self.client.service.CheckDocument(id)
        # Отправить на проверку с использованием только собственного модуля поиска и модуля поиска "wikipedia". Для получения списка модулей поиска см. пример get_tariff_info()
        # client.service.CheckDocument(id, ["wikipedia", COMPANY_NAME])
        except suds.WebFault:
            raise

        # Получить текущий статус последней проверки
        status = self.client.service.GetCheckStatus(id)

        # Цикл ожидания окончания проверки
        while status.Status == "InProgress":
            time.sleep(status.EstimatedWaitTime * 0.1)
            status = self.client.service.GetCheckStatus(id)

        # Проверка закончилась не удачно.
        if status.Status == "Failed":
            logger.error(f"An error occurred while validating the document {filename}: {status.FailDetails}")

        # Получить краткий отчет
        report = self.client.service.GetReportView(id)

        logger.info(f"Report Summary: {report.Summary.Score:.2f}%")
        result = SimpleCheckResult(filename=os.path.basename(filename),
                                   plagiarism=f'{report.Summary.Score:.2f}%',
                                   services=[],
                                   author=Author())

        for checkService in report.CheckServiceResults:
            # Информация по каждому поисковому модулю

            service = Service(service_name=checkService.CheckServiceName,
                              originality=f'{checkService.ScoreByReport.Legal:.2f}%',
                              plagiarism=f'{checkService.ScoreByReport.Plagiarism:.2f}%',
                              source=[])

            logger.info(f"Check service: {checkService.CheckServiceName}, "
                        f"Score.White={checkService.ScoreByReport.Legal:.2f}% "
                        f"Score.Black={checkService.ScoreByReport.Plagiarism:.2f}%")
            if not hasattr(checkService, "Sources"):
                result.services.append(service)
                continue
            for source in checkService.Sources:
                _source = Source(hash=source.SrcHash,
                                 score_by_report=f'{source.ScoreByReport:.2f}%',
                                 score_by_source=f'{source.ScoreBySource:.2f}%',
                                 name=source.Name,
                                 author=source.Author,
                                 url=source.Url)

                service.source.append(_source)
                # Информация по каждому найденному источнику
                logger.info(
                    f'\t{source.SrcHash}: Score={source.ScoreByReport:.2f}%({source.ScoreBySource:.2f}%), '
                    f'Name="{source.Name}" Author="{source.Author}"'
                    f' Url="{source.Url}"')

                # Получить полный отчет
            result.services.append(service)

        options = self.client.factory.create("ReportViewOptions")
        options.FullReport = True
        options.NeedText = True
        options.NeedStats = True
        options.NeedAttributes = True
        fullreport = self.client.service.GetReportView(id, options)

        logger.info(f"Author Surname={fullreport.Attributes.DocumentDescription.Authors.AuthorName[0].Surname} "
                    f"OtherNames={fullreport.Attributes.DocumentDescription.Authors.AuthorName[0].OtherNames} "
                    f"CustomID={fullreport.Attributes.DocumentDescription.Authors.AuthorName[0].PersonIDs.CustomID}")

        result.author.surname = fullreport.Attributes.DocumentDescription.Authors.AuthorName[0].Surname
        result.author.othernames = fullreport.Attributes.DocumentDescription.Authors.AuthorName[0].OtherNames
        result.author.custom_id = fullreport.Attributes.DocumentDescription.Authors.AuthorName[0].PersonIDs.CustomID

        loan_blocks = []
        if fullreport.Details.CiteBlocks:
            for block in fullreport.Details.CiteBlocks:
                loan_block = LoanBlock(text=fullreport.Details.Text[block.Offset:block.Offset + block.Length],
                                       offset=block.Offset,
                                       length=block.Length)
                loan_blocks.append(loan_block)
        result.loan_blocks = loan_blocks

        return result.dict()




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