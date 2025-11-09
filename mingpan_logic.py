# -*- coding: utf-8 -*-
import re
from datetime import datetime

# ======================= 全域設定 =======================
DEBUG = True  # 預設開啟除錯
CYEAR = None  # ← 新增：統一年份來源（由 __main__ 依 TARGET_YEAR 設定）

# ===== 白名單（原版保留） =====
MAIN_STARS = ["紫微","天府","天相","天梁","武曲","七殺","破軍","廉貞","天機","太陽","太陰","巨門","天同","貪狼"]
AUX_STARS  = ["文曲","文昌","左輔","右弼"]
MINI_STARS = ["火星","鈴星","祿存","擎羊","陀螺"]  # 會把「陀羅」正規為「陀螺」

ALIASES = {"陀羅": "陀螺"}  # 同義正規

PALACE_ABBR = {
    "命宮":"命","兄弟宮":"兄","夫妻宮":"夫","子女宮":"子","財帛宮":"財","疾厄宮":"疾",
    "遷移宮":"遷","交友宮":"僕","事業宮":"官","田宅宮":"田","福德宮":"福","父母宮":"父",
}

# ===== 生年四化對照（原版保留） =====
YEAR_HUA = {
    "甲": {"祿":"廉貞","權":"破軍","科":"武曲","忌":"太陽"},
    "乙": {"祿":"天機","權":"天梁","科":"紫微","忌":"太陰"},
    "丙": {"祿":"天同","權":"天機","科":"文昌","忌":"廉貞"},
    "丁": {"祿":"太陰","權":"天同","科":"天機","忌":"巨門"},
    "戊": {"祿":"貪狼","權":"太陰","科":"右弼","忌":"天機"},
    "己": {"祿":"武曲","權":"貪狼","科":"天梁","忌":"文曲"},
    "庚": {"祿":"太陽","權":"武曲","科":"太陰","忌":"天同"},
    "辛": {"祿":"巨門","權":"太陽","科":"文曲","忌":"文昌"},
    "壬": {"祿":"天梁","權":"紫微","科":"左輔","忌":"武曲"},
    "癸": {"祿":"破軍","權":"巨門","科":"太陰","忌":"貪狼"},
}

# ===== 工具（原版保留；尾綴多重清理、不砍「星」字） =====
def normalize_token(t: str) -> str:
    """
    去同義、移除尾綴（支援多重：廟權 / 旺科 ...）
    注意：不移除結尾「星」，避免把『火星/鈴星』誤砍成『火/鈴』
    """
    t = t.strip()
    t = ALIASES.get(t, t)
    t = re.sub(r"(旺|陷|廟|地|平|權|科|祿|忌|利)+$", "", t)
    return t

def pick_whitelist(star_line: str):
    """只抽取白名單（主/輔/小），去重保序。"""
    raw = re.split(r"[,\，\s、]+", star_line.strip())
    raw = [x for x in raw if x]
    found_main, found_aux, found_mini = [], [], []
    for tok in raw:
        norm = normalize_token(tok)
        if norm in MAIN_STARS and norm not in found_main:
            found_main.append(norm)
        elif norm in AUX_STARS and norm not in found_aux:
            found_aux.append(norm)
        elif norm in MINI_STARS and norm not in found_mini:
            found_mini.append(norm)
    return found_main, found_aux, found_mini

def palace_to_abbr(palace_name: str) -> str:
    """宮名→縮寫；含『命宮-身宮』類型一律視為『命』。"""
    if "命宮" in palace_name:
        return "命"
    for full, ab in PALACE_ABBR.items():
        if full in palace_name:
            return ab
    return ""

def parse_year_stem(raw_text: str) -> str:
    """從『干支』行擷取生年天干（甲乙丙丁戊己庚辛壬癸）。"""
    m = re.search(r"干支[:：︰]\s*([甲乙丙丁戊己庚辛壬癸])[子丑寅卯辰巳午未申酉戌亥]年", raw_text)
    return m.group(1) if m else ""

