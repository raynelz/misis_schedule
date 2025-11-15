import pandas as pd
import numpy as np
import httpx
import bs4

from app.utils.logging import log
from app.loader import engine
from app.configs.settings import settings


def data_preprocess(df: pd.DataFrame, group, odd_even: str) -> pd.DataFrame:
    cur = df.loc[:, [group, "order", "weekday", f"{group}-кабинеты"]]
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

            columns = list(
                pd.DataFrame(df.columns)
                .replace(r"^Unnamed.*", np.nan, regex=True)
                .ffill(limit=1)[0]
            )
            df.columns = columns

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
            df = df.loc[:, ~df.columns.str.startswith("nan", na=False)]
            df.drop(columns=["Время", np.nan], inplace=True, errors="ignore")

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