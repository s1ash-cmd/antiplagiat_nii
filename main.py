import os
import time
import base64
import urllib3
from zeep import Client
from zeep.transports import Transport
from zeep.exceptions import Fault
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
        self.login = login
        self.password = password
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
            FileName=os.path.splitext(filename)[0],
            FileType=os.path.splitext(filename)[1],
            ExternalUserID=external_user_id
        )

    def add_to_index(self, filename: str, author_surname: str = '',
                     author_other_names: str = '',
                     external_user_id: str = 'ivanov',
                     custom_id: str = 'original') -> object:
        logger.info(f"Indexing document: {filename}")
        data = self._get_doc_data(filename, external_user_id=external_user_id)

        person_ids = self.factory.PersonIDs(CustomID=custom_id)
        docatr = self.factory.DocAttributes()
        arr = self.factory.ArrayOfAuthorName()
        author = self.factory.AuthorName(
            OtherNames=author_other_names,
            Surname=author_surname,
            PersonIDs=person_ids
        )
        arr.AuthorName.append(author)
        docatr.DocumentDescription = {'Authors': arr}

        try:
            upload_result = self.client.service.UploadDocument(data, docatr)
        except Fault as e:
            logger.error(f"SOAP Fault during upload: {e}")
            raise
        except Exception:
            logger.exception("Failed to upload document")
            raise

        try:
            uploaded = upload_result.Uploaded[0]
        except (AttributeError, IndexError):
            uploaded = upload_result[0]

        def get_id(obj):
            if hasattr(obj, 'Id'):
                return obj.Id
            if isinstance(obj, dict) and 'Id' in obj:
                return obj['Id']
            return obj

        doc_id_val = get_id(get_id(uploaded))

        doc_id = self.factory.DocumentId(Id=doc_id_val, External=None)
        logger.info(f"Indexed document ID: {doc_id_val}")

        return doc_id

    def check_by_id(self, doc_id: object) -> dict:
        logger.info(f"Starting check for document ID: {doc_id.Id}")

        try:
            self.client.service.CheckDocument(doc_id)
        except Fault as e:
            logger.error(f"SOAP Fault during check start: {e}")
            raise

        status = self.client.service.GetCheckStatus(doc_id)
        while status.Status == "InProgress":
            time.sleep(status.EstimatedWaitTime * 0.1)
            status = self.client.service.GetCheckStatus(doc_id)

        if status.Status == "Failed":
            logger.error(f"An error occurred while validating the document ID {doc_id.Id}: {status.FailDetails}")

        report = self.client.service.GetReportView(doc_id)
        logger.info(f"Report Summary: {report.Summary.Score:.2f}%")
        logger.info(f"Report attributes: {dir(report)}")

        options = self.factory.ReportViewOptions(
            FullReport=True,
            NeedText=True,
            NeedStats=True,
            NeedAttributes=True
        )

        fullreport = self.client.service.GetReportView(doc_id, options)
        logger.info(f"DocumentDescription attributes: {dir(fullreport.Attributes.DocumentDescription)}")
        if hasattr(fullreport.Attributes.DocumentDescription, 'Work'):
            logger.info(f"Work field content: {fullreport.Attributes.DocumentDescription.Work}")

        filename = getattr(fullreport.Attributes.DocumentDescription, 'Work', 'unknown')
        if filename != 'unknown' and hasattr(fullreport.Attributes.DocumentDescription, 'FileType'):
            filename = f"{filename}{getattr(fullreport.Attributes.DocumentDescription, 'FileType', '')}"
        print(f"Имя файла, полученное от сервера: {filename}")

        result = SimpleCheckResult(
            filename=filename,
            plagiarism_score=f'{report.Summary.Score:.2f}%',
            services=[],
            author=Author(surname="", other_names="", custom_id="original"),
            loan_blocks=[],
            pdf_link=''
        )

        for checkService in getattr(report, 'CheckServiceResults', []) or []:
            logger.info(f"ScoreByReport raw: {checkService.ScoreByReport}")

            score_report = checkService.ScoreByReport
            unknown = getattr(score_report, 'Unknown', 0.0)
            plagiarism = getattr(score_report, 'Plagiarism', 0.0)

            service = Service(
                name=checkService.CheckServiceName,
                originality=f"{unknown:.2f}%",
                plagiarism=f"{plagiarism:.2f}%",
                sources=[]
            )

            logger.info(
                f"Check service: {checkService.CheckServiceName}, "
                f"Score.White={checkService.ScoreByReport.Legal:.2f}% "
                f"Score.Black={checkService.ScoreByReport.Plagiarism:.2f}%"
            )

            for source in getattr(checkService, 'Sources', []) or []:
                _source = Source(
                    hash=source.SrcHash,
                    score_by_report=f'{source.ScoreByReport:.2f}%',
                    score_by_source=f'{source.ScoreBySource:.2f}%',
                    name=source.Name,
                    author=source.Author,
                    url=source.Url
                )

                service.sources.append(_source)

                logger.info(
                    f'\t{source.SrcHash}: Score={source.ScoreByReport:.2f}%({source.ScoreBySource:.2f}%), '
                    f'Name="{source.Name}" Author="{source.Author}" Url="{source.Url}"'
                )

            result.services.append(service)

        author_info = fullreport.Attributes.DocumentDescription.Authors.AuthorName[0]
        result.author.surname = author_info.Surname
        result.author.other_names = author_info.OtherNames
        result.author.custom_id = author_info.PersonIDs.CustomID

        loan_blocks = []
        for block in getattr(fullreport.Details, 'CiteBlocks', []) or []:
            text = fullreport.Details.Text[block.Offset:block.Offset + block.Length]
            loan_block = LoanBlock(
                text=text,
                offset=block.Offset,
                length=block.Length
            )
            loan_blocks.append(loan_block)

        result.loan_blocks = loan_blocks

        exportReportInfo = self.client.service.ExportReportToPdf(doc_id)
        logger.info(f"ExportReportInfo attributes: {dir(exportReportInfo)}")

        while exportReportInfo.Status == "InProgress":
            time.sleep(max(exportReportInfo.EstimatedWaitTime, 10) * 0.1)
            exportReportInfo = self.client.service.ExportReportToPdf(doc_id)

        # Формирование отчета закончилось неудачно.
        if exportReportInfo.Status == "Failed":
            print("При формировании PDF-отчета для документа %s произошла ошибка: %s" % (filename, exportReportInfo.FailDetails))

        pdf_path = self.download_report(exportReportInfo.DownloadLink, f"report_{doc_id.Id}.pdf")
        print(f"PDF отчёт сохранён: {pdf_path}")

        result.pdf_link = f"{self.antiplagiat_uri}{exportReportInfo.DownloadLink}"

        return result.model_dump()

    def download_report(self, download_link: str, dest: str):
        url = f"{self.antiplagiat_uri}{download_link}"
        # Та же сессия, что и для SOAP
        resp = self.client.transport.session.get(url, verify=False)
        resp.raise_for_status()

        with open(dest, "wb") as f:
            f.write(resp.content)
        logger.info(f"Отчёт сохранён в {dest}")
        return dest

