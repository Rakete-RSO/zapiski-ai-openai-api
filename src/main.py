import base64
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID

from fastapi import (Depends, FastAPI, File, Form, HTTPException, UploadFile,
                     status)
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .auth import verify_access_token
from .database import create_tables, get_db
from .models import Chat, Message
from .openai_service import get_completion


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Startup code
    create_tables()
    yield


app = FastAPI(lifespan=lifespan)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


@app.post("/chat")
def create_chat(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = verify_access_token(token)
    if not payload:
        return {"msg": "Invalid token"}
    user_id = payload["sub"]
    new_chat = Chat(user_id=user_id, created_at=datetime.now())
    db.add(new_chat)
    db.commit()
    db.refresh(new_chat)

    # Insert the system prompt message
    system_prompt = "You are a helpful assistant."
    system_message = Message(
        chat_id=new_chat.id,
        content=system_prompt,
        role="system",
        visible=False,
        created_at=datetime.now(),
    )
    db.add(system_message)
    db.commit()
    db.refresh(system_message)

    return {"chat_id": new_chat.id}


@app.post("/chat/messages")
def create_message(
    chat_id: UUID = Form(...),
    message: str = Form(...),
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    # Verify the token
    payload = verify_access_token(token)
    if not payload:
        return {"msg": "Invalid token"}
    print(payload)
    user_id = payload["sub"]
    if not user_id:
        return {"msg": "Invalid token payload"}

    # Get the chat from the database
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        return {"msg": "Chat not found"}

    filetype = (file.filename or "").split(".")[-1]
    base64_image = get_image_base64(file)
    formatted_base64_image = ""
    if base64_image:
        formatted_base64_image = format_base64_image(base64_image, filetype)
    # Get the system message from the database
    previous_messages = db.query(Message).filter(Message.chat_id == chat_id).all()
    if not previous_messages:
        return {"msg": "No messages found, expected at least system message"}
    openai_messages = build_openai_input(
        previous_messages, message, formatted_base64_image
    )
    print("openai_messages", openai_messages)
    assistant_message = get_completion(openai_messages)
    user_message_db = Message(
        chat_id=chat_id,
        content=message,
        role="user",
        visible=True,
        created_at=datetime.now(),
        base64_image=formatted_base64_image,
    )
    assistant_message_db = Message(
        chat_id=chat_id,
        content=assistant_message,
        role="assistant",
        visible=True,
        created_at=datetime.now(),
    )
    db.add(user_message_db)
    db.add(assistant_message_db)
    db.commit()
    db.refresh(user_message_db)
    db.refresh(assistant_message_db)

    return {"message_id": user_message_db.id, "content": assistant_message_db.content}


def get_image_base64(file: UploadFile) -> str:
    base64_image = ""
    if file:
        try:
            # Read the file content
            file_content = file.file.read()
            # Encode to base64
            base64_image = base64.b64encode(file_content).decode("utf-8")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to process file: {str(e)}",
            )
        finally:
            file.file.close()
    return base64_image


def format_base64_image(base64_image: str, filetype: str) -> str:
    return f"data:image/{filetype};base64,{base64_image}"


# messages: A list of messages comprising the conversation so far. Depending on the
#   [model](https://platform.openai.com/docs/models) you use, different message
#   types (modalities) are supported, like
#   [text](https://platform.openai.com/docs/guides/text-generation),
#   [images](https://platform.openai.com/docs/guides/vision), and
#   and more
def build_openai_input(
    previous_messages: list[Message], user_input: str, base64_image: str
):
    output = []
    for message in previous_messages:
        content = []
        if message.content:
            content.append({"type": "text", "text": message.content})
        if message.base64_image:
            content.append(
                {"type": "image_url", "image_url": {"url": message.base64_image}}
            )
        output.append({"role": message.role, "content": message.content})

    new_content = []
    if base64_image:
        new_content.append({"type": "image_url", "image_url": {"url": base64_image}})
    if user_input:
        new_content.append({"type": "text", "text": user_input})
    output.append({"role": "user", "content": new_content})
    return output
