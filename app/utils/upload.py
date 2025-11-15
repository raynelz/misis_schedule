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

                weekdays = df.iloc[:, 0].ffill()
                df["Дата"] = weekdays
                lesson_orders = df.iloc[:, 1].ffill()
                df["Номер"] = lesson_orders
                df["Номер"] = df["Номер"].astype(int, errors="ignore")

                columns = list(
                    pd.DataFrame(df.columns)
                    .replace(r"^Unnamed.*", np.nan, regex=True)
                    .ffill(limit=1)[0]
                )
                df.columns = columns
                log.debug(f"After ffill columns: {list(df.columns)}")

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
                # Фильтруем колонки, которые являются nan или начинаются с "nan"
                valid_columns = []
                for col in df.columns:
                    if pd.isna(col) or (isinstance(col, str) and col.lower().startswith("nan")):
                        continue
                    valid_columns.append(col)
                
                df = df.loc[:, valid_columns]
                log.debug(f"After nan filtering columns ({len(df.columns)}): {list(df.columns)}")

                # Удаляем служебные колонки
                columns_to_drop = ["Время"]
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

                df["weekday"] = df["weekday"].map(
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