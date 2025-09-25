from uuid import UUID

from sqlalchemy import select, func

from src.messages.models import ConversationModel, ConversationParticipantModel


async def get_or_create_conversation(session, sender_id: UUID, receiver_id: UUID):
    try:
        subquery = (
            select(ConversationParticipantModel.conversation_id)
            .where(ConversationParticipantModel.user_id.in_([sender_id, receiver_id]))
            .group_by(ConversationParticipantModel.conversation_id)
            .having(func.count(func.distinct(ConversationParticipantModel.user_id)) == 2)
        )

        result = await session.execute(
            select(ConversationModel)
            .where(ConversationModel.id.in_(subquery))
        )
        conversation = result.scalars().first()

        if conversation:
            return str(conversation.id)

        new_conversation = ConversationModel()
        session.add(new_conversation)
        await session.flush()

        participants = [
            ConversationParticipantModel(
                conversation_id=new_conversation.id,
                user_id=sender_id
            ),
            ConversationParticipantModel(
                conversation_id=new_conversation.id,
                user_id=receiver_id
            )
        ]
        session.add_all(participants)
        await session.commit()

        print(f'Created new conversation {new_conversation.id} between users {sender_id} and {receiver_id}')
        return str(new_conversation.id)
    
    except Exception as e:
        print(f'Error in get_or_create_conversation: {e}')
        await session.rollback()
        raise
