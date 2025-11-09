from flask import Flask, render_template, request
import mingpan_logic as mp
import markdown
import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

app = Flask(__name__)

FORM_URL = "https://fate.windada.com/cgi-bin/fate"

def _pick_select_name(soup, select_id, fallback_name):
    """從 select 的 id 找到對應的 name，若沒有就用預設名稱。"""
    tag = soup.find("select", id=select_id)
    if tag and tag.get("name"):
        return tag["name"]
    return fallback_name

def _pick_radio_value(soup, input_id, default_value):
    """從 radio input 取實際 value 屬性，若沒有就用預設值。"""
    tag = soup.find("input", id=input_id)
    if tag and tag.get("value"):
        return tag["value"]
    return default_value

def fetch_chart_http(year, month, day, hour, gender):
    """
    以 requests 模擬表單提交，取得命盤主表格文字（不需要 Selenium/Chrome）
    """
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    })

    # 1) 先 GET 取得表單，抓真正的欄位 name 與必要 hidden 欄位
    resp = s.get(FORM_URL, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    form = soup.find("form")
    if not form:
        raise RuntimeError("找不到命盤輸入表單")

    action = form.get("action") or FORM_URL
    post_url = urljoin(FORM_URL, action)

    payload = {}

    # 抓出 select 的實際 name（網站可能不是 Month/Day/Hour 的固定字串）
    name_year  = (form.find("input", {"name": "Year"}) or {}).get("name", "Year")
    name_month = _pick_select_name(form, "bMonth", "Month")
    name_day   = _pick_select_name(form, "bDay",   "Day")
    name_hour  = _pick_select_name(form, "bHour",  "Hour")
    name_sex   = (form.find("input", {"name": "Sex"}) or {}).get("name", "Sex")  # radio name

    # radio 實際的 value（有些站台不是固定 Male/Female，而是 "1"/"0" 或中文）
    male_value   = _pick_radio_value(form, "bMale",   "Male")
    female_value = _pick_radio_value(form, "bFemale", "Female")

    payload[name_year]  = str(year)
    payload[name_month] = str(int(month))  # 1-12
    payload[name_day]   = str(int(day))    # 1-31
    payload[name_hour]  = str(int(hour))   # 0-23
    payload[name_sex]   = male_value if str(gender).lower().startswith("m") else female_value

    # 也把 form 裡所有 hidden 欄位帶上（避免伺服器檢查失敗）
    for hid in form.find_all("input", {"type": "hidden"}):
        name = hid.get("name")
        val  = hid.get("value", "")
        if name and name not in payload:
            payload[name] = val

    # 2) POST 送出表單
    resp2 = s.post(post_url, data=payload, timeout=30)
    resp2.raise_for_status()
    soup2 = BeautifulSoup(resp2.text, "lxml")

    # 3) 尋找包含「命宮」的主表格，抽出所有 <td> 的文字
    tables = soup2.find_all("table")
    main_table = None
    for t in tables:
        if "命宮" in t.get_text(" ", strip=True):
            main_table = t
            break

    if not main_table:
        # 將回應片段附上，便於 debug
        snippet = soup2.get_text(" ", strip=True)[:400]
        raise RuntimeError(f"找不到命盤主表格，可能網站結構變更或輸入無效。頁面片段：{snippet}")

    cells = main_table.find_all("td")
    chart_lines = []
    for c in cells:
        txt = c.get_text("\n", strip=True)
        if not txt:
            continue
        txt = re.sub(r'^\d+\.\s*', '', txt)  # 清掉 "1. " 這類編號
        chart_lines.append(txt)

    return "\n\n".join(chart_lines)

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

            # ★ 以 HTTP 模擬表單方式抓資料（不再使用 Selenium/Chrome）
            raw_input = fetch_chart_http(
                user_inputs["year"],
                user_inputs["month"],
                user_inputs["day"],
                user_inputs["hour"],
                user_inputs["gender"]
            )

            # 命盤分析
            mp.CYEAR = user_inputs["cyear"]
            data, col_order, year_stem = mp.parse_chart(raw_input)
            md = mp.render_markdown_table_v7(data, col_order, year_stem, raw_input)
            result_html = markdown.markdown(md, extensions=["tables"])

        except Exception as e:
            print(f"ERROR: {e}")
            result_html = (
                "<p style='color:red; font-weight: bold;'>發生錯誤：無法生成命盤</p>"
                f"<p style='color:orange;'>原因：{e}</p>"
                "<p style='color:lightgray; font-size: small;'>"
                "（此版本不使用 Chrome/Selenium，若仍失敗，多半為網站欄位或結構更新，請回報錯誤訊息）</p>"
            )

    return render_template("index.html", result_html=result_html, raw_input=raw_input, inputs=user_inputs)

# ---------------------- 啟動伺服器 ----------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