if __name__ == "__main__":
    client = AntiplagiatClient(
        login="testapi@antiplagiat.ru",
        password="testapi",
        company_name="testapi"
    )

    while True:
        print("\n$____________________Меню____________________$")
        print("1. Индексировать документ;")
        print("2. Проверить на оригинальность по id;")
        print("3. Загрузить и проверить документ;")
        print("0. Выход.")

        choice = input("Введите пункт меню: ")
        if choice == '1':
            filename = input("Введите название файла для индексации: ")
            author_surname = input("Введите фамилию автора: ")
            author_other_names = input("Введите имя автора: ")
            external_user_id = input("Введите внешний ID пользователя: ")
            try:
                doc_id = client.add_to_index(
                    filename,
                    author_surname=author_surname,
                    author_other_names=author_other_names,
                    external_user_id=external_user_id,
                    custom_id = "original"
                )
                print(f"Идентификатор добавленного в индекс документа: {doc_id.Id}")
            except Exception as e:
                print(f"Ошибка при индексации: {e}")

        elif choice == '2':
            raw_id = int(input("Введите ID документа для проверки: "))
            doc_id = client.factory.DocumentId(Id=raw_id, External=None)
            try:
                report = client.check_by_id(doc_id)
                print("\nОтчет проверки:")
                print(f"Общий процент плагиата: {report['plagiarism_score']}")
                print("\nРезультаты по сервисам:")
                for svc in report['services']:
                    print(f"Сервис: {svc['name']}")
                    print(f"Оригинальность: {svc['originality']}")
                    print(f"Плагиат: {svc['plagiarism']}")

            except Exception as e:
                print(f"Ошибка при проверке: {e}")


        elif choice == '3':
            filename = input("Введите путь к файлу: ")
            author_surname = input("Введите фамилию автора: ")
            author_other_names = input("Введите имя автора: ")
            external_user_id = input("Введите внешний ID пользователя: ")
            try:
                doc_id = client.add_to_index(
                    filename,
                    author_surname=author_surname,
                    author_other_names=author_other_names,
                    external_user_id=external_user_id,
                    custom_id="original"
                )
                print(f"Документ добавлен в индекс с ID: {doc_id.Id}")

                report = client.check_by_id(doc_id)
                print("\nОтчет проверки:")
                print(f"Общий процент плагиата: {report['plagiarism_score']}")
                print("\nРезультаты по сервисам:")
                for svc in report['services']:
                    print(f"Сервис: {svc['name']}")
                    print(f"Оригинальность: {svc['originality']}")
                    print(f"Плагиат: {svc['plagiarism']}")

            except Exception as e:
                print(f"Ошибка при загрузке и проверке: {e}")

        elif choice == '0':
            print("Выход...")
            break

        else:
            print("Неверный выбор. Попробуйте снова.")