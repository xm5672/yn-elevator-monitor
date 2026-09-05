# -*- coding: utf-8 -*-
"""
云南电梯招标/中标信息监控
=========================
数据源：
  1. 云南省公共资源交易网 (ggzy.yn.gov.cn) —— 工程类 + 政府采购类，覆盖预公示/招标/变更/中标
  2. 中国政府采购网 (ccgp.gov.cn)          —— 全国政采，按云南地域过滤

输出：PushPlus 微信推送（无更新时发心跳）

用法：
    set PUSHPLUS_TOKEN=xxxx        (Windows)
    export PUSHPLUS_TOKEN=xxxx     (Linux/GitHub Actions)
    python monitor.py
"""
import os
import re
import json
import time
import random
import hashlib
import warnings
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

warnings.filterwarnings("ignore")

# ============================================================
# 配置区
# ============================================================

# 推送 Token（从环境变量读取，禁止硬编码）
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "").strip()

# 近多少天内的数据才推送（避免推历史旧闻）
DAYS_BACK = int(os.environ.get("DAYS_BACK", "7"))

# 去重记录文件
SEEN_FILE = os.environ.get("SEEN_FILE", "seen.json")

# 每个源最多取多少页
MAX_PAGES = int(os.environ.get("MAX_PAGES", "3"))

# 是否推送"无更新"心跳
SEND_HEARTBEAT = os.environ.get("SEND_HEARTBEAT", "1") == "1"

# 关键词（服务端搜索用，取并集后本地再二次校验）
# 说明：搜"电梯"已可覆盖 电梯/自动扶梯/电梯维修/电梯保养/电梯改造/电梯更新/电梯维保
KEYWORDS = ["电梯", "扶梯", "升降机", "液压平台"]

# 本地二次校验用的完整词表（命中任一即算相关）
MATCH_WORDS = [
    "电梯", "自动扶梯", "扶梯", "升降机", "液压平台", "液压升降平台",
    "电梯维修", "电梯保养", "电梯改造", "电梯更新", "电梯维保",
]

# 云南 16 州市 + 省级标识
YN_CITIES = [
    "云南", "昆明", "昭通", "曲靖", "玉溪", "保山", "楚雄", "红河",
    "文山", "普洱", "西双版纳", "大理", "德宏", "丽江", "怒江", "迪庆", "临沧",
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

GGZY_API = "https://ggzy.yn.gov.cn/ynggfwpt-home-api"
GGZY_HEAD = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": "https://ggzy.yn.gov.cn",
    "Referer": "https://ggzy.yn.gov.cn/",
}

# ggzy 端点配置：路径 -> (信息类型, 标题字段名, 日期字段名)
GGZY_ENDPOINTS = {
    "/jyzyCenter/jyInfo/gcjs/getZbwjygsList": ("预公示", "tenderProjectName", "publishTime"),
    "/jyzyCenter/jyInfo/gcjs/getTenserPlanList": ("招标计划", "tenderProjectName", "publishTime"),
    "/jyzyCenter/jyInfo/gcjs/getZbggList": ("招标公告", "bulletinname", "bulletinissuetime"),
    "/jyzyCenter/jyInfo/gcjs/getGzsxList": ("变更公告", "bulletinname", "bulletinissuetime"),
    "/jyzyCenter/jyInfo/gcjs/getZbJgGgList": ("中标结果", "bulletinname", "bulletinissuetime"),
    "/jyzyCenter/jyInfo/gcjs/getZbycList": ("异常公告", "bulletinname", "bulletinissuetime"),
    "/jyInfo/zfcg/getCgggList": ("政采公告", "bulletintitle", "bulletinstarttime"),
    "/jyInfo/zfcg/getGzsxList": ("政采变更", "terminationbulletintitle", "modificationstarttime"),
    "/jyInfo/zfcg/getZbjgList": ("政采中标", "winbidbulletintitle", "winbidbulletinstarttime"),
}


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def make_id(text):
    """生成稳定唯一 ID"""
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:16]


