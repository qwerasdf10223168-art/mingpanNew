from flask import Flask, render_template, request
import mingpan_logic as mp
import markdown
import os
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

app = Flask(__name__)

# ---------------------- 爬蟲部分 ----------------------
def fetch_chart_selenium(year, month, day, hour, gender):
    """
    從 fate.windada.com 爬取紫微命盤文字
    Render 相容版：使用 headless Chromium（新版 Headless 模式）
    """

    # === Chrome 設定區 ===
    chrome_path = os.getenv("CHROME_BIN", "/usr/bin/chromium-browser")

    # 嘗試多個常見路徑，Render 上通常在 /usr/lib/chromium-browser/chromedriver
    possible_drivers = [
        os.getenv("CHROMEDRIVER_PATH"),
        "/usr/lib/chromium-browser/chromedriver",  # Render (Debian)
        "/usr/bin/chromedriver",                   # Linux (一般)
        ]
    
    driver_path = next((p for p in possible_drivers if p and os.path.exists(p)), None)

    if not driver_path:
        raise FileNotFoundError("找不到 chromedriver，請確認 render.yaml 是否正確安裝 chromium-driver。")


    options = Options()
    options.binary_location = chrome_path
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--window-size=1280,800")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.page_load_strategy = "eager"  # 改用較快模式，避免 Render 超時

    driver = webdriver.Chrome(service=Service(driver_path), options=options)

    try:
        driver.set_page_load_timeout(25)
        driver.get("https://fate.windada.com/cgi-bin/fate")

        WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.NAME, "Sex")))

        if gender.lower().startswith("m"):
            driver.find_element(By.ID, "bMale").click()
        else:
            driver.find_element(By.ID, "bFemale").click()

        driver.find_element(By.NAME, "Year").send_keys(str(year))
        Select(driver.find_element(By.ID, "bMonth")).select_by_value(str(month))
        Select(driver.find_element(By.ID, "bDay")).select_by_value(str(day))
        Select(driver.find_element(By.ID, "bHour")).select_by_value(str(hour))
        driver.find_element(By.CSS_SELECTOR, 'input[type="submit"]').click()

        WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.TAG_NAME, "table")))

        tables = driver.find_elements(By.TAG_NAME, "table")
        main_table = None
        for t in tables:
            if "命宮" in t.text:
                main_table = t
                break

        if not main_table:
            raise Exception("找不到命盤主表格。")

        cells = main_table.find_elements(By.TAG_NAME, "td")
        chart_lines = []
        for c in cells:
            txt = c.text.strip()
            if not txt:
                continue
            txt = re.sub(r'^\d+\.\s*', '', txt)
            chart_lines.append(txt)

        chart_text = "\n\n".join(chart_lines)
        return chart_text

    finally:
        driver.quit()


# ---------------------- Flask 主邏輯 ----------------------
@app.route("/", methods=["GET", "POST"])
def home():
    result_html = ""
    raw_input = ""
    user_inputs = {"year": 1990, "month": 1, "day": 1, "hour": 0, "gender": "m", "cyear": 2025}

    if request.method == "POST":
        try:
            user_inputs["year"] = int(request.form.get("year", 1990))
            user_inputs["month"] = int(request.form.get("month", 1))
            user_inputs["day"] = int(request.form.get("day", 1))
            user_inputs["hour"] = int(request.form.get("hour", 0))
            user_inputs["gender"] = request.form.get("gender", "m")
            user_inputs["cyear"] = int(request.form.get("cyear", 2025))

            raw_input = fetch_chart_selenium(
                user_inputs["year"],
                user_inputs["month"],
                user_inputs["day"],
                user_inputs["hour"],
                user_inputs["gender"]
            )

            mp.CYEAR = user_inputs["cyear"]

            data, col_order, year_stem = mp.parse_chart(raw_input)
            md = mp.render_markdown_table_v7(data, col_order, year_stem, raw_input)
            result_html = markdown.markdown(md, extensions=["tables"])

        except Exception as e:
            result_html = f"<p style='color:red;'>發生錯誤：{e}</p>"

    return render_template("index.html", result_html=result_html, raw_input=raw_input, inputs=user_inputs)


# ---------------------- 啟動伺服器 ----------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