# ===== 解析（原版保留） =====
def parse_chart(raw_text: str):
    """
    回傳 data, col_order, year_stem
    data = {
      col: {'palace','main'[], 'aux'[], 'mini'[], 'daxian','abbr'}
    }
    col_order = [依輸入順序的宮干支]
    year_stem = '甲'..'癸' 或 ''
    """
    block_pat = re.compile(
        r"([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])【([^】]+)】\s*"
        r"大限:([0-9]+)-([0-9]+)\s*"
        r"小限:[^\n]*\n"
        r"([^\n]+)"
    )
    data = {}
    col_order = []
    for m in re.finditer(block_pat, raw_text):
        col = m.group(1)
        palace = m.group(2)
        dx_a, dx_b = m.group(3), m.group(4)
        star_line = m.group(5)

        main, aux, mini = pick_whitelist(star_line)
        abbr = palace_to_abbr(palace)

        data[col] = {
            "palace": palace,
            "main": main,
            "aux": aux,
            "mini": [ALIASES.get(x, x) for x in mini],
            "daxian": f"{dx_a}~{dx_b}",
            "abbr": abbr,
        }
        if col not in col_order:
            col_order.append(col)

    year_stem = parse_year_stem(raw_text)
    return data, col_order, year_stem

# ===== 舊版渲染（原版保留） =====
def render_markdown_table(data: dict, col_order: list, year_stem: str = "") -> str:
    header = ["原始資料", "宮干支"] + col_order
    lines = []
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["----","---"] + ["----"]*len(col_order)) + " |")

    # 主星
    row = ["", "主星"]
    for col in col_order:
        row.append("/".join(data[col]["main"]) if data[col]["main"] else "")
    lines.append("| " + " | ".join(row) + " |")

    # 輔星
    row = ["", "輔星"]
    for col in col_order:
        row.append("/".join(data[col]["aux"]) if data[col]["aux"] else "")
    lines.append("| " + " | ".join(row) + " |")

    # 小星
    row = ["", "小星"]
    for col in col_order:
        row.append("/".join(data[col]["mini"]) if data[col]["mini"] else "")
    lines.append("| " + " | ".join(row) + " |")

    # 大限
    row = ["", "大限"]
    for col in col_order:
        row.append(data[col]["daxian"])
    lines.append("| " + " | ".join(row) + " |")

    # 本命（原版在前）
    row = ["本命", "宮位"]
    for col in col_order:
        row.append(data[col]["abbr"])
    lines.append("| " + " | ".join(row) + " |")

    # 生年四化（主/輔/小三者定位）
    if year_stem and year_stem in YEAR_HUA:
        hua_map = YEAR_HUA[year_stem]
        cell = {col: [] for col in col_order}
        for typ in ["祿","權","科","忌"]:
            star = hua_map.get(typ, "")
            if not star:
                continue
            located_cols = []
            for c in col_order:
                bucket = data.get(c, {})
                if (star in bucket.get("main", [])) or \
                   (star in bucket.get("aux",  [])) or \
                   (star in bucket.get("mini", [])):
                    located_cols.append(c)
            for c in located_cols:
                cell[c].append(f"{star}{typ}")
        row = ["", f"生年四化（{year_stem}）"]
        for col in col_order:
            row.append("/".join(cell[col]) if cell[col] else "")
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)

# ===== 舊版檢核（原版保留） =====
def quick_validate(data: dict, col_order: list, year_stem: str = ""):
    # 主星出現計數
    count = {s:0 for s in MAIN_STARS}
    for col in col_order:
        for s in data[col]["main"]:
            count[s] += 1
    missing = [s for s,c in count.items() if c == 0]
    if missing:
        print("⚠️ 以下主星未在輸入文本中出現：", "、".join(missing))
    # 大限缺失
    dx_missing = [col for col in col_order if not data[col]["daxian"]]
    if dx_missing:
        print("⚠️ 以下欄位缺大限：", "、".join(dx_missing))
    # 宮位縮寫缺失
    abbr_missing = [col for col in col_order if not data[col]["abbr"]]
    if abbr_missing:
        print("⚠️ 以下欄位無法辨識本命宮位縮寫：", "、".join(abbr_missing))
    # 生年四化存在但星未定位（主/輔/小）
    if year_stem and year_stem in YEAR_HUA:
        hua_map = YEAR_HUA[year_stem]
        not_found = []
        for typ, star in hua_map.items():
            found = any(
                (star in data[c]["main"]) or
                (star in data[c]["aux"])  or
                (star in data[c]["mini"])
                for c in col_order
            )
            if not found:
                not_found.append(f"{star}{typ}")
        if not_found:
            print("⚠️ 生年四化中以下星未定位到（含主/輔/小）：", "、".join(not_found))

