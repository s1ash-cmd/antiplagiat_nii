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
