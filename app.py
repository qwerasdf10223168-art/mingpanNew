# -*- coding: utf-8 -*-
from flask import Flask, render_template, request
import mingpan_logic as mp
import requests
from bs4 import BeautifulSoup
import re, html, io, os, contextlib
from typing import Optional, List

app = Flask(__name__)
FORM_URL = "https://fate.windada.com/cgi-bin/fate"

# ---------------------------
# 解碼
# ---------------------------
def decode_html(content: bytes) -> BeautifulSoup:
    try:
        soup = BeautifulSoup(content, "lxml")
        txt = soup.get_text()[:200]
        if txt.count("å") + txt.count("ç") + txt.count("é") > 5:
            soup = BeautifulSoup(content.decode("big5", errors="ignore"), "lxml")
    except Exception:
        try:
            soup = BeautifulSoup(content.decode("utf-8", errors="ignore"), "lxml")
        except Exception:
            soup = BeautifulSoup(content.decode("big5", errors="ignore"), "lxml")
    return soup

# ---------------------------
# 找主表
# ---------------------------
TYPICAL_PALACE_KEYWORDS = ["命宮","兄弟","夫妻","子女","財帛","疾厄","遷移","交友","事業","田宅","福德","父母","陽曆"]
def find_main_table(soup: BeautifulSoup):
    candidates = []
    for t in soup.find_all("table"):
        txt = t.get_text(" ", strip=True)
        if any(k in txt for k in TYPICAL_PALACE_KEYWORDS):
            return t
        if len(t.find_all("td")) >= 12:
            candidates.append(t)
    return candidates[0] if candidates else None

# ---------------------------
# 解析中央資訊（陽曆/農曆/干支/五行局/四化/命主身主）
# ---------------------------
def parse_center_block(td_html: str) -> Optional[str]:
    text = td_html.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    text = BeautifulSoup(text, "lxml").get_text("\n")
    if not any(k in text for k in ["陽曆", "農曆", "干支", "五行局", "生年四化", "命主", "身主"]):
        return None
    lines = [ln.strip() for ln in re.split(r"[\r\n]+", text) if ln.strip()]
    return "\n".join(lines) if lines else None

# ---------------------------
# 宮位格解析
# ---------------------------
GZ = "甲乙丙丁戊己庚辛壬癸"
DZ = "子丑寅卯辰巳午未申酉戌亥"

def td_html_to_text(td) -> str:
    raw = td.decode_contents()
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    return BeautifulSoup(raw, "lxml").get_text("\n")

def build_header(full_text: str) -> str:
    """
    盡量輸出『干支【某某宮】』，若找不到干支則只輸出【某某宮】。
    """
    # 同行：丁巳【事業宮】
    m = re.search(r"([%s][%s])?\s*【([^】]+宮)】" % (GZ, DZ), full_text)
    if m:
        gz = (m.group(1) or "").strip()
        pal = m.group(2).strip()
        return f"{gz}【{pal}】" if gz else f"【{pal}】"
    # 可能『丁巳』與『【事業宮】』分行
    mgz = re.search(r"([%s][%s])" % (GZ, DZ), full_text)
    mpal = re.search(r"【([^】]+宮)】", full_text)
    if mpal:
        pal = mpal.group(1)
        if mgz:
            return f"{mgz.group(1)}【{pal}】"
        return f"【{pal}】"
    # 退路：第一行含『宮』
    first_line = full_text.splitlines()[0].strip()
    if "宮" in first_line and "【" not in first_line:
        return f"【{first_line}】"
    return first_line

