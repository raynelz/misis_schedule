from typing import Optional
from pydantic import BaseModel, ConfigDict


class LessonInput(BaseModel):
    title: str
    weekday: str
    order: int
    odd_even_week: int
    type: str
    group_name: str
    teacher_fio: Optional[str]
    room_id: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Математика",
                "weekday": 0,
                "order": 1,
                "odd_even_week": 0,
                "type": "Лекция",
                "group_name": "БИВТ-21-17",
                "teacher_fio": "Ласурия Роберт Андреевич",
                "room_id": "Б-3",
            }
        }
    )


class LessonDto(LessonInput):
    id: int

    model_config = ConfigDict(from_attributes=True)
