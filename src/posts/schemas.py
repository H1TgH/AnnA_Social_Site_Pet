from typing import Optional, List

from pydantic import BaseModel


class PostCreationSchema(BaseModel):
    text: Optional[str]
    images: Optional[List[str]]
    