def is_relevant(title):
    """本地二次校验：是否命中关键词"""
    t = title or ""
    return any(w in t for w in MATCH_WORDS)


def in_time_range(date_str, days=DAYS_BACK):
    """判断日期是否在最近 N 天内。无法解析时返回 True（保守放行）"""
    if not date_str:
        return True
    s = str(date_str).strip()
    if not s:
        return True
    # 归一化为 YYYY-MM-DD
    m = re.search(r"(\d{4})[-/年]?(\d{1,2})[-/月]?(\d{1,2})?", s)
    if not m:
        return True
    try:
        y, mo = int(m.group(1)), int(m.group(2))
        d = int(m.group(3)) if m.group(3) else 1
        dt = datetime(y, mo, d)
    except Exception:
        return True
    return dt >= datetime.now() - timedelta(days=days)


def clean_date(date_str):
    """提取 YYYY-MM-DD"""
    if not date_str:
        return ""
    m = re.search(r"(\d{4})[-/年]?(\d{1,2})[-/月]?(\d{1,2})?", str(date_str))
    if not m:
        return str(date_str)[:10]
    y, mo = m.group(1), int(m.group(2))
    d = int(m.group(3)) if m.group(3) else 1
    return f"{y}-{mo:02d}-{d:02d}"


# ============================================================
# 数据源 1：云南省公共资源交易网
# ============================================================

def fetch_ggzy():
    """抓取 ggzy.yn.gov.cn 各端点"""
    results = []
    cutoff = (datetime.now() - timedelta(days=DAYS_BACK)).strftime("%Y-%m-%d")
    log(f"抓取 ggzy.yn.gov.cn（近 {DAYS_BACK} 天，截止 {cutoff}）")

    sess = requests.Session()
    sess.headers.update(GGZY_HEAD)

    for ep, (itype, tfield, dfield) in GGZY_ENDPOINTS.items():
        for kw in KEYWORDS:
            try:
                payload = {"pageNo": 1, "pageSize": 30, "title": kw}
                r = sess.post(GGZY_API + ep, json=payload, timeout=25)
                j = r.json()
                if str(j.get("code")) != "1":
                    continue
                v = j.get("value", {})
                lst = v.get("list", []) if isinstance(v, dict) else []
                for item in lst:
                    # 标题：主字段取不到时，回退到任意含 title/name 的字段
                    title = item.get(tfield) or ""
                    if not title:
                        for k, val in item.items():
                            if ("title" in k.lower() or "name" in k.lower()) and isinstance(val, str) and len(val) > 6:
                                title = val
                                break
                    title = (title or "").strip()
                    if not title or not is_relevant(title):
                        continue

                    date_raw = item.get(dfield) or ""
                    if not date_raw:
                        for k in ("publishTime", "bulletinissuetime", "createTime", "modifyTime"):
                            if item.get(k):
                                date_raw = item[k]
                                break
                    date_s = clean_date(date_raw)

                    # 时间过滤
                    if date_s and date_s < cutoff:
                        continue

                    guid = item.get("guid") or make_id(title + date_s)
                    # 详情页链接
                    link = f"https://ggzy.yn.gov.cn/#/tradeHall/tradeDetail?guid={guid}"
                    area = item.get("areaName") or ""

                    results.append({
                        "id": make_id("ggzy_" + str(guid)),
                        "source": "云南公共资源交易",
                        "type": itype,
                        "title": title[:120],
                        "date": date_s,
                        "area": area,
                        "link": link,
                    })
                time.sleep(random.uniform(0.3, 0.8))
            except Exception as e:
                log(f"  ggzy {ep} kw={kw} 失败: {type(e).__name__}")
                continue
    log(f"  ggzy 抓到 {len(results)} 条")
    return results


# ============================================================
# 数据源 2：中国政府采购网
# ============================================================

