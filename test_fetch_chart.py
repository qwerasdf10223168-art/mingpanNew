import requests
from bs4 import BeautifulSoup
import re

def fetch_chart_requests(year, month, day, hour, gender):
    print(f"⚙️ 抓取命盤：{year}-{month}-{day} {hour}h 性別={gender}")

    session = requests.Session()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/129.0 Safari/537.36"
        ),
        "Referer": "https://fate.windada.com/cgi-bin/fate",
    }

    # Step 1️⃣: GET 首頁以獲取正確 form 結構
    res = session.get("https://fate.windada.com/cgi-bin/fate", headers=headers, timeout=15)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    form = soup.find("form")
    if not form:
        raise Exception("找不到表單 (<form>)")

    action = form.get("action", "fate").strip()
    print(f"🧩 表單 action: {action}")

    # 建立要提交的 data（包含隱藏欄位）
    data = {}
    for inp in form.find_all("input"):
        name = inp.get("name")
        value = inp.get("value", "")
        if name:
            data[name] = value

    # 手動補上使用者輸入的值
    data["Sex"] = "1" if gender.lower().startswith("m") else "2"
    data["Year"] = str(year)
    data["Month"] = str(month)
    data["Day"] = str(day)
    data["Hour"] = str(hour)
    data["Submit"] = "查詢命盤"

    print("📦 最終送出資料：")
    for k, v in data.items():
        print(f"  {k} = {v}")

    # Step 2️⃣: 修正 action 路徑，組出正確 URL
    if action.startswith("http"):
        post_url = action
    elif action.startswith("/"):
        post_url = "https://fate.windada.com" + action
    else:
        post_url = "https://fate.windada.com/cgi-bin/" + action

    print(f"🚀 POST 目標網址：{post_url}")

    response = session.post(post_url, data=data, headers=headers, timeout=30)
    print("📡 狀態碼：", response.status_code)
    response.raise_for_status()

    # 儲存 HTML 方便檢查
    with open("response_debug.html", "w", encoding="utf-8") as f:
        f.write(response.text)

    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.title.get_text() if soup.title else "(無標題)"
    print(f"📄 頁面標題：{title}")
    print("📜 頁面前 300 字：\n", soup.get_text()[:300])

    tables = soup.find_all("table")
    print(f"🔍 找到 {len(tables)} 個 <table>")

    main_table = None
    for t in tables:
        if "命宮" in t.get_text():
            main_table = t
            break

    if not main_table:
        raise Exception("找不到命盤主表格")

    # 擷取每個宮位
    cells = main_table.find_all("td")
    chart_data = []
    for c in cells:
        txt = c.get_text(strip=True)
        if txt:
            txt = re.sub(r'^\d+\.\s*', '', txt)
            chart_data.append(txt)

    print("✅ 命盤內容：\n")
    for cell in chart_data:
        print(cell)
        print()

    return chart_data


if __name__ == "__main__":
    year = 1991
    month = 7
    day = 24
    hour = 17
    gender = "m"

    try:
        fetch_chart_requests(year, month, day, hour, gender)
    except Exception as e:
        print(f"⚠️ 發生錯誤：{e}")
