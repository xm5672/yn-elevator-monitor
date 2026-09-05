# 云南电梯招标监控

自动监控云南电梯相关招标 / 中标 / 变更信息，每天定时推送到微信。

> **重要提示**：云南公共资源交易网（ggzy.yn.gov.cn）只对中国大陆 IP 开放，
> GitHub 等境外服务器抓不到。本系统采用「**本机 + 云端分源部署**」方案：
> 本机抓主力源 ggzy（境内 IP），云端抓 ccgp 作为保底。两边各跑各的、不会重复推送。

---

## 一、监控范围

### 数据源（分源抓取）

| 数据源 | 由谁抓 | 覆盖 |
|---|---|---|
| 云南省公共资源交易网（ggzy.yn.gov.cn） | **本机**（境内 IP） | 工程类 + 政府采购类，云南本地最全 |
| 中国政府采购网（ccgp.gov.cn） | **云端 GitHub Actions** | 全国政采，按"云南省"过滤 |

### 信息类型
- 招标公告
- 预公告（招标文件预公示、招标计划）
- 变更 / 更正公告
- 中标结果（含中标候选人）
- 异常公告

### 关键词
电梯、自动扶梯、扶梯、升降机、液压平台、液压升降平台、
电梯维修、电梯保养、电梯改造、电梯更新、电梯维保

### 地域
云南省 16 州市全覆盖（昆明、昭通、曲靖、玉溪、保山、楚雄、红河、文山、
普洱、西双版纳、大理、德宏、丽江、怒江、迪庆、临沧）

---

## 二、当前部署情况

### 本机（Windows 计划任务）
- 任务名：`YN-Elevator-Monitor`
- 触发时间：**每天 08:00 和 20:00**
- 执行脚本：`run_local.bat`
- 抓取源：`ggzy`（仅云南本地源）
- 去重文件：`seen_local.json`（与云端隔离，互不重复推送）

### 云端（GitHub Actions）
- 仓库：`https://github.com/xm5672/yn-elevator-monitor`
- 触发时间：**每天北京时间 08:00**（UTC 0 点）
- 工作流：`.github/workflows/daily.yml`
- 抓取源：`ccgp`（仅全国政采）
- 去重文件：`seen.json`（云端自动 commit 回仓库）

### 推送
- 渠道：PushPlus 微信公众号推送
- 有新增：推送条目清单
- 无新增：推送"今日无更新"心跳（证明系统在跑）

---

## 三、文件说明

| 文件 | 作用 |
|---|---|
| `monitor.py` | 主抓取脚本，支持 `SOURCES` 和 `SEEN_FILE` 环境变量分源分库 |
| `.github/workflows/daily.yml` | 云端 GitHub Actions 配置（每天 08:00 UTC 0 点跑） |
| `run_local.bat` | 本机包装脚本（设好 token + SOURCES=ggzy + SEEN_FILE=seen_local.json） |
| `requirements.txt` | Python 依赖 |
| `seen.json` | 云端去重基线（自动提交） |
| `seen_local.json` | 本机去重基线（仅本机） |
| `deploy.py` / `upload.py` | 一键部署到 GitHub 的脚本（已跑过） |
| `logs/run.log` | 本机每次运行的日志 |

---

## 四、本地调试

```bash
# 仅抓 ggzy（适合本机）
set PUSHPLUS_TOKEN=你的token
set SOURCES=ggzy
set SEEN_FILE=seen_local.json
python monitor.py

# 仅抓 ccgp（适合云端）
set SOURCES=ccgp
set SEEN_FILE=seen.json
python monitor.py

# 全抓（首次调试）
set SOURCES=all
python monitor.py
```

> 首次运行会把现有信息建立为基线，只发一条"监控已启动"通知，不会轰炸。
> 之后每次运行只推送新增。

---

## 五、调整监控参数

编辑 `monitor.py` 顶部的配置区：

```python
DAYS_BACK = 7              # 只推近 N 天的信息
KEYWORDS = [...]           # 服务端搜索关键词
MATCH_WORDS = [...]        # 本地二次校验词表
SOURCES = "all"            # 默认全抓，本机和云端会覆盖
```

改完后重新部署：

- **云端**：把改后的 monitor.py 提交到 GitHub，云端次日自动生效
- **本机**：直接保存即可，下次定时运行自动生效

---

## 六、未接入的源（后续可扩展）

- 中国招标投标公共服务平台（ctbpsp.com / cebpubservice.com）：纯前端渲染，需浏览器抓包
- 政采云（zcygov.cn）：与已接入的两源重复度较高，暂未接入
- 州市政府门户、企业自建采购平台：覆盖云南地方小项目和国企非必招项目

---

## 七、注意事项

- **电脑关机影响**：关机时 ggzy 不抓，ccgp（云端）仍正常推送
- **去重机制**：本机 `seen_local.json` 与云端 `seen.json` 互不影响
- **监控失效**：如果你超过 1 周没收到任何消息（连心跳都没有），说明本机计划任务停了