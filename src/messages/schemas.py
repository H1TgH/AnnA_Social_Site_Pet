from uuid import UUID

from pydantic import BaseModel


class MessageCreateSchema(BaseModel):
    receiver_id: UUID
    text: str