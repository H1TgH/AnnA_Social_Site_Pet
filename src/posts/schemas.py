from typing import Optional, List

from pydantic import BaseModel


class PostCreationSchema(BaseModel):
    text: Optional[str]
    images: Optional[List[str]]

class CommentCreationSchema(BaseModel):
    text: str
    parent_id: Optional[str] = None
    