# ----------------------------------------------------------------------
# ============================ 新  版  功  能（v2~v5 保留）====================
# ----------------------------------------------------------------------

# 0) 欄位標準順序（依『本命｜宮位』）：命→兄→夫→子→財→疾→遷→僕→官→田→福→父
PALACE_ORDER_CANONICAL = ["命","兄","夫","子","財","疾","遷","僕","官","田","福","父"]

# 1) 解析出生年（西元）與今年
def parse_birth_year(raw_text: str) -> int:
    m = re.search(r"陽曆[:：︰]?\s*(\d{4})年", raw_text)
    return int(m.group(1)) if m else 0

def current_year() -> int:
    return datetime.now().year

# 2) 依『本命｜宮位』重排欄位
def reorder_cols_by_palace(data: dict, col_order: list) -> list:
    buckets = {abbr: None for abbr in PALACE_ORDER_CANONICAL}
    used = set()
    for col in col_order:
        abbr = (data.get(col, {}).get("abbr") or "").strip()
        if abbr in PALACE_ORDER_CANONICAL and buckets[abbr] is None:
            buckets[abbr] = col
            used.add(col)
    ordered = [buckets[a] for a in PALACE_ORDER_CANONICAL if buckets[a]]
    tail = [c for c in col_order if c not in used]
    return ordered + tail

# 3) 找出「歲數」所在的大限欄位（含頭含尾）
def find_daxian_anchor_col(data: dict, cols: list, age: int) -> str:
    for c in cols:
        rng = data.get(c, {}).get("daxian", "")
        m = re.match(r"^\s*(\d+)\s*~\s*(\d+)\s*$", rng)
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        if a <= age <= b:
            return c
    return ""

# 3b) 容錯版（找不到就挑最近）
def safe_find_anchor_by_age(data: dict, cols: list, age: int) -> str:
    found = find_daxian_anchor_col(data, cols, age)
    if found:
        if DEBUG:
            print(f"DEBUG[DAXIAN] 歲數 {age} 命中：{found}（區間 {data[found]['daxian']}）")
        return found
    best_col, best_gap = "", 10**9
    for c in cols:
        m = re.match(r"^\s*(\d+)\s*~\s*(\d+)\s*$", data.get(c,{}).get("daxian",""))
        if not m: continue
        a,b = int(m.group(1)), int(m.group(2))
        gap = min(abs(age-a), abs(age-b)) if (age < a or age > b) else 0
        if gap < best_gap:
            best_gap, best_col = gap, c
    if DEBUG and best_col:
        print(f"DEBUG[DAXIAN] 歲數 {age} 未命中任何區間，改用最近：{best_col}（區間 {data[best_col]['daxian']}，距離={best_gap}）")
    return best_col

# 4) 依錨點建構「大限命｜宮位」一行
def build_daxian_ming_row(cols: list, data: dict, anchor_col: str) -> list:
    """
    anchor_col 標『命』，其右側依序標『兄→夫→子→財→疾→遷→僕→官→田→福→父』循環填滿。
    找不到 anchor 則全空。
    """
    if not anchor_col or anchor_col not in cols:
        return [""] * len(cols)
    labels = PALACE_ORDER_CANONICAL
    out = [""] * len(cols)
    start_idx = cols.index(anchor_col)
    for offset in range(len(cols)):
        pos = (start_idx + offset) % len(cols)
        out[pos] = labels[offset % len(labels)]
    return out

# 5) 小工具（天干 / 欄位 / 四化）
def get_stem_from_col(col: str) -> str:
    return col[0] if col and col[0] in YEAR_HUA else ""

