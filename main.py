import os
import base64
import asyncio
import logging
import datetime
import urllib3
import ssl
import httpx
import zeep
from zeep.transports import AsyncTransport

from libs.schemas import SimpleCheckResult, Service, Source, Author, LoanBlock
from libs.logger import logger

# Отключаем проверку SSL (для тестовых серверов)
ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(level=logging.INFO)


class AsyncAntiplagiatClient:

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
        self.httpx_client = httpx.AsyncClient(auth=(self.login, self.password))
        self.client = zeep.AsyncClient(
            f'https://{self.apicorp_address}/apiCorp/{self.company_name}?singleWsdl',
            transport=AsyncTransport(client=self.httpx_client))
        self.factory = self.client.type_factory('ns0')

    async def _get_doc_data(self, filename: str, external_user_id: str):
        Data = base64.b64encode(open(filename, "rb").read()).decode()
        FileName = os.path.basename(filename)
        FileType = os.path.splitext(filename)[1]
        ExternalUserID = external_user_id

        data = self.factory.DocData(Data=Data, FileName=FileName, FileType=FileType, ExternalUserID=ExternalUserID)
        return data

    async def simple_check(self, filename: str, author_surname='',
                           author_other_names='',
                           external_user_id='ivanov', custom_id='original'
                           ) -> SimpleCheckResult:
        logger.info("SimpleCheck filename=" + filename)

        data = await self._get_doc_data(filename, external_user_id=external_user_id)
        docatr = self.factory.DocAttributes()

        personIds = self.factory.PersonIDs()
        personIds.CustomID = custom_id
        arr = self.factory.ArrayOfAuthorName()
        author = self.factory.AuthorName()
        author.OtherNames = author_other_names
        author.Surname = author_surname
        author.PersonIDs = personIds
        arr.AuthorName.append(author)

        try:
            docatr.Authors = arr
        except Exception as e:
            logger.warning(f"Failed to set Authors in DocAttributes: {e}")

        try:
            uploadResult = await self.client.service.UploadDocument(data, docatr)
        except Exception as e:
            logger.error(f"UploadDocument failed: {e}")
            raise

        doc_id = uploadResult[0]['Id']

        try:
            await self.client.service.CheckDocument(doc_id)
        except Exception as e:
            logger.error(f"CheckDocument failed: {e}")
            raise

        status = await self.client.service.GetCheckStatus(doc_id)

        while status.Status == "InProgress":
            await asyncio.sleep(status.EstimatedWaitTime * 0.1)
            status = await self.client.service.GetCheckStatus(doc_id)

        if status.Status == "Failed":
            print(f"An error occurred while validating the document {filename}: {status.FailDetails}")
            return

        report = await self.client.service.GetReportView(doc_id)

        logger.info(f"Report Summary: {report.Summary.Score:.2f}%")

        loan_blocks = []
        if hasattr(report.Details, "CiteBlocks") and report.Details.CiteBlocks:
            for block in report.Details.CiteBlocks:
                loan_block = LoanBlock(
                    text=report.Details.Text[block.Offset:block.Offset + block.Length],
                    offset=block.Offset,
                    length=block.Length)
                loan_blocks.append(loan_block)

        result = SimpleCheckResult(
            filename=os.path.basename(filename),
            plagiarism=f'{report.Summary.Score:.2f}%',
            services=[],
            author=Author(
                surname=author_surname or '',
                othernames=author_other_names or '',
                custom_id=custom_id
            ),
            loan_blocks=loan_blocks
        )

        for checkService in report.CheckServiceResults:
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

                logger.info(
                    f'\t{source.SrcHash}: Score={source.ScoreByReport:.2f}%({source.ScoreBySource:.2f}%), '
                    f'Name="{source.Name}" Author="{source.Author}"'
                    f' Url="{source.Url}"')

            result.services.append(service)

        return result.model_dump()


async def main():
    login = input("Введите логин: ")
    password = input("Введите пароль: ")
    company_name = input("Введите название компании: ")

    client = AsyncAntiplagiatClient(login, password, company_name)

    while True:
        print("\n=== Меню ===")
        print("1. Проверить файл и получить отчет")
        print("0. Выход")

        choice = input("Выберите пункт меню: ").strip()

        if choice == '0':
            print("Выход...")
            break

        elif choice == '1':
            filename = input("Введите путь к файлу для проверки: ").strip()
            if not filename or not os.path.isfile(filename):
                print("Файл не найден. Попробуйте снова.")
                continue

            author_surname = input("Фамилия автора (необязательно): ").strip()
            author_other_names = input("Имя автора (необязательно): ").strip()
            custom_id = input("Custom ID (необязательно, по умолчанию 'original'): ").strip() or 'original'

            print(f"Запуск проверки файла '{filename}'...")

            try:
                result = await client.simple_check(
                    filename,
                    author_surname=author_surname,
                    author_other_names=author_other_names,
                    custom_id=custom_id
                )
                print("Отчет по проверке:")
                print(result)
            except Exception as e:
                print(f"Ошибка при проверке файла: {e}")

        else:
            print("Неверный выбор. Пожалуйста, выберите пункт из меню.")


if __name__ == "__main__":
    asyncio.run(main())
