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
        # === Render 環境設定 (保持不變) ===
        chrome_path = os.getenv("CHROME_BIN", "/usr/bin/chromium-browser")
        driver_path = os.getenv("CHROMEDRIVER_PATH", "/usr/lib/chromium-browser/chromedriver")
        
        if not os.path.exists(driver_path):
            raise FileNotFoundError("Render 環境找不到 chromedriver，請檢查 render.yaml 安裝狀態。")

        # Render 必須設定 binary_location 並使用 headless 模式
        options.binary_location = chrome_path
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--window-size=1280,800")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.page_load_strategy = "eager"

        service = Service(driver_path)

    else:
        # === 本地環境設定 - 強化尋找邏輯 ===
        # 1. 嘗試在當前目錄尋找 (最符合使用者操作)
        local_driver_path = os.path.join(os.getcwd(), 'chromedriver')
        if os.name == 'nt' and not os.path.exists(local_driver_path):  # Windows 檢查 .exe
            local_driver_path = os.path.join(os.getcwd(), 'chromedriver.exe')
        
        explicit_path_found = os.path.exists(local_driver_path)

        if explicit_path_found:
            service = Service(local_driver_path)
            print(f"DEBUG: 本地環境，使用專案根目錄的 ChromeDriver: {local_driver_path}")
        else:
            # 2. 退而求其次，嘗試讓 Service() 自動尋找 (PATH)
            try:
                service = Service()
                print("DEBUG: 本地環境，使用 PATH 環境變數中的 ChromeDriver。")
            except Exception as e:
                # 如果本地執行失敗，提供明確的指導
                raise FileNotFoundError(
                    f"本地環境找不到 chromedriver。請確認已下載對應版本的 chromedriver "
                    f"並放置在系統 PATH 或本專案的根目錄。原始錯誤: {e}"
                )
        
        # 本地除錯：不使用 Headless 模式，讓瀏覽器可見
        # 僅在未明確找到路徑且 Service() 成功時，允許它使用預設的 Chrome
        if not explicit_path_found:
            options.add_experimental_option("detach", True)  # 避免程式結束就關閉
        options.page_load_strategy = "eager"

    # === Driver 建立：優先使用 Selenium Manager，自動解決版本相容 ===
    # 先嘗試 webdriver.Chrome(options=options)（需要 Selenium >= 4.6）
    # 若該環境無法使用，才用前面準備好的 Service(...) 作為後備方案。
    try:
        driver = webdriver.Chrome(options=options)
    except Exception as e1:
        if service is not None:
            driver = webdriver.Chrome(service=service, options=options)
        else:
            # 沒有可用的 service 就把原始錯誤丟出，讓前端顯示
            raise e1

    try:
        driver.set_page_load_timeout(25)
        driver.get("https://fate.windada.com/cgi-bin/fate")

        # 等待網頁元素載入
        WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.NAME, "Sex")))

        # 填寫表單
        # 注意: 確保您的瀏覽器版本與 chromedriver 版本相符（Selenium Manager 會自動處理）
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
        # 僅在成功運行後退出 Driver
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
            # 捕獲所有錯誤並回傳紅字訊息給用戶
            print(f"ERROR: {e}")
            # 注意：這裡將錯誤訊息完整顯示出來，讓用戶知道問題所在
            result_html = (
                "<p style='color:red; font-weight: bold;'>發生錯誤：無法生成命盤</p>"
                f"<p style='color:orange;'>原因：{e}</p>"
                "<p style='color:lightgray; font-size: small;'>請檢查您的出生資訊是否有效，或確認 ChromeDriver/Chrome 版本是否相符。</p>"
            )

    # 渲染結果頁面
    return render_template("index.html", result_html=result_html, raw_input=raw_input, inputs=user_inputs)


# ---------------------- 啟動伺服器 ----------------------
if __name__ == "__main__":
    # 本地執行時，使用 0.0.0.0 確保外部連線 (可選)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