def build_hua_cells_for_stem(stem: str, cols: list, data: dict) -> list:
    cells = {c: [] for c in cols}
    if not stem or stem not in YEAR_HUA:
        return ["" for _ in cols]
    hua_map = YEAR_HUA[stem]
    for typ in ["祿","權","科","忌"]:
        star = hua_map.get(typ, "")
        if not star: continue
        located = [c for c in cols if (star in data[c]["main"]) or (star in data[c]["aux"]) or (star in data[c]["mini"])]
        for c in located: cells[c].append(f"{star}{typ}")
    return ["/".join(cells[c]) if cells[c] else "" for c in cols]

def find_col_for_label(cols: list, ming_line: list, target_label: str) -> str:
    for i, lab in enumerate(ming_line):
        if lab == target_label:
            return cols[i]
    return ""

# 6) Debug 輔助
def debug_report_order(col_order: list, cols_reordered: list, data: dict):
    if not DEBUG: return
    pairs = [f"{i+1}.{c}({data.get(c,{}).get('abbr','?')})" for i,c in enumerate(col_order)]
    pairs2= [f"{i+1}.{c}({data.get(c,{}).get('abbr','?')})" for i,c in enumerate(cols_reordered)]
    print("DEBUG[ORDER] 原始欄序：", " | ".join(pairs))
    print("DEBUG[ORDER] 重排欄序：", " | ".join(pairs2))
    tail = [c for c in cols_reordered if not data.get(c,{}).get('abbr')]
    if tail:
        print("DEBUG[ORDER] 無縮寫（置於隊尾）：", "、".join(tail))

def debug_four_hua_locate(tag: str, stem: str, cols: list, data: dict) -> dict:
    cells = {c: [] for c in cols}
    if not stem or stem not in YEAR_HUA:
        if DEBUG: print(f"DEBUG[HUA] {tag}：無有效天干（{stem}）")
        return cells
    det = []
    for typ in ["祿","權","科","忌"]:
        star = YEAR_HUA[stem].get(typ,"")
        located = [c for c in cols if (star in data[c]["main"]) or (star in data[c]["aux"]) or (star in data[c]["mini"])]
        if not located:
            det.append(f"{typ}:{star}->未定位")
        else:
            det.append(f"{typ}:{star}->" + ",".join(located))
            for c in located: cells[c].append(f"{star}{typ}")  # NOTE: 保留原樣
            # 上行若你想維持舊版字樣，請改回 f"{star}{typ}"
    if DEBUG: print(f"DEBUG[HUA] {tag}（{stem}）｜" + "； ".join(det))
    return cells

# ---------------- 流年／流月 工具 ----------------
ZODIAC = ["子","丑","寅","卯","辰","巳","午","未","申","酉","戌","亥"]
STEMS  = ["甲","乙","丙","丁","戊","己","庚","辛","壬","癸"]

def zodiac_of_year(year: int) -> str:
    base = 1984  # 甲子年，地支=子
    return ZODIAC[(year - base) % 12]

def year_stem_of_year(year: int) -> str:
    base = 1984  # 甲子年，天干=甲
    return STEMS[(year - base) % 10]

def get_col_with_branch(cols: list, branch: str) -> str:
    for c in cols:
        if branch in c:
            return c
    return ""

def build_liunian_row(cols: list, year: int) -> list:
    """
    以『今年的地支』所在欄為命，其右側依 PALACE_ORDER_CANONICAL（命→兄→…→父）循環。
    """
    dz = zodiac_of_year(year)
    anchor_col = get_col_with_branch(cols, dz)
    if not anchor_col:
        return [""] * len(cols)
    labels = PALACE_ORDER_CANONICAL[:]
    out = [""] * len(cols)
    start_idx = cols.index(anchor_col)
    for offset in range(len(cols)):
        pos = (start_idx + offset) % len(cols)
        out[pos] = labels[offset % len(labels)]
    return out

# 指定年份每月天干（你提供的 2025 / 2026 對照）
LIUYUE_MONTH_STEMS = {
    2025: ["戊","己","庚","辛","壬","癸","甲","乙","丙","丁","戊","己"],
    2026: ["庚","辛","壬","癸","甲","乙","丙","丁","戊","己","庚","辛"],
}

