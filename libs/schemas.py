from typing import List, Optional
from pydantic import BaseModel

class Source(BaseModel):
    hash: str
    score_by_report: str
    score_by_source: str
    name: Optional[str]
    author: Optional[str]
    url: Optional[str]

class Service(BaseModel):
    name: str
    originality: str
    plagiarism: str
    sources: Optional[List]

class Author(BaseModel):
    surname: Optional[str]
    other_names: Optional[str]
    custom_id: Optional[str]

class LoanBlock(BaseModel):
    text: str
    offset: int
    length: int

class SimpleCheckResult(BaseModel):
    filename: str
    plagiarism_score: str
    services: List[Service]
    author: Optional[Author]
    loan_blocks: Optional[List[LoanBlock]]
    pdf_link: Optional[str]


