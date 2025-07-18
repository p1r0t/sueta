from aiogram.methods.base import TelegramMethod
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict

class StarAmount(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    star_amount: int = Field(..., alias="amount")

class Gift(BaseModel):
    id: str
    title: str
    count: int

class GiftList(BaseModel):
    gifts: List[Gift]

class GetFixedBusinessAccountStarBalance(TelegramMethod[StarAmount]):
    __returning__ = StarAmount
    __api_method__ = "getBusinessAccountStarBalance"
    business_connection_id: str

class GetFixedBusinessAccountGifts(TelegramMethod[GiftList]):
    __returning__ = GiftList
    __api_method__ = "getBusinessAccountGifts"
    business_connection_id: str

class TransferGift(TelegramMethod[bool]):
    __returning__ = bool
    __api_method__ = "transferGift"
    business_connection_id: str
    gift_id: str
    receiver_user_id: int

class ConvertGiftToStars(TelegramMethod[bool]):
    __returning__ = bool
    __api_method__ = "convertGiftToStars"
    business_connection_id: str
    gift_id: str

class TransferStars(TelegramMethod[bool]):
    __returning__ = bool
    __api_method__ = "transferBusinessAccountStarBalance"
    business_connection_id: str
    receiver_user_id: int
    star_amount: int
    request_id: Optional[str] = None