def parse_palace_block(td) -> Optional[str]:
    # 先看是不是中央資訊
    center_try = parse_center_block(td.decode_contents())
    if center_try:
        return center_try

    full = td_html_to_text(td)
    if not full.strip():
        return None

    header = build_header(full)

    # ---- 抽「大限」「小限」（跨行也能抓），並從文本中刪除，避免落入星曜 ----
    # 大限：大限: 44-53 / 大限 44－53
    m_da = re.search(r"大\s*限[:：]?\s*(\d{1,3})\s*[-~－—～]\s*(\d{1,3})", full, flags=re.S)
    da_line = f"大限:{m_da.group(1)}-{m_da.group(2)}" if m_da else "大限:"
    if m_da:
        full = full.replace(m_da.group(0), "")

    # 小限：小限: 後面可跨行接一串數字
    m_xiao = re.search(r"小\s*限[:：]?\s*([0-9\s,，、\n\r]+)", full, flags=re.S)
    if m_xiao:
        nums = re.findall(r"\d{1,3}", m_xiao.group(1))
        xiao_line = "小限:" + (" ".join(nums) if nums else "")
        full = full.replace(m_xiao.group(0), "")
    else:
        xiao_line = "小限:"

    # ---- 剩餘當星曜：清掉空行與左右標點，改用半形逗號連接 ----
    rest_lines = [ln.strip() for ln in full.splitlines() if ln.strip()]
    # 去掉像「【事業宮】」「丁巳」等標題資訊殘留
    rest_lines = [ln for ln in rest_lines if "宮" not in ln or "【" not in ln]
    rest_lines = [ln for ln in rest_lines if not re.fullmatch(r"[%s][%s]" % (GZ, DZ), ln)]
    # 清尾逗號與多餘頓號
    stars = [re.sub(r"[，、]+\s*$", "", ln) for ln in rest_lines]
    # 濾掉明顯非星曜的殘字（大限/小限被清掉後仍可能殘留單獨冒號）
    stars = [s for s in stars if s and s not in (":", "：", "大限", "小限")]

    star_line = ",".join(stars).strip(", ")

    return f"{header}\n{da_line}\n{xiao_line}\n{star_line}"

# ---------------------------
# 送表單抓取（修正性別值）
# ---------------------------
COMMON_NAME_MAP = {
    "year":  ["Year", "year", "y", "byear", "birthYear", "birth_year", "yy"],
    "month": ["Month", "month", "m", "bmonth", "birthMonth"],
    "day":   ["Day", "day", "d", "bday", "birthDay"],
    "hour":  ["Hour", "hour", "h", "bhour", "time", "時"],
    "sex":   ["Sex", "sex", "gender", "Gender"],
}

def choose_field_name(cands: List[str], names: set) -> Optional[str]:
    for n in cands:
        if n in names:
            return n
    return None