def fetch_ccgp():
    """抓取 ccgp.gov.cn 云南相关公告"""
    results = []
    log("抓取 ccgp.gov.cn（中国政府采购网）")

    today = datetime.now()
    # ccgp 要求 YYYY:MM:DD 格式（再 URL 编码），且用 displayZone 做服务端地域过滤
    start = (today - timedelta(days=DAYS_BACK)).strftime("%Y:%m:%d").replace("-", ":")
    end = today.strftime("%Y:%m:%d").replace("-", ":")
    zone = requests.utils.quote("云南省")
    zone_id = "53"   # 云南省行政区划代码，用于 ccgp 服务端地域过滤（关键）

    full_head = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    }

    for kw in KEYWORDS:
        sess = requests.Session()
        sess.headers.update(full_head)
        try:
            sess.get("http://www.ccgp.gov.cn/", timeout=20)
        except Exception:
            pass
        time.sleep(random.uniform(1.0, 2.0))
        sess.headers.update({"Referer": "http://www.ccgp.gov.cn/", "Host": "search.ccgp.gov.cn"})

        url = (f"http://search.ccgp.gov.cn/bxsearch?searchtype=1&page_index=1&bidSort=0"
               f"&kw={requests.utils.quote(kw)}"
               f"&start_time={requests.utils.quote(start)}"
               f"&end_time={requests.utils.quote(end)}"
               f"&timeType=6&displayZone={zone}&zoneId={zone_id}&pppStatus=0&agentName=")
        try:
            r = sess.get(url, timeout=25)
            r.encoding = r.apparent_encoding or "utf-8"
            html = r.text
            if "频繁访问" in html or len(html) < 5000:
                log(f"  ccgp kw={kw} 被限流，跳过")
                time.sleep(random.uniform(3, 6))
                continue
            soup = BeautifulSoup(html, "lxml")
            links = soup.find_all("a", href=re.compile(r"ccgp\.gov\.cn/cggg/"))
            for a in links:
                title = a.get_text(strip=True)
                if not title or not is_relevant(title):
                    continue
                # 服务端已按 displayZone=云南省 过滤，此处不再强制校验标题
                # （如"江城哈尼族彝族自治县…"标题不含"云南"二字，强制过滤会误杀）
                area = ""
                for c in YN_CITIES[1:]:
                    if c in title:
                        area = c
                        break
                href = a.get("href", "").strip()
                if href.startswith("//"):
                    href = "http:" + href
                # 日期：从同一容器里找
                date_s = ""
                parent = a.find_parent(["li", "div"])
                if parent:
                    m = re.search(r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})", parent.get_text())
                    if m:
                        date_s = clean_date(m.group(1))
                results.append({
                    "id": make_id("ccgp_" + href),
                    "source": "中国政府采购网",
                    "type": "政采公告",
                    "title": title[:120],
                    "date": date_s,
                    "area": area or "云南",
                    "link": href,
                })
            time.sleep(random.uniform(2, 4))
        except Exception as e:
            log(f"  ccgp kw={kw} 失败: {type(e).__name__}")
            continue

    log(f"  ccgp 抓到 {len(results)} 条")
    return results


# ============================================================
# 去重
# ============================================================

def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_seen(seen):
    try:
        # 只保留最近 3000 条，防止无限膨胀
        lst = sorted(seen)[-3000:]
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(lst, f, ensure_ascii=False, indent=0)
    except Exception as e:
        log(f"  保存 seen 失败: {e}")


# ============================================================
# 推送
# ============================================================

def push(title, content):
    """PushPlus 推送"""
    if not PUSHPLUS_TOKEN:
        log("  ⚠️ 未配置 PUSHPLUS_TOKEN，跳过推送")
        return False
    try:
        r = requests.post(
            "https://www.pushplus.plus/send",
            json={"token": PUSHPLUS_TOKEN, "title": title,
                  "content": content, "template": "txt"},
            timeout=25,
        )
        j = r.json()
        ok = str(j.get("code")) == "200"
        log(f"  推送{'成功' if ok else '失败'}: {j.get('msg', j)}")
        return ok
    except Exception as e:
        log(f"  推送异常: {type(e).__name__}: {e}")
        return False