def liuyue_base_index(cols: list, data: dict, liunian_row: list) -> int:
    """
    先抓『本命 寅』所在欄位 → 該欄位本命宮位（abbr），
    再去流年行中找到相同宮位的欄位索引 = 流月 1 月的 anchor。
    """
    col_yin = get_col_with_branch(cols, "寅")
    base_pal = data.get(col_yin, {}).get("abbr", "")
    if DEBUG:
        print(f"DEBUG[LIUYUE] 本命『寅』在欄 {col_yin}，本命宮位＝{base_pal}")
    try:
        idx = liunian_row.index(base_pal)
        if DEBUG:
            print(f"DEBUG[LIUYUE] 流年行中對應宮位索引 = {idx}")
        return idx
    except ValueError:
        if DEBUG:
            print("DEBUG[LIUYUE] 在流年行找不到對應宮位，流月將輸出空白。")
        return -1

def build_liuyue_row_by_month(cols: list, base_idx: int, month_no: int) -> list:
    """
    以 base_idx 為 1 月命的位置；第 n 月＝ base_idx+(n-1)。
    『向右遞增』對應你要的 子→丑→寅→… 的月序。
    """
    if base_idx < 0:
        return [""] * len(cols)
    labels = PALACE_ORDER_CANONICAL[:]
    out = [""] * len(cols)
    start_idx = (base_idx - (month_no - 1)) % len(cols)
    for offset in range(len(cols)):
        pos = (start_idx + offset) % len(cols)
        out[pos] = labels[offset % len(labels)]
    return out

# ========================== v6：強化 Debug + 自動修正 ==========================
def render_markdown_table_v6(data: dict, col_order: list, year_stem: str, raw_text: str) -> str:
    """
    v6 = v5 + 強化偵錯與自動修正：欄序、大限錨點、安全查找、四化定位摘要
    （此函式保留，供回溯比較；主輸出在 v7）
    """
    cols = reorder_cols_by_palace(data, col_order)
    if DEBUG: debug_report_order(col_order, cols, data)

    # 表頭
    header = ["原始資料", "宮干支"] + cols
    lines = []
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["----","---"] + ["----"]*len(cols)) + " |")

    # 主/輔/小/大限
    row = ["", "主星"];   [row.append("/".join(data[c]["main"]) if data[c]["main"] else "") for c in cols]; lines.append("| " + " | ".join(row) + " |")
    row = ["", "輔星"];   [row.append("/".join(data[c]["aux"])  if data[c]["aux"]  else "") for c in cols]; lines.append("| " + " | ".join(row) + " |")
    row = ["", "小星"];   [row.append("/".join(data[c]["mini"]) if data[c]["mini"] else "") for c in cols]; lines.append("| " + " | ".join(row) + " |")
    row = ["", "大限"];   [row.append(data[c]["daxian"]) for c in cols]; lines.append("| " + " | ".join(row) + " |")

    # 本命
    row = ["本命","宮位"]; [row.append(data[c]["abbr"]) for c in cols]; lines.append("| " + " | ".join(row) + " |")

    # 生年四化（列出定位詳情）
    if year_stem and year_stem in YEAR_HUA:
        cell_map = debug_four_hua_locate("生年四化", year_stem, cols, data)
        row = ["", f"生年四化（{year_stem}）"]; [row.append("/".join(cell_map[c]) if cell_map[c] else "") for c in cols]; lines.append("| " + " | ".join(row) + " |")

    # 大限命｜宮位（採用安全 anchor）
    byear = parse_birth_year(raw_text)
    age = (CYEAR - byear) if byear else None   # ← 修正：使用全域 CYEAR

    anchor_col = safe_find_anchor_by_age(data, cols, age) if age is not None else ""
    ming_line = build_daxian_ming_row(cols, data, anchor_col)
    row = ["大限命","宮位"]; [row.append(v) for v in ming_line]; lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)