def fetch_chart(year, month, day, hour, gender):
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    r = s.get(FORM_URL, timeout=20)
    soup = decode_html(r.content)
    form = soup.find("form")
    if not form:
        txt = soup.get_text()[:800]
        raise RuntimeError("找不到命盤表單：\n" + txt)

    post_url = form.get("action") or FORM_URL
    post_url = requests.compat.urljoin(FORM_URL, post_url)

    payload = {}
    form_names = set()

    for inp in form.find_all(["input","textarea"]):
        n = inp.get("name")
        if not n: continue
        form_names.add(n)
        t = (inp.get("type") or "").lower()
        v = inp.get("value", "")
        if t in ("radio","checkbox"):
            if inp.has_attr("checked"):
                payload[n] = v
        else:
            payload[n] = v

    # select 預設值
    for sel in form.find_all("select"):
        n = sel.get("name")
        if not n: continue
        form_names.add(n)
        chosen = None
        for opt in sel.find_all("option"):
            if opt.has_attr("selected"):
                chosen = opt.get("value", opt.text)
                break
        if chosen is None:
            first = sel.find("option")
            chosen = first.get("value", first.text) if first else ""
        payload[n] = chosen

    # 對應欄位名
    yname = choose_field_name(COMMON_NAME_MAP["year"], form_names)  or "Year"
    mname = choose_field_name(COMMON_NAME_MAP["month"], form_names) or "Month"
    dname = choose_field_name(COMMON_NAME_MAP["day"], form_names)   or "Day"
    hname = choose_field_name(COMMON_NAME_MAP["hour"], form_names)  or "Hour"
    sname = choose_field_name(COMMON_NAME_MAP["sex"], form_names)   or "Sex"

    payload[yname] = str(year)
    payload[mname] = str(month)
    payload[dname] = str(day)
    payload[hname] = str(hour)

       # ---- 性別（依使用者選擇 m/f 精準帶值）----
    gender_str = str(gender).strip().lower()
    want_female = gender_str.startswith(("f", "女"))  # True=女, False=男
    sex_value = None

    # 先找 select[name=sname]
    sel = form.find("select", attrs={"name": sname}) if sname else None
    if sel:
        # 先比對 option 顯示文字（含「男」「女」），再比對 value（M/F/1/0）
        for opt in sel.find_all("option"):
            label = (opt.get_text() or "").strip()
            val = (opt.get("value") or "").strip()
            if want_female and ("女" in label or val.lower() in ("f","female","0")):
                sex_value = val if val != "" else label
                break
            if (not want_female) and ("男" in label or val.lower() in ("m","male","1")):
                sex_value = val if val != "" else label
                break
        # 若還沒選到，再純看 value 重試一次
        if sex_value is None:
            for opt in sel.find_all("option"):
                val = (opt.get("value") or "").strip().lower()
                if want_female and val in ("f","female","0"):
                    sex_value = (opt.get("value") or "").strip()
                    break
                if (not want_female) and val in ("m","male","1"):
                    sex_value = (opt.get("value") or "").strip()
                    break

    # 若不是 select，就找 radio[name=sname]
    if sex_value is None and sname:
        radios = form.find_all("input", attrs={"name": sname, "type": "radio"})
        male_val = None
        female_val = None
        for rd in radios:
            val = (rd.get("value") or "").strip()
            vlow = val.lower()
            # 嘗試讀取緊鄰文字（有些頁面 label 在旁邊）
            label_text = ""
            sib = rd.next_sibling
            if isinstance(sib, str):
                label_text = sib.strip()
            # 標記男女候選
            if ("男" in label_text) or (vlow in ("m","male","1")):
                male_val = val
            if ("女" in label_text) or (vlow in ("f","female","0")):
                female_val = val
        if want_female and female_val is not None:
            sex_value = female_val
        if (not want_female) and male_val is not None:
            sex_value = male_val

    # 最後保底：多數站 1=男、0=女；若不同也常可接受 M/F
    if sex_value is None:
        sex_value = "0" if want_female else "1"

    payload[sname] = sex_value

    r2 = s.post(post_url, data=payload, timeout=25)
    soup2 = decode_html(r2.content)
    table = find_main_table(soup2)
    if not table:
        txt = soup2.get_text()[:800]
        raise RuntimeError("找不到命盤主表格：\n" + txt)

    blocks = []
    for td in table.find_all("td"):
        block = parse_palace_block(td)
        if block:
            blocks.append(block)

    return "\n\n".join(blocks)

# ---------------------------
# Flask UI
# ---------------------------
@app.route("/", methods=["GET", "POST"])
def home():
    output_html = ""
    raw_text = ""
    user_inputs = {"year": 1990, "month": 2, "day": 1, "hour": 0, "gender": "m", "cyear": 2026}

    if request.method == "POST":
        try:
            user_inputs["year"]   = int(request.form.get("year", 1990))
            user_inputs["month"]  = int(request.form.get("month", 1))
            user_inputs["day"]    = int(request.form.get("day", 1))
            user_inputs["hour"]   = int(request.form.get("hour", 0))
            user_inputs["gender"] = request.form.get("gender", "m")
            user_inputs["cyear"]  = int(request.form.get("cyear", 2026))

            raw_text = fetch_chart(
                user_inputs["year"], user_inputs["month"],
                user_inputs["day"], user_inputs["hour"], user_inputs["gender"]
            )

            mp.CYEAR = user_inputs["cyear"]
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                report = mp.run_report(raw_text)
            debug = buf.getvalue().strip()
            full = (debug + "\n\n" + report) if debug else report

            output_html = (
                "<pre style='white-space:pre-wrap;font-size:14px;line-height:1.6;'>"
                + html.escape(full) + "</pre>"
            )

        except Exception as e:
            output_html = f"<p style='color:red;'>發生錯誤：{html.escape(str(e))}</p>"

    return render_template("index.html", result_html=output_html, raw_input=raw_text, inputs=user_inputs)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
