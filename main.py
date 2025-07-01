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
    print("1. Загрузить и индексировать")
    print("2. Проверить на оригинальность")
    print("0. Выход")