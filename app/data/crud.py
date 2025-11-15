from sqlalchemy.orm import Session

from app.data import models
from app.utils.logging import log
from app.dependencies import ScheduleFilters


def get_lessons(
    db: Session,
    filters: ScheduleFilters,
    offset: int,
    limit: int,
) -> list[models.Lesson]:
    """
    Получить занятия по фильтрам
    """
    db_query = db.query(models.Lesson)
    if filters.group_name:
        # Используем точное совпадение, но нормализуем пробелы
        # Убираем лишние пробелы и приводим к единому формату
        normalized_group_name = " ".join(filters.group_name.split())
        db_query = db_query.filter(models.Lesson.group_name == normalized_group_name)
        log.debug(f"Filtering by group_name: '{normalized_group_name}' (original: '{filters.group_name}')")
    if filters.teacher_fio:
        db_query = db_query.filter(models.Lesson.teacher_fio == filters.teacher_fio)
    if filters.room_id:
        db_query = db_query.filter(models.Lesson.room_id == filters.room_id)
    if filters.weekday is not None:
        db_query = db_query.filter(models.Lesson.weekday == filters.weekday)

    # Применяем фильтр по типу недели только если он задан
    if filters.week_type is not None:
        db_query = db_query.filter(models.Lesson.odd_even_week == filters.week_type)
        log.debug(f"Filtering by week_type: {filters.week_type}")

    log.debug(f"Query will return {db_query.count()} records before offset/limit")
    
    return (
        db_query
        .offset(offset)
        .limit(limit)
        .all()
    )
