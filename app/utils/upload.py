import pandas as pd
import numpy as np
import httpx
import bs4

from app.utils.logging import log
from app.loader import engine
from app.configs.settings import settings


def data_preprocess(df: pd.DataFrame, group, odd_even: str) -> pd.DataFrame:
    try:
        cur = df.loc[:, [group, "order", "weekday", f"{group}-кабинеты"]]
    except KeyError as e:
        log.error(f"Missing columns for group {group}. Available: {list(df.columns)}")
        raise
    cur.dropna(inplace=True)
    cur.rename(
        columns={
            f"{group}-кабинеты": "room_id",
            group: "title",
        },
        inplace=True,
    )

    # Преобразуем title в строку перед использованием .str accessor
    cur["title"] = cur["title"].astype(str)
    cur["teacher_fio"] = cur["title"].str.split("\n").str[1]
    cur["type"] = cur["title"].str.extract(r"\(([^)]*)\)[^(]*$")
    cur["title"] = cur["title"].str.split("\n").str[0]
    cur["odd_even_week"] = 0 if odd_even == "even" else 1
    cur["group_name"] = group

    cur.to_sql(
        "lessons",
        engine,
        if_exists="append",
        index=False,
    )


def upload_schedules():
    log.debug("Uploading schedules")
    response = httpx.get(settings.SCHEDULE_URL, timeout=60)
    if response.status_code != 200:
        raise Exception("Can't get schedule")

    soup = bs4.BeautifulSoup(response.text, "html.parser")
    div = soup.find("div", class_="data")
    links = [
        "https://misis.ru" + link["href"]
        for link in div.find_all("a")
        if "ibo" not in link["href"]
    ]

    for link in links:
        data = pd.ExcelFile(link)
        log.debug(link)

        for sheet_name in data.sheet_names:
            if "курс" not in sheet_name:
                continue

            try:
                df = pd.read_excel(data, sheet_name=sheet_name)
                
                # Логируем исходные колонки
                log.debug(f"File: {link}, Sheet: {sheet_name}")
                log.debug(f"Original columns ({len(df.columns)}): {list(df.columns)}")
                log.debug(f"DataFrame shape: {df.shape}")
                log.debug(f"First few rows:\n{df.head()}")

                # Заполняем пропуски в первых колонках
                for i in range(min(3, len(df.columns))):
                    df.iloc[:, i] = df.iloc[:, i].ffill()

                # Обрабатываем названия колонок
                columns = list(
                    pd.DataFrame(df.columns)
                    .replace(r"^Unnamed.*", np.nan, regex=True)
                    .ffill(limit=1)[0]
                )
                df.columns = columns
                log.debug(f"After ffill columns: {list(df.columns)}")

                # Умное определение колонок по содержимому
                weekday_col_idx = None
                order_col_idx = None
                time_col_idx = None
                
                weekdays_list = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
                
                # Ищем колонку с днями недели
                for idx, col in enumerate(df.columns[:5]):  # Проверяем первые 5 колонок
                    if pd.isna(col):
                        continue
                    try:
                        # Используем iloc для гарантированного получения Series
                        col_series = df.iloc[:, idx]
                        sample_values = col_series.dropna().head(10).astype(str).tolist()
                        if any(day in ' '.join(sample_values) for day in weekdays_list):
                            weekday_col_idx = idx
                            log.debug(f"Found weekday column at index {idx}: {col}")
                            break
                    except Exception as e:
                        log.debug(f"Error checking column {idx} ({col}): {e}")
                        continue
                
                # Ищем колонку с номерами пар (должна содержать числа 1-5)
                for idx, col in enumerate(df.columns[:5]):
                    if pd.isna(col) or idx == weekday_col_idx:
                        continue
                    try:
                        # Используем iloc для гарантированного получения Series
                        col_series = df.iloc[:, idx]
                        # Пробуем преобразовать в числа
                        numeric_values = pd.to_numeric(col_series.dropna().head(20), errors='coerce')
                        valid_numbers = numeric_values.dropna()
                        if len(valid_numbers) > 0:
                            # Проверяем, что числа в диапазоне 1-10 (номера пар)
                            if valid_numbers.between(1, 10).sum() > len(valid_numbers) * 0.5:
                                order_col_idx = idx
                                log.debug(f"Found order column at index {idx}: {col}")
                                break
                    except Exception as e:
                        log.debug(f"Error checking column {idx} ({col}): {e}")
                        continue
                
                # Ищем колонку со временем (формат "09:00:00 - 10:35:00" или подобный)
                for idx, col in enumerate(df.columns[:5]):
                    if pd.isna(col) or idx in [weekday_col_idx, order_col_idx]:
                        continue
                    try:
                        # Используем iloc для гарантированного получения Series
                        col_series = df.iloc[:, idx]
                        sample_values = col_series.dropna().head(10).astype(str).tolist()
                        if any(':' in str(val) and '-' in str(val) for val in sample_values):
                            time_col_idx = idx
                            log.debug(f"Found time column at index {idx}: {col}")
                            break
                    except Exception as e:
                        log.debug(f"Error checking column {idx} ({col}): {e}")
                        continue

                # Если не нашли автоматически, используем старую логику (первые две колонки)
                if weekday_col_idx is None:
                    weekday_col_idx = 0
                    log.debug("Using default weekday column (index 0)")
                if order_col_idx is None:
                    order_col_idx = 1 if weekday_col_idx != 1 else 2
                    log.debug(f"Using default order column (index {order_col_idx})")

                # Создаем колонки Дата и Номер из найденных
                df["Дата"] = df.iloc[:, weekday_col_idx].ffill()
                df["Номер"] = df.iloc[:, order_col_idx].ffill()
                
                # Преобразуем номер в int, если возможно
                df["Номер"] = pd.to_numeric(df["Номер"], errors='coerce').astype('Int64')
                
                log.debug(f"Weekday column index: {weekday_col_idx}, Order column index: {order_col_idx}")

                # Сохраняем исходные названия колонок до обработки дубликатов
                original_col_names = list(df.columns)
                
                # Обрабатываем дубликаты в названиях колонок
                groups = set(columns)
                try:
                    groups.remove("Номер")
                    groups.remove("Дата")
                    groups.remove("Время")
                    groups.remove(np.nan)
                except KeyError:
                    pass

                df.columns = [
                    f"{col}-кабинеты" if is_duplicated else col
                    for col, is_duplicated in zip(
                        df.columns, df.columns.duplicated(keep="first")
                    )
                ]
                log.debug(f"After duplicate handling columns: {list(df.columns)}")

                # Улучшенная фильтрация nan колонок
                valid_columns = []
                for col in df.columns:
                    if pd.isna(col) or (isinstance(col, str) and col.lower().startswith("nan")):
                        continue
                    valid_columns.append(col)
                
                df = df.loc[:, valid_columns]
                log.debug(f"After nan filtering columns ({len(df.columns)}): {list(df.columns)}")

                # Удаляем служебные колонки (время и исходные колонки, которые мы уже скопировали)
                columns_to_drop = ["Время"]
                
                # Удаляем исходные колонки, если они еще есть (но не "Дата" и "Номер", которые мы создали)
                if weekday_col_idx < len(original_col_names):
                    orig_weekday_col = original_col_names[weekday_col_idx]
                    if orig_weekday_col not in ["Дата", "Номер"] and orig_weekday_col in df.columns:
                        columns_to_drop.append(orig_weekday_col)
                if order_col_idx < len(original_col_names):
                    orig_order_col = original_col_names[order_col_idx]
                    if orig_order_col not in ["Дата", "Номер"] and orig_order_col in df.columns:
                        columns_to_drop.append(orig_order_col)
                if time_col_idx is not None and time_col_idx < len(original_col_names):
                    orig_time_col = original_col_names[time_col_idx]
                    if orig_time_col not in ["Дата", "Номер"] and orig_time_col in df.columns:
                        columns_to_drop.append(orig_time_col)
                
                for col in columns_to_drop:
                    if col in df.columns:
                        df.drop(columns=[col], inplace=True, errors="ignore")
                
                log.debug(f"Final columns before rename ({len(df.columns)}): {list(df.columns)}")

                df = df.rename(
                    columns={
                        "Дата": "weekday",
                        "Номер": "order",
                    }
                )
                
                # Обновляем список групп после всех преобразований
                groups = set(df.columns)
                groups.discard("weekday")
                groups.discard("order")
                # Удаляем колонки с "-кабинеты" из списка групп
                groups = {g for g in groups if not g.endswith("-кабинеты")}
                
                log.debug(f"Groups to process: {list(groups)}")
                log.debug(f"Final DataFrame columns: {list(df.columns)}")

                # Преобразуем weekday в числа
                df["weekday"] = df["weekday"].astype(str).map(
                    {
                        "Понедельник": 0,
                        "Вторник": 1,
                        "Среда": 2,
                        "Четверг": 3,
                        "Пятница": 4,
                        "Суббота": 5,
                        "Воскресенье": 6,
                    }
                )

                odd = df.iloc[::2, :]
                even = df.iloc[1::2, :]

                for group in groups:
                    try:
                        # Проверяем наличие всех необходимых колонок
                        required_cols = [group, "order", "weekday", f"{group}-кабинеты"]
                        missing_cols = [col for col in required_cols if col not in df.columns]
                        if missing_cols:
                            log.warning(f"Missing columns for group {group}: {missing_cols}. Available: {list(df.columns)}")
                            continue
                        
                        data_preprocess(odd, group, "odd")
                        data_preprocess(even, group, "even")
                    except Exception as e:
                        log.error(f"Error processing group {group} in {link}/{sheet_name}: {e}")
                        log.error(f"Available columns: {list(df.columns)}")
                        raise

            except Exception as e:
                log.error(f"Error processing sheet {sheet_name} in {link}: {e}")
                log.error(f"Columns at error: {list(df.columns) if 'df' in locals() else 'N/A'}")
                raise