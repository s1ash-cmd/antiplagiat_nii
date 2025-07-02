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

from libs.schemas import SimpleCheckResult, Service, Source, Author, LoanBlock
from libs.logger import logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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

        wsdl_url = f'https://{self.apicorp_address}/apiCorp/{self.company_name}?singleWsdl'

        session = requests.Session()
        session.verify = False
        session.auth = (self.login, self.password)

        transport = Transport(session=session)
        self.client = Client(wsdl=wsdl_url, transport=transport)

        self.factory = self.client.type_factory('ns0')
        print("SOAP клиент создан")

    def _get_doc_data(self, filename: str, external_user_id: str):
        return self.factory.DocData(
        Data=base64.b64encode(open(filename, "rb").read()).decode(),
        FileName = os.path.splitext(filename)[0],
        FileType = os.path.splitext(filename)[1],
        ExternalUserID = external_user_id
    )

    def add_to_index(self, filename: str, author_surname='',
                     author_other_names='',
                     external_user_id='ivanov', custom_id='original'
                     ) -> SimpleCheckResult:
        logger.info("SimpleCheck filename=" + filename)

        data = self._get_doc_data(filename, external_user_id=external_user_id)

        personIds = self.factory.PersonIDs(CustomID=custom_id)
        docatr = self.factory.DocAttributes()
        arr = self.factory.ArrayOfAuthorName()
        author = self.factory.AuthorName(
            OtherNames = author_other_names,
            Surname = author_surname,
            PersonIDs = personIds
            )
        arr.AuthorName.append(author)
        docatr.DocumentDescription = {
            'Authors': arr
            }
        # Загрузка файла
        try:
            uploadResult = self.client.service.UploadDocument(data, docatr)

        except Exception:
            raise

        # Идентификатор документа. Если загружается не архив, то список загруженных документов будет состоять из одного элемента.
        try:
            id = uploadResult.Uploaded[0].Id

        except AttributeError:
            id = uploadResult[0].Id

        print(id)
        self.client.service.CheckDocument(id)

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
                                   author=Author(surname="", othernames="", custom_id=""),
                                   loan_blocks=[])

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

        options = self.factory.ReportViewOptions(
            FullReport = True,
            NeedText = True,
            NeedStats = True,
            NeedAttributes = True
            )
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

        return result.model_dump()


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

        while True:
            num = input("Введите пункт меню: ")
            try:
                num = int(num)
                break
            except ValueError:
                print("Введите номер пункта из меню!")

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
            print("Выход...")
            break

        else:
            print("Неверный запрос. Введите номер пункта из меню.")
