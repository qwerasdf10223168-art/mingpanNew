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

    # 判斷是否為 Render 環境 (透過檢查 CHROME_BIN 環境變數)
    IS_RENDER = os.getenv("CHROME_BIN") is not None
    
    options = Options()
    service = None

    if IS_RENDER:
        # === Render 環境設定（加強版） ===
        # 建議在 render.yaml 設成：
        # CHROME_BIN=/usr/bin/chromium
        # CHROMEDRIVER_PATH=/usr/bin/chromedriver
        chrome_path = os.getenv("CHROME_BIN", "/usr/bin/chromium")
        driver_path = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")
        
        if not os.path.exists(driver_path):
            raise FileNotFoundError("Render 環境找不到 chromedriver，請檢查 render.yaml 安裝與路徑設定。")

        # 準備乾淨可寫的暫存資料夾（避免權限或 /dev/shm 問題）
        TMP_BASE = "/tmp"
        UD = os.path.join(TMP_BASE, "chrome-user-data")
        DP = os.path.join(TMP_BASE, "chrome-data")
        DC = os.path.join(TMP_BASE, "chrome-cache")
        os.makedirs(UD, exist_ok=True)
        os.makedirs(DP, exist_ok=True)
        os.makedirs(DC, exist_ok=True)

        # Headless/容器相容旗標
        options.binary_location = chrome_path
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--window-size=1280,800")
        options.add_argument("--disable-infobars")
        options.add_argument("--no-first-run")
        options.add_argument("--no-zygote")
        options.add_argument("--single-process")
        options.add_argument("--remote-debugging-port=9222")
        options.add_argument(f"--user-data-dir={UD}")
        options.add_argument(f"--data-path={DP}")
        options.add_argument(f"--disk-cache-dir={DC}")
        options.page_load_strategy = "eager"

        # 讓 ChromeDriver 輸出詳細 log，方便頁面上回傳尾端內容排錯
        log_file = os.path.join(TMP_BASE, "chromedriver.log")
        try:
            service = Service(driver_path, log_output=log_file)
        except TypeError:
            # 舊版 selenium 無 log_output 參數時退回預設
            service = Service(driver_path)

    else:
        # === 本地環境設定 - 強化尋找邏輯 ===
        local_driver_path = os.path.join(os.getcwd(), 'chromedriver')
        if os.name == 'nt' and not os.path.exists(local_driver_path):  # Windows 檢查 .exe
            local_driver_path = os.path.join(os.getcwd(), 'chromedriver.exe')
        
        explicit_path_found = os.path.exists(local_driver_path)

        if explicit_path_found:
            service = Service(local_driver_path)
            print(f"DEBUG: 本地環境，使用專案根目錄的 ChromeDriver: {local_driver_path}")
        else:
            # 退而求其次，嘗試讓 Service() 用 PATH
            try:
                service = Service()
                print("DEBUG: 本地環境，使用 PATH 環境變數中的 ChromeDriver。")
            except Exception as e:
                raise FileNotFoundError(
                    f"本地環境找不到 chromedriver。請確認已下載對應版本的 chromedriver "
                    f"並放置在系統 PATH 或本專案的根目錄。原始錯誤: {e}"
                )
        
        # 本地除錯可見視窗（若未明確找到路徑且用 PATH）
        if not explicit_path_found:
            options.add_experimental_option("detach", True)
        options.page_load_strategy = "eager"

    # === Driver 建立：優先使用 Selenium Manager，自動解決版本相容 ===
    try:
        driver = webdriver.Chrome(options=options)
    except Exception as e1:
        if service is not None:
            driver = webdriver.Chrome(service=service, options=options)
        else:
            # 沒有可用的 service 就把原始錯誤丟出
            raise e1

    try:
        driver.set_page_load_timeout(25)
        driver.get("https://fate.windada.com/cgi-bin/fate")

        # 等待網頁元素載入
        WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.NAME, "Sex")))

        # 填寫表單
        if gender.lower().startswith("m"):
            driver.find_element(By.ID, "bMale").click()
        else:
            driver.find_element(By.ID, "bFemale").click()

        driver.find_element(By.NAME, "Year").send_keys(str(year))
        Select(driver.find_element(By.ID, "bMonth")).select_by_value(str(month))
        Select(driver.find_element(By.ID, "bDay")).select_by_value(str(day))
        Select(driver.find_element(By.ID, "bHour")).select_by_value(str(hour))
        
        # 提交表單
        driver.find_element(By.CSS_SELECTOR, 'input[type="submit"]').click()

        # 等待結果表格出現
        WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.TAG_NAME, "table")))

        tables = driver.find_elements(By.TAG_NAME, "table")
        main_table = None
        for t in tables:
            # 判斷包含「命宮」關鍵字的表格為主表格
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
            # 清理開頭的編號 (e.g., "1. " or "2. ")
            txt = re.sub(r'^\d+\.\s*', '', txt)
            chart_lines.append(txt)

        chart_text = "\n\n".join(chart_lines)
        return chart_text

    finally:
        if driver:
            driver.quit()


# ---------------------- Flask 主邏輯 ----------------------
@app.route("/", methods=["GET", "POST"])
def home():
    result_html = ""
    raw_input = ""
    # 預設值與 index.html 中的預設值保持一致
    user_inputs = {"year": 1990, "month": 1, "day": 1, "hour": 0, "gender": "m", "cyear": 2025}

    if request.method == "POST":
        try:
            # 從表單獲取用戶輸入
            user_inputs["year"] = int(request.form.get("year", 1990))
            user_inputs["month"] = int(request.form.get("month", 1))
            user_inputs["day"] = int(request.form.get("day", 1))
            user_inputs["hour"] = int(request.form.get("hour", 0))
            user_inputs["gender"] = request.form.get("gender", "m")
            user_inputs["cyear"] = int(request.form.get("cyear", 2025))

            # 執行爬蟲
            raw_input = fetch_chart_selenium(
                user_inputs["year"],
                user_inputs["month"],
                user_inputs["day"],
                user_inputs["hour"],
                user_inputs["gender"]
            )

            # 執行命盤分析
            mp.CYEAR = user_inputs["cyear"]

            data, col_order, year_stem = mp.parse_chart(raw_input)
            md = mp.render_markdown_table_v7(data, col_order, year_stem, raw_input)
            result_html = markdown.markdown(md, extensions=["tables"])

        except Exception as e:
            # 捕獲所有錯誤並回傳紅字訊息給用戶，同時附上 ChromeDriver log 尾端
            print(f"ERROR: {e}")

            # 讀取 /tmp/chromedriver.log 尾端 200 行便於排錯（若檔案存在）
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
                "請確認 Render 環境的 chromium/chromedriver 路徑及 headless 旗標；"
                "若仍失敗，請提供下方 ChromeDriver 日誌尾端以利排錯。</p>"
                f"<pre style='white-space:pre-wrap; font-size:12px; color:#ccc;'>{safe_tail}</pre>"
            )

    # 渲染結果頁面
    return render_template("index.html", result_html=result_html, raw_input=raw_input, inputs=user_inputs)


# ---------------------- 啟動伺服器 ----------------------
if __name__ == "__main__":
    # 本地執行時，使用 0.0.0.0 確保外部連線 (可選)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
