import pandas as pd
import numpy as np
import httpx
import bs4

from app.utils.logging import log
from app.loader import engine
from app.configs.settings import settings


def data_preprocess(df: pd.DataFrame, group, odd_even: str) -> pd.DataFrame:
    # Safely extract group column (handle accidental duplicate column names)
    group_col = df[group]
    if isinstance(group_col, pd.DataFrame):
        group_col = group_col.iloc[:, 0]  # take first if duplicates

    room_col = df[f"{group}-кабинеты"]
    if isinstance(room_col, pd.DataFrame):
        room_col = room_col.iloc[:, 0]

    cur = pd.DataFrame({
        group: group_col,
        "order": df["order"],
        "weekday": df["weekday"],
        f"{group}-кабинеты": room_col,
    })
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

            df = pd.read_excel(data, sheet_name=sheet_name)

            weekdays = df.iloc[:, 0].ffill()
            df["Дата"] = weekdays
            lesson_orders = df.iloc[:, 1].ffill()
            df["Номер"] = lesson_orders
            df["Номер"] = df["Номер"].astype(int, errors="ignore")

            # --- NEW COLUMN NORMALIZATION FOR NEW XLSX FORMAT ---
            raw_cols = list(df.columns)

            # First 3 columns: Дата, Номер, Время
            fixed_cols = raw_cols[:3]

            other = raw_cols[3:]
            groups = []

            # Ensure even number of columns (drop trailing garbage column if exists)
            if len(other) % 2 != 0:
                other = other[:-1]

            i = 0
            while i < len(other):
                group_col = other[i]

                # Resolve Unnamed columns by inheriting the previous real group name
                if "Unnamed" in str(group_col):
                    j = i - 1
                    while j >= 0 and "Unnamed" in str(other[j]):
                        j -= 1
                    group_col = other[j]

                groups.append(group_col)

                room_col = f"{group_col}-кабинеты"
                fixed_cols.append(group_col)
                fixed_cols.append(room_col)

                i += 2

            df.columns = fixed_cols

            df = df.rename(
                columns={
                    "Дата": "weekday",
                    "Номер": "order",
                }
            )
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
                data_preprocess(odd, group, "odd")
                data_preprocess(even, group, "even")
