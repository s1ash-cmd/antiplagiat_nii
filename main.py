# import os
# import suds
# import time
# import base64
# import urllib3
# import io
# import base64
# import sys
# import datetime
# from suds.client import Client
# import requests
# import ssl
#
# from libs.schemas import SimpleCheckResult, Service, Source, Author, LoanBlock
# from libs.logger import logger
#
# ssl._create_default_https_context = ssl._create_unverified_context
# urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
#
# class AntiplagiatClient:
#     def __init__(self, login,
#                  password,
#                  company_name,
#                  apicorp_address="api.antiplagiat.ru:4959",
#                  antiplagiat_uri="https://testapi.antiplagiat.ru"):
#
#         self.antiplagiat_uri = antiplagiat_uri
#         self.login = "testapi@antiplagiat.ru"
#         self.password = "testapi"
#         self.company_name = company_name
#         self.apicorp_address = apicorp_address
#
#         self.client = Client(f'https://{self.apicorp_address}/apiCorp/{self.company_name}?singleWsdl',
#                              username=self.login,
#                              password=self.password)
#         print("SOAP клиент создан")
#
#     def _get_doc_data(self, filename: str, external_user_id: str):
#         data = self.client.factory.create("DocData")
#         data.Data = base64.b64encode(open(filename, "rb").read()).decode()
#         data.FileName = os.path.splitext(filename)[0]
#         data.FileType = os.path.splitext(filename)[1]
#         data.ExternalUserID = external_user_id
#         return data
#
#     def add_to_index(self, filename: str, author_surname='',
#                      author_other_names='',
#                      external_user_id='ivanov', custom_id='original'
#                      ) -> SimpleCheckResult:
#         logger.info("SimpleCheck filename=" + filename)
#
#         data = self._get_doc_data(filename, external_user_id=external_user_id)
#
#         docatr = self.client.factory.create("DocAttributes")
#         personIds = self.client.factory.create("PersonIDs")
#         personIds.CustomID = custom_id
#
#         arr = self.client.factory.create("ArrayOfAuthorName")
#
#         author = self.client.factory.create("AuthorName")
#         author.OtherNames = author_other_names
#         author.Surname = author_surname
#         author.PersonIDs = personIds
#
#         arr.AuthorName.append(author)
#
#         docatr.DocumentDescription.Authors = arr
#         # Загрузка файла
#         try:
#             uploadResult = self.client.service.UploadDocument(data, docatr)
#
#         except Exception:
#             raise
#
#         # Идентификатор документа. Если загружается не архив, то список загруженных документов будет состоять из одного элемента.
#         id = uploadResult.Uploaded[0].Id
#         return id
#
#     def check_document(self, id: str) -> dict:
#         if not id:
#             raise ValueError("Document ID должен быть передан для проверки")
#
#         # Создаём объект DocumentId
#         doc_id = self.client.factory.create("DocumentId")
#         doc_id.Id = int(id)  # Приводим к int, если нужно
#
#         # Запускаем проверку документа, передавая объект DocumentId
#         self.client.service.CheckDocument(doc_id)
#
#         # Аналогично для последующих вызовов:
#         status = self.client.service.GetCheckStatus(doc_id)
#         while status.Status == "InProgress":
#             time.sleep(status.EstimatedWaitTime * 0.1)
#             status = self.client.service.GetCheckStatus(doc_id)
#
#         if status.Status == "Failed":
#             raise Exception(f"Ошибка проверки документа с ID {id}: {status.FailDetails}")
#
#         report = self.client.service.GetReportView(doc_id)
#
#
#     # Формируем результат
#         result = SimpleCheckResult(
#             filename='',
#             plagiarism=f'{report.Summary.Score:.2f}%',
#             services=[],
#             author=Author()
#         )
#
#         for checkService in report.CheckServiceResults:
#             service = Service(
#                 service_name=checkService.CheckServiceName,
#                 originality=f'{checkService.ScoreByReport.Legal:.2f}%',
#                 plagiarism=f'{checkService.ScoreByReport.Plagiarism:.2f}%',
#                 source=[]
#             )
#             if hasattr(checkService, "Sources"):
#                 for source in checkService.Sources:
#                     _source = Source(
#                         hash=source.SrcHash,
#                         score_by_report=f'{source.ScoreByReport:.2f}%',
#                         score_by_source=f'{source.ScoreBySource:.2f}%',
#                         name=source.Name,
#                         author=source.Author,
#                         url=source.Url
#                     )
#                     service.source.append(_source)
#             result.services.append(service)
#
#         # Получаем полные атрибуты для автора, если есть
#         options = self.client.factory.create("ReportViewOptions")
#         options.FullReport = True
#         options.NeedAttributes = True
#         fullreport = self.client.service.GetReportView(id, options)
#
#         if fullreport.Attributes and fullreport.Attributes.DocumentDescription.Authors.AuthorName:
#             author_info = fullreport.Attributes.DocumentDescription.Authors.AuthorName[0]
#             result.author.surname = author_info.Surname
#             result.author.othernames = author_info.OtherNames
#             result.author.custom_id = author_info.PersonIDs.CustomID
#
#         # Получаем цитируемые блоки, если есть
#         loan_blocks = []
#         if hasattr(fullreport.Details, "CiteBlocks") and fullreport.Details.CiteBlocks:
#             for block in fullreport.Details.CiteBlocks:
#                 loan_block = LoanBlock(
#                     text=fullreport.Details.Text[block.Offset:block.Offset + block.Length],
#                     offset=block.Offset,
#                     length=block.Length
#                 )
#                 loan_blocks.append(loan_block)
#         result.loan_blocks = loan_blocks
#
#         return result.dict()
#
#
#     def _get_report_name(self, id, reportOptions):
#         author = u''
#
#         if reportOptions is not None:
#             if reportOptions.Author:
#                 author = '_' + reportOptions.Author
#
#         curDate = datetime.datetime.today().strftime('%Y%m%d')
#         return f'Certificate_{id.Id}_{curDate}_{author}.pdf'
#
#     def get_verification_report_pdf(self, filename: str,
#                                     author: str,
#                                     department: str,
#                                     type: str,
#                                     verifier: str,
#                                     work: str,
#                                     path: str = None,
#                                     external_user_id: str = 'ivanov'
#                                     ):
#
#         logger.info("Get report pdf:" + filename)
#
#         data = self._get_doc_data(filename, external_user_id=external_user_id)
#
#         uploadResult = self.client.service.UploadDocument(data)
#
#         id = uploadResult.Uploaded[0].Id
#
#         self.client.service.CheckDocument(id)
#
#         status = self.client.service.GetCheckStatus(id)
#
#         while status.Status == "InProgress":
#             time.sleep(status.EstimatedWaitTime)
#             status = self.client.service.GetCheckStatus(id)
#
#         if status.Status == "Failed":
#             logger.error(f"An error occurred while validating the document {filename}: {status.FailDetails}")
#             return
#
#         try:
#
#             reportOptions = self.client.factory.create("VerificationReportOptions")
#             reportOptions.Author = author  # ФИО автора работы
#             reportOptions.Department = department  # Факультет (структурное подразделение)
#             reportOptions.ShortReport = True  # Требуется ли ссылка на краткий отчёт? (qr код)
#             reportOptions.Type = type  # Тип работы
#             reportOptions.Verifier = verifier  # ФИО проверяющего
#             reportOptions.Work = work  # Название работы
#
#             reportWithFields = self.client.service.GetVerificationReport(id, reportOptions)
#
#             decoded = base64.b64decode(reportWithFields)
#             fileName = self._get_report_name(id, reportOptions)
#
#             if path:
#                 if not os.path.exists(path):
#                     os.makedirs(path)
#                 filepath = os.path.join(path, f'{fileName}')
#
#
#             else:
#                 filepath = fileName
#
#             f = open(f"{filepath}", 'wb')
#             f.write(decoded)
#         except suds.WebFault as e:
#             if e.fault.faultcode == "a:InvalidArgumentException":
#                 raise Exception(
#                     u"У документа нет отчёта/закрытого отчёта или в качестве id в GetVerificationReport передано None: " + e.fault.faultstring)
#             if e.fault.faultcode == "a:DocumentIdException":
#                 raise Exception(u"Указан невалидный DocumentId" + e.fault.faultstring)
#             raise
#         logger.info("Success create report in path: " + filepath)
#
#
# if __name__ == "__main__":
#     client = AntiplagiatClient(
#         login="testapi@antiplagiat.ru",
#         password="testapi",
#         company_name="testapi"
#     )
#
#     while True:
#
#         print("\n$____________________Меню____________________$")
#         print("1. Загрузить и индексировать документ;")
#         print("2. Проверить на оригинальность и получить отчет;")
#         print("0. Выход.")
#
#         num = int(input("Введите пункт меню: "))
#
#         if num == 1:
#             filename = input("Введите название файла для индексации: ")
#             id_index = AntiplagiatClient.add_to_index(client, filename)
#             print("Идентификатор добавленного в индекс документа: " + str(id_index))
#
#         elif num == 2:
#             id_doc = input("Введите ID документа для проверки: ")
#             try:
#                 result = client.check_document(id_doc)
#                 print(f"Отчет по документу с ID {id_doc}:")
#                 print(f"Общий процент плагиата: {result['plagiarism']}")
#                 for service in result['services']:
#                     print(f"  Сервис: {service['service_name']}")
#                     print(f"    Оригинальность: {service['originality']}")
#                     print(f"    Плагиат: {service['plagiarism']}")
#                     if service['source']:
#                         print("    Источники:")
#                         for src in service['source']:
#                             print(f"      - {src['name']} ({src['score_by_report']}) URL: {src['url']}")
#             except Exception as e:
#                 print("Ошибка при проверке документа:", e)
#
#
#         elif num == 0:
#             print("Выход.")
#
#         else:
#             print("Неверный запрос. Введите номер пункта из меню.")

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
import ssl
import os
import suds
import time
import base64
import logging
import datetime
import sys

