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

def _soup_from_bytes(content: bytes) -> BeautifulSoup:
    """
    以 bytes 建立 BeautifulSoup（讓它依 <meta charset> 自動判斷），
    若仍有亂碼，改用 big5 / cp950 備援。
    """
    # 先讓 BS 依內容/標頭自動判斷（多半正確）
    soup = BeautifulSoup(content, "lxml")
    # 簡單檢查是否明顯亂碼（常見 'å', 'ç', 'é' 大量出現）
    txt = soup.get_text()[:200]
    if txt.count("å") + txt.count("ç") + txt.count("é") > 5:
        # 再試 big5 / cp950
        for enc in ("big5-hkscs", "cp950", "big5"):
            try:
                soup = BeautifulSoup(content.decode(enc, errors="ignore"), "lxml")
                t2 = soup.get_text()[:200]
                if t2.count("å") + t2.count("ç") + t2.count("é") <= 1:
                    break
            except Exception:
                continue
    return soup

def _pick_select_name(soup, select_id, fallback_name):
    """從 select 的 id 找到對應的 name，若沒有就用預設名稱。"""
    tag = soup.find("select", id=select_id)
    if tag and tag.get("name"):
        return tag["name"]
    # 再嘗試以 placeholder/fallback 查找
    alt = soup.find("select", {"name": fallback_name})
    if alt and alt.get("name"):
        return alt["name"]
    return fallback_name

def _pick_radio_value(soup, input_id, default_value):
    """從 radio input 取實際 value 屬性，若沒有就用預設值。"""
    tag = soup.find("input", id=input_id)
    if tag and tag.get("value"):
        return tag["value"]
    # 如果找不到該 id，就挑選同 name 群組的任一 value 作為備援
    # 常見 name：Sex、sex 等
    for name_guess in ("Sex", "sex", "gender"):
        group = soup.find_all("input", {"type": "radio", "name": name_guess})
        if group:
            # 優先挑有 "Male"/"男" 關聯的值
            for g in group:
                v = (g.get("value") or "").strip()
                if v and (v.lower() in ("male", "m") or "男" in v):
                    return v
            # 否則就回傳第一個
            v = (group[0].get("value") or default_value)
            return v
    return default_value

def _find_main_table(soup: BeautifulSoup):
    """尋找包含命盤主要內容的表格：以『命宮』為主關鍵，正則放寬，並有次要關鍵備援。"""
    tables = soup.find_all("table")
    pattern = re.compile(r"命\s*宮")
    for t in tables:
        text = t.get_text(" ", strip=True)
        if pattern.search(text):
            return t
    # 備援：找含「紫微」且欄位很多的表格
    candidates = []
    for t in tables:
        text = t.get_text(" ", strip=True)
        if ("紫微" in text or "身宮" in text or "田宅" in text or "兄弟" in text) and len(t.find_all("td")) >= 12:
            candidates.append((len(t.find_all("td")), t))
    if candidates:
        candidates.sort(reverse=True)  # 取 td 最多者
        return candidates[0][1]
    return None

def fetch_chart_http(year, month, day, hour, gender):
    """
    以 requests 模擬表單提交，取得命盤主表格文字（不使用 Selenium/Chrome）
    """
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    })

    # 1) GET 表單（用 bytes 解析，避免亂碼）
    r = s.get(FORM_URL, timeout=20)
    r.raise_for_status()
    soup = _soup_from_bytes(r.content)

    form = soup.find("form")
    if not form:
        snippet = soup.get_text(" ", strip=True)[:400]
        raise RuntimeError(f"找不到命盤輸入表單。頁面片段：{snippet}")

    action = form.get("action") or FORM_URL
    post_url = urljoin(FORM_URL, action)

    payload = {}

    # 嘗試取得實際的 name
    name_year  = (form.find("input", {"name": "Year"}) or {}).get("name", "Year")
    name_month = _pick_select_name(form, "bMonth", "Month")
    name_day   = _pick_select_name(form, "bDay",   "Day")
    name_hour  = _pick_select_name(form, "bHour",  "Hour")

    # radio 群組的 name（Sex/sex/gender 等）
    radio_name = None
    for nm in ("Sex", "sex", "gender"):
        if form.find("input", {"type": "radio", "name": nm}):
            radio_name = nm
            break
    if not radio_name:
        radio_name = (form.find("input", {"name": "Sex"}) or {}).get("name", "Sex")

    male_value   = _pick_radio_value(form, "bMale",   "Male")
    female_value = _pick_radio_value(form, "bFemale", "Female")

    payload[name_year]  = str(year)
    payload[name_month] = str(int(month))
    payload[name_day]   = str(int(day))
    payload[name_hour]  = str(int(hour))
    payload[radio_name] = male_value if str(gender).lower().startswith("m") else female_value

    # 附帶 hidden 欄位（避免伺服器校驗失敗）
    for hid in form.find_all("input", {"type": "hidden"}):
        name = hid.get("name")
        val  = hid.get("value", "")
        if name and name not in payload:
            payload[name] = val

    # 2) POST 送出
    r2 = s.post(post_url, data=payload, headers={"Referer": FORM_URL}, timeout=30)
    r2.raise_for_status()
    soup2 = _soup_from_bytes(r2.content)

    # 3) 找主表格
    main_table = _find_main_table(soup2)
    if not main_table:
        snippet = soup2.get_text(" ", strip=True)[:400]
        raise RuntimeError(f"找不到命盤主表格，可能網站結構變更或輸入無效。頁面片段：{snippet}")

    # 4) 萃取表格文字
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

            # ★ 使用 HTTP 直連版
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
                "（此版本不使用 Chrome/Selenium；若仍失敗，多半為網站欄位或結構更新，請將此錯誤訊息貼回協助調整）</p>"
            )

    return render_template("index.html", result_html=result_html, raw_input=raw_input, inputs=user_inputs)

# ---------------------- 啟動伺服器 ----------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