def build_content(items):
    """构造推送正文"""
    # 按类型分组
    groups = {}
    for it in items:
        groups.setdefault(it["type"], []).append(it)

    lines = []
    order = ["招标公告", "预公示", "招标计划", "政采公告", "变更公告", "政采变更",
             "中标结果", "政采中标", "异常公告"]
    ordered = [k for k in order if k in groups] + [k for k in groups if k not in order]

    for t in ordered:
        lst = groups[t]
        lines.append(f"\n【{t}】{len(lst)} 条")
        for it in lst[:12]:
            area = f"（{it['area']}）" if it.get("area") else ""
            date = f" {it['date']}" if it.get("date") else ""
            lines.append(f"\n• {it['title']}{area}{date}")
            lines.append(f"  {it['link']}")
        if len(lst) > 12:
            lines.append(f"\n  …… 另有 {len(lst)-12} 条，请登录平台查看")

    return "\n".join(lines)


# ============================================================
# 主流程
# ============================================================

def main():
    log("=" * 55)
    log("云南电梯招标监控 启动")
    log("=" * 55)

    all_items = []

    # 1. 抓取
    try:
        all_items += fetch_ggzy()
    except Exception as e:
        log(f"ggzy 源异常: {e}")
    try:
        all_items += fetch_ccgp()
    except Exception as e:
        log(f"ccgp 源异常: {e}")

    # 2. 全局去重（按 id）
    uniq = {}
    for it in all_items:
        if it["id"] not in uniq:
            uniq[it["id"]] = it
    all_items = list(uniq.values())
    log(f"去重后共 {len(all_items)} 条")

    # 3. 与历史去重
    seen = load_seen()
    first_run = len(seen) == 0
    new_items = [it for it in all_items if it["id"] not in seen]
    log(f"历史已记录 {len(seen)} 条，本次新增 {len(new_items)} 条")

    # 4. 推送
    today = datetime.now().strftime("%Y-%m-%d")

    if first_run:
        # 首次运行：仅建立基线，不发全部（避免轰炸）
        for it in all_items:
            seen.add(it["id"])
        save_seen(seen)
        sample = sorted(all_items, key=lambda x: x.get("date", ""), reverse=True)[:8]
        push(f"✅ 云南电梯招标监控已启动｜{today}",
             f"首次运行完成。\n已纳入 {len(all_items)} 条现有信息作为基线，此后仅推送新增。\n\n"
             f"监控源：云南省公共资源交易网、中国政府采购网\n"
             f"关键词：{'、'.join(MATCH_WORDS)}\n"
             f"地域：云南省 16 州市\n\n"
             f"【最近 8 条参考】\n{build_content(sample)}")
        log("首次运行：已建立基线")

    elif new_items:
        MAX_PUSH = 40
        sorted_items = sorted(new_items, key=lambda x: x.get("date", ""), reverse=True)
        push_items = sorted_items[:MAX_PUSH]
        title = f"🔔 云南电梯招标 {today}｜新增 {len(new_items)} 条"
        head = f"共 {len(new_items)} 条新信息"
        if len(new_items) > MAX_PUSH:
            head += f"（以下展示最新 {MAX_PUSH} 条）"
        push(title, head + "\n" + build_content(push_items))
        for it in new_items:
            seen.add(it["id"])
        save_seen(seen)
    else:
        log("本次无新增")
        if SEND_HEARTBEAT:
            push(f"☑️ 云南电梯招标 {today}｜今日无更新",
                 f"巡检完成，近 {DAYS_BACK} 天内未发现新的电梯相关招标/中标信息。\n"
                 f"监控范围：云南公共资源交易网、中国政府采购网\n"
                 f"关键词：{'、'.join(MATCH_WORDS)}")

    # 5. 本地留存（便于排查）
    try:
        with open("latest_result.json", "w", encoding="utf-8") as f:
            json.dump(all_items, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    log("完成")


if __name__ == "__main__":
    main()