from libs.schemas import SimpleCheckResult, Service, Source, Author, LoanBlock
from libs.logger import logger

ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import os
import suds
import time
import base64
import logging
import datetime
import sys

ANTIPLAGIAT_URI = "https://testapi.antiplagiat.ru"
LOGIN = "testapi@antiplagiat.ru"
PASSWORD = "testapi"
COMPANY_NAME = "testapi"
APICORP_ADDRESS = "api.antiplagiat.ru:4959"

# Initialize SOAP client
try:
    client = suds.client.Client(f"https://{APICORP_ADDRESS}/apiCorp/{COMPANY_NAME}?singleWsdl",
                                username=LOGIN,
                                password=PASSWORD)
except Exception as e:
    print(f"Ошибка инициализации клиента API: {str(e)}")
    sys.exit(1)

# Configure logging
logging.basicConfig(level=logging.INFO)
logging.getLogger("suds.client").setLevel(logging.DEBUG)  # Enable detailed SOAP logging

def get_doc_data(filename):
    """Prepare document data for upload."""
    try:
        data = client.factory.create("DocData")
        data.Data = base64.b64encode(open(filename, "rb").read()).decode()
        data.FileName = os.path.splitext(filename)[0]
        data.FileType = os.path.splitext(filename)[1]
        data.ExternalUserID = "ivanov"
        return data
    except Exception as e:
        print(f"Ошибка при подготовке данных документа: {str(e)}")
        return None