# ========================== v7：主輸出（含 12 宮四化＋流年＋流月） ==========================
def render_markdown_table_v7(data: dict, col_order: list, year_stem: str, raw_text: str) -> str:
    """
    主輸出：
      1) 欄位重排（命→兄→…→父）
      2) 主/輔/小/大限/本命/生年四化
      3) 大限命｜宮位
      4) 大限 12 宮四化（大命、大兄…大父，依標準順序）
      5) 流年命（YYYY）＋ 流命四化（若天干≠地支欄天干，則兩行）
      6) 流月 1~12（以『本命寅』的本命宮位，對齊當年流年行，決定 1 月 anchor）
         並輸出每月四化（2025/2026 以你提供的干支表；其他年份用天干推算）
    """
    cols = reorder_cols_by_palace(data, col_order)
    if DEBUG: debug_report_order(col_order, cols, data)

    # ===== 表頭 =====
    header = ["原始資料", "宮干支"] + cols
    lines = []
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["----","---"] + ["----"]*len(cols)) + " |")

    # ===== 主/輔/小/大限 =====
    row = ["", "主星"];   [row.append("/".join(data[c]["main"]) if data[c]["main"] else "") for c in cols]; lines.append("| " + " | ".join(row) + " |")
    row = ["", "輔星"];   [row.append("/".join(data[c]["aux"])  if data[c]["aux"]  else "") for c in cols]; lines.append("| " + " | ".join(row) + " |")
    row = ["", "小星"];   [row.append("/".join(data[c]["mini"]) if data[c]["mini"] else "") for c in cols]; lines.append("| " + " | ".join(row) + " |")
    row = ["", "大限"];   [row.append(data[c]["daxian"]) for c in cols]; lines.append("| " + " | ".join(row) + " |")

    # ===== 本命 =====
    row = ["本命","宮位"]; [row.append(data[c]["abbr"]) for c in cols]; lines.append("| " + " | ".join(row) + " |")

    # ===== 生年四化 =====
    if year_stem and year_stem in YEAR_HUA:
        cell_map = debug_four_hua_locate("生年四化", year_stem, cols, data)
        row = ["", f"生年四化（{year_stem}）"]; [row.append("/".join(cell_map[c]) if cell_map[c] else "") for c in cols]; lines.append("| " + " | ".join(row) + " |")

    # ===== 大限命｜宮位 =====
    byear = parse_birth_year(raw_text)
    age = (CYEAR - byear) if byear else None   # ← 使用 CYEAR
    anchor_col = safe_find_anchor_by_age(data, cols, age) if age is not None else ""
    ming_line = build_daxian_ming_row(cols, data, anchor_col)
    row = ["大限命","宮位"]; [row.append(v) for v in ming_line]; lines.append("| " + " | ".join(row) + " |")

    # ===== 大限 12 宮四化（命→兄→…→父） =====
    for label in PALACE_ORDER_CANONICAL:
        if 'OUTPUT_SWITCH' in globals() and not OUTPUT_SWITCH["DA_FOUR_HUA"].get(label, True):
            continue
        target_col = find_col_for_label(cols, ming_line, label)
        stem = get_stem_from_col(target_col)
        cells_map = debug_four_hua_locate(f"大{label}四化", stem, cols, data)
        row = ["", f"大{label}四化（{stem}）"]
        for c in cols:
            row.append("/".join(cells_map[c]) if cells_map[c] else "")
        lines.append("| " + " | ".join(row) + " |")

    # ===== 流年命（今年）＋ 流命四化（可能 1 或 2 行） =====
    liu_row = build_liunian_row(cols, CYEAR)   # 使用 CYEAR
    row = [f"流年命（{CYEAR}）","宮位"]; [row.append(v) for v in liu_row]; lines.append("| " + " | ".join(row) + " |")

    stem_year = year_stem_of_year(CYEAR)       # 使用 CYEAR
    dz = zodiac_of_year(CYEAR)                 # 使用 CYEAR

    col_branch = get_col_with_branch(cols, dz); stem_branch = get_stem_from_col(col_branch)
    # --- 行名「流命四化」，邏輯不變；僅加開關 ---
    year_cells_map = debug_four_hua_locate("流命四化(天干)", stem_year, cols, data)
    if stem_branch and stem_branch != stem_year:
        if 'OUTPUT_SWITCH' not in globals() or OUTPUT_SWITCH["LIU_MING_FOUR_HUA"].get("YEAR_STEM_LINE", True):
            row = ["", f"流命四化（{stem_year}）"]; [row.append("/".join(year_cells_map[c]) if year_cells_map[c] else "") for c in cols]; lines.append("| " + " | ".join(row) + " |")
        br_cells_map = debug_four_hua_locate("流命四化(地支欄天干)", stem_branch, cols, data)
        if 'OUTPUT_SWITCH' not in globals() or OUTPUT_SWITCH["LIU_MING_FOUR_HUA"].get("BRANCH_STEM_LINE", True):
            row = ["", f"流命四化（{stem_branch}）"]; [row.append("/".join(br_cells_map[c]) if br_cells_map[c] else "") for c in cols]; lines.append("| " + " | ".join(row) + " |")
        if DEBUG: print(f"DEBUG[LIUNIAN] 兩行輸出：天干={stem_year}；地支欄天干={stem_branch}")
    else:
        if 'OUTPUT_SWITCH' not in globals() or OUTPUT_SWITCH["LIU_MING_FOUR_HUA"].get("YEAR_STEM_LINE", True):
            row = ["", f"流命四化（{stem_year}）"]; [row.append("/".join(year_cells_map[c]) if year_cells_map[c] else "") for c in cols]; lines.append("| " + " | ".join(row) + " |")
        if DEBUG: print(f"DEBUG[LIUNIAN] 合併輸出：天干={stem_year}（地支欄天干相同或不可得）")

    # ===== 新增：流年 12 宮四化（流命/流兄/…/流父） =====
    for label in PALACE_ORDER_CANONICAL:
        if 'OUTPUT_SWITCH' in globals() and not OUTPUT_SWITCH["LIU_FOUR_HUA"].get(label, True):
            continue
        target_col = find_col_for_label(cols, liu_row, label)  # 流年 anchor
        stem = get_stem_from_col(target_col)
        cells_map = debug_four_hua_locate(f"流{label}四化", stem, cols, data)
        row = ["", f"流{label}四化（{stem}）"]
        for c in cols:
            row.append("/".join(cells_map[c]) if cells_map[c] else "")
        lines.append("| " + " | ".join(row) + " |")

    # ===== 流月（以『本命寅』對齊流年行決定 1 月 anchor） =====
    base_idx = liuyue_base_index(cols, data, liu_row)
    month_stems = LIUYUE_MONTH_STEMS.get(CYEAR)  # 使用 CYEAR
    if not month_stems:
        ystem = year_stem_of_year(CYEAR)
        start = STEMS.index(ystem) if ystem in STEMS else 0
        month_stems = [STEMS[(start+i)%10] for i in range(12)]
        if DEBUG:
            print(f"DEBUG[LIUYUE] 未提供 {CYEAR} 月干表，改用年干推算：{month_stems}")

    for i in range(12):
        m_no = i + 1
        if 'OUTPUT_SWITCH' in globals() and m_no not in OUTPUT_SWITCH["LIU_YUE"]["MONTHS"]:
            continue

        row_labels = build_liuyue_row_by_month(cols, base_idx, m_no)
        if 'OUTPUT_SWITCH' not in globals() or OUTPUT_SWITCH["LIU_YUE"].get("SHOW_PALACE_ROW", True):
            row = [f"流月命（{CYEAR}-{m_no:02d}）","宮位"]; [row.append(v) for v in row_labels]; lines.append("| " + " | ".join(row) + " |")

        if 'OUTPUT_SWITCH' not in globals() or OUTPUT_SWITCH["LIU_YUE"].get("SHOW_HUA_ROW", True):
            m_stem = month_stems[i]
            m_cells_map = debug_four_hua_locate(f"流月{m_no:02d}四化", m_stem, cols, data)
            row = ["", f"流月四化（{m_stem}）"]; [row.append("/".join(m_cells_map[c]) if m_cells_map[c] else "") for c in cols]; lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)

# ======================= 主程式（請把命盤貼在 RAW） =======================


# --- Module-friendly default for web integration ---
if 'CYEAR' not in globals() or globals().get('CYEAR') is None:
    CYEAR = 2025

# 避免被 Flask 匯入時自動執行
if __name__ == "__main__":
    print("此模組為命盤分析邏輯，請由 app.py 呼叫使用。")