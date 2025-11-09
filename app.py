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
    Render/本地 相容版：智慧判斷環境並啟動 Chromium/ChromeDriver
    """

    IS_RENDER = os.getenv("CHROME_BIN") is not None
    options = Options()
    service = None

    if IS_RENDER:
        # === Render 環境（Chrome for Testing + 對應 Driver）===
        chrome_path = os.getenv("CHROME_BIN", "/opt/chrome/chrome")
        driver_path = os.getenv("CHROMEDRIVER_PATH", "/opt/chromedriver/chromedriver")

        if not (os.path.exists(chrome_path) and os.path.exists(driver_path)):
            raise FileNotFoundError(
                f"Render 找不到 Chrome/Driver：CHROME_BIN={chrome_path}, CHROMEDRIVER_PATH={driver_path}"
            )

        # /tmp 可寫資料夾
        TMP_BASE = "/tmp"
        UD = os.path.join(TMP_BASE, "chrome-user-data")
        DP = os.path.join(TMP_BASE, "chrome-data")
        DC = os.path.join(TMP_BASE, "chrome-cache")
        for d in (UD, DP, DC):
            os.makedirs(d, exist_ok=True)

        # Headless 容器相容旗標（去掉 single-process；補 setuid sandbox 與 remote-allow-origins）
        options.binary_location = chrome_path
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--disable-infobars")
        options.add_argument("--no-first-run")
        options.add_argument("--no-zygote")
        options.add_argument("--remote-allow-origins=*")
        options.add_argument("--remote-debugging-port=9222")
        options.add_argument("--window-size=1280,800")
        options.add_argument(f"--user-data-dir={UD}")
        options.add_argument(f"--data-path={DP}")
        options.add_argument(f"--disk-cache-dir={DC}")
        options.page_load_strategy = "eager"

        # 只用指定的 chromedriver（避免 Selenium Manager 自行挑版本）
        log_file = os.path.join(TMP_BASE, "chromedriver.log")
        try:
            service = Service(driver_path, log_output=log_file)
        except TypeError:
            service = Service(driver_path)

        # 在 Render 上直接用 service 啟動，避免去嘗試 Manager
        driver = webdriver.Chrome(service=service, options=options)

    else:
        # === 本地環境（保留你的原有行為）===
        local_driver_path = os.path.join(os.getcwd(), 'chromedriver')
        if os.name == 'nt' and not os.path.exists(local_driver_path):
            local_driver_path = os.path.join(os.getcwd(), 'chromedriver.exe')
        explicit_path_found = os.path.exists(local_driver_path)

        if explicit_path_found:
            service = Service(local_driver_path)
            print(f"DEBUG: 本地環境，使用專案根目錄的 ChromeDriver: {local_driver_path}")
        else:
            try:
                service = Service()  # 使用 PATH
                print("DEBUG: 本地環境，使用 PATH 的 ChromeDriver。")
            except Exception as e:
                raise FileNotFoundError(
                    f"本地找不到 chromedriver。請將對應版本放到 PATH 或專案根目錄。原始錯誤: {e}"
                )
        options.page_load_strategy = "eager"
        if not explicit_path_found:
            options.add_experimental_option("detach", True)

        # 本地先試 Manager，失敗再 fallback
        try:
            driver = webdriver.Chrome(options=options)
        except Exception:
            driver = webdriver.Chrome(service=service, options=options)

    # ====== 實際爬取 ======
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
            raise Exception("爬蟲失敗：找不到命盤主表格。可能網頁結構已改變或輸入無效。")

        cells = main_table.find_elements(By.TAG_NAME, "td")
        chart_lines = []
        for c in cells:
            txt = c.text.strip()
            if not txt:
                continue
            txt = re.sub(r'^\d+\.\s*', '', txt)
            chart_lines.append(txt)

        return "\n\n".join(chart_lines)

    finally:
        try:
            driver.quit()
        except Exception:
            pass

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
                user_inputs["year"], user_inputs["month"], user_inputs["day"],
                user_inputs["hour"], user_inputs["gender"]
            )

            mp.CYEAR = user_inputs["cyear"]
            data, col_order, year_stem = mp.parse_chart(raw_input)
            md = mp.render_markdown_table_v7(data, col_order, year_stem, raw_input)
            result_html = markdown.markdown(md, extensions=["tables"])

        except Exception as e:
            print(f"ERROR: {e}")
            # 讀取 /tmp/chromedriver.log（Render 才會有）
            tail = ""
            try:
                with open("/tmp/chromedriver.log", "r", encoding="utf-8", errors="ignore") as f:
                    tail = "".join(f.readlines()[-200:])
            except Exception:
                pass
            safe_tail = (
                tail[:8000]
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            result_html = (
                "<p style='color:red; font-weight: bold;'>發生錯誤：無法生成命盤</p>"
                f"<p style='color:orange;'>原因：{e}</p>"
                "<p style='color:lightgray; font-size: small;'>"
                "請確認 Render 的 Chrome/Driver 路徑與相容性；若仍失敗，請提供下方 ChromeDriver 日誌尾端。</p>"
                f"<pre style='white-space:pre-wrap; font-size:12px; color:#ccc;'>{safe_tail}</pre>"
            )

    return render_template("index.html", result_html=result_html, raw_input=raw_input, inputs=user_inputs)

# ---------------------- 啟動伺服器 ----------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