def upload_and_index_document(filename):
    """Upload and index a document."""
    print(f"Загрузка и индексирование документа: {filename}")
    data = get_doc_data(filename)
    if not data:
        return

    docatr = client.factory.create("DocAttributes")
    personIds = client.factory.create("PersonIDs")
    personIds.CustomID = "original"

    arr = client.factory.create("ArrayOfAuthorName")
    author = client.factory.create("AuthorName")
    author.OtherNames = "Иван Иванович"
    author.Surname = "Иванов"
    author.PersonIDs = personIds
    arr.AuthorName.append(author)
    docatr.DocumentDescription.Authors = arr

    opts = client.factory.create("UploadOptions")
    opts.AddToIndex = True

    try:
        uploadResult = client.service.UploadDocument(data, docatr, opts)
        doc_id = uploadResult.Uploaded[0].Id
        print(f"Документ успешно загружен и индексирован. ID: {doc_id}")
    except suds.WebFault as e:
        print(f"Ошибка API при загрузке документа: {e.fault.faultstring}")
    except Exception as e:
        print(f"Общая ошибка при загрузке документа: {str(e)}")

def check_originality(filename=None, doc_id=None):
    """Check document originality and get report."""
    if filename and doc_id:
        print("Ошибка: укажите либо файл, либо ID документа, но не оба.")
        return
    if not filename and not doc_id:
        print("Ошибка: необходимо указать файл или ID документа.")
        return

    # Create DocumentId object
    document_id = client.factory.create("DocumentId")

    if filename:
        print(f"Проверка оригинальности документа: {filename}")
        data = get_doc_data(filename)
        if not data:
            return

        docatr = client.factory.create("DocAttributes")
        personIds = client.factory.create("PersonIDs")
        personIds.CustomID = "original"

        arr = client.factory.create("ArrayOfAuthorName")
        author = client.factory.create("AuthorName")
        author.OtherNames = "Иван Иванович"
        author.Surname = "Иванов"
        author.PersonIDs = personIds
        arr.AuthorName.append(author)
        docatr.DocumentDescription.Authors = arr

        try:
            # Upload document
            uploadResult = client.service.UploadDocument(data, docatr)
            document_id.Id = uploadResult.Uploaded[0].Id
            print(f"Документ загружен. ID: {document_id.Id}")
        except suds.WebFault as e:
            print(f"Ошибка API при загрузке документа: {e.fault.faultstring}")
            return
        except Exception as e:
            print(f"Общая ошибка при загрузке документа: {str(e)}")
            return
    else:
        print(f"Проверка оригинальности документа с ID: {doc_id}")
        try:
            document_id.Id = int(doc_id)  # Ensure doc_id is an integer
        except ValueError:
            print("Ошибка: ID документа должен быть числом.")
            return

    try:
        # Check document using DocumentId object
        client.service.CheckDocument(document_id)
        print("Документ отправлен на проверку...")

        # Wait for check completion
        status = client.service.GetCheckStatus(document_id)
        while status.Status == "InProgress":
            print(f"Статус: В процессе, ожидаемое время: {status.EstimatedWaitTime} сек")
            time.sleep(status.EstimatedWaitTime * 0.1)
            status = client.service.GetCheckStatus(document_id)

        if status.Status == "Failed":
            print(f"Ошибка при проверке документа: {status.FailDetails}")
            return

        # Get full report
        options = client.factory.create("ReportViewOptions")
        options.FullReport = True
        options.NeedText = True
        options.NeedStats = True
        options.NeedAttributes = True
        report = client.service.GetReportView(document_id, options)

        if not report:
            print("Ошибка: отчет не получен от API.")
            return

        # Print report summary
        print(f"\nОтчет по оригинальности: {report.Summary.Score:.2f}%")
        for checkService in report.CheckServiceResults or []:
            print(f"Сервис проверки: {checkService.CheckServiceName}")
            print(f"  Легитимный контент: {checkService.ScoreByReport.Legal:.2f}%")
            print(f"  Плагиат: {checkService.ScoreByReport.Plagiarism:.2f}%")
            if hasattr(checkService, "Sources") and checkService.Sources:
                for source in checkService.Sources:
                    print(f"  Источник: {source.Name}")
                    print(f"    URL: {source.Url}")
                    print(f"    Процент совпадения: {source.ScoreByReport:.2f}%")

        # Print largest plagiarism block if exists
        if hasattr(report.Details, "CiteBlocks") and report.Details.CiteBlocks:
            max_block = max(report.Details.CiteBlocks, key=lambda x: x.Length)
            print(f"\nНаибольший блок заимствования (длина: {max_block.Length}):")
            print(f"Источник: {max_block.SrcHash}")
            text_preview = report.Details.Text[max_block.Offset:max_block.Offset + min(max_block.Length, 200)]
            print(f"Текст: {text_preview}...")

        # Print author info
        if (hasattr(report, "Attributes") and report.Attributes and
                hasattr(report.Attributes, "DocumentDescription") and
                report.Attributes.DocumentDescription and
                hasattr(report.Attributes.DocumentDescription, "Authors") and
                report.Attributes.DocumentDescription.Authors and
                report.Attributes.DocumentDescription.Authors.AuthorName):
            author_info = report.Attributes.DocumentDescription.Authors.AuthorName[0]
            print(f"\nАвтор: {author_info.Surname} {author_info.OtherNames}")
            print(f"ID автора: {author_info.PersonIDs.CustomID}")
        else:
            print("Информация об авторе недоступна.")

    except suds.WebFault as e:
        print(f"Ошибка API при проверке оригинальности: {e.fault.faultstring}")
        if "DocumentIdException" in e.fault.faultcode:
            print("Проверьте, существует ли документ с указанным ID и доступен ли он для вашей учетной записи.")
    except AttributeError as e:
        print(f"Ошибка доступа к данным отчета: {str(e)}")
        print("Возможно, отчет не сформирован или данные отсутствуют.")
    except Exception as e:
        print(f"Общая ошибка при проверке оригинальности: {str(e)}")

def main_menu():
    """Display menu and handle user input."""
    while True:
        print("\n$____________________Меню____________________$")
        print("1. Загрузить и индексировать документ")
        print("2. Проверить на оригинальность и получить отчет")
        print("0. Выход")

        choice = input("\nВыберите опцию (0-2): ")

        if choice == "1":
            filename = input("Введите путь к файлу: ")
            if os.path.exists(filename):
                upload_and_index_document(filename)
            else:
                print("Файл не найден!")
        elif choice == "2":
            use_existing_id = input("Использовать существующий ID документа? (y/n): ").lower() == 'y'
            if use_existing_id:
                doc_id = input("Введите ID документа: ")
                check_originality(doc_id=doc_id)
            else:
                filename = input("Введите путь к файлу: ")
                if os.path.exists(filename):
                    check_originality(filename=filename)
                else:
                    print("Файл не найден!")
        elif choice == "0":
            print("Выход из программы...")
            break
        else:
            print("Неверный выбор! Пожалуйста, выберите 0, 1 или 2.")

if __name__ == "__main__":
    main_menu()