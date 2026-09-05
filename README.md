# 云南电梯招标监控

自动监控云南电梯相关招标 / 中标 / 变更信息，每天定时推送到微信。
部署在 GitHub Actions，电脑关机也能跑，不消耗任何费用。

---

## 一、监控范围

### 数据源
| 数据源 | 覆盖范围 |
|---|---|
| 云南省公共资源交易网（ggzy.yn.gov.cn） | 工程类 + 政府采购类（云南本地最全） |
| 中国政府采购网（ccgp.gov.cn） | 全国政采，按"云南省"过滤 |

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

## 二、部署步骤（只需做一次）

### 第 1 步：把代码上传到 GitHub

进入你的仓库 `https://github.com/xm5672/yn-elevator-monitor`，
点 **Add file → Upload files**，把下面 4 个文件拖进去：

```
monitor.py
requirements.txt
.github/workflows/daily.yml      ← 注意：要连目录一起创建
seen.json（本地跑过才有，有就传，没有可跳过）
```

> **如何创建 `.github/workflows/` 目录？**
> GitHub 网页上传时无法直接建空目录。可以点 **Add file → Create new file**，
> 在文件名框里直接输入 `.github/workflows/daily.yml`（带斜杠），
> GitHub 会自动帮你建好目录，然后把 daily.yml 的内容粘贴进去即可。

### 第 2 步：配置推送密钥（重要）

1. 进入仓库 → **Settings** → **Secrets and variables** → **Actions**
2. 点 **New repository secret**
3. Name 填：`PUSHPLUS_TOKEN`
4. Value 填你的 PushPlus Token
5. 点 **Add secret**

> 密钥会加密存储，代码里看不到，也不会出现在运行日志里。

### 第 3 步：启用 Actions

1. 进入仓库 → **Actions** 标签页
2. 如果看到提示 "I understand my workflows, go ahead and enable them"，点它启用
3. 左侧找到 **云南电梯招标监控**，点进去
4. 右上角点 **Run workflow** → **Run workflow**，手动跑一次测试

几秒到一分钟后，你微信就能收到消息了。

---

## 三、运行时间

默认：**每天北京时间 08:00**

想改时间，编辑 `.github/workflows/daily.yml` 里的 cron：

```yaml
schedule:
  - cron: '0 0 * * *'    # UTC 时间，北京时间 = UTC + 8
```

换算方法：**北京时间 - 8 = UTC 时间**

| 想要的时间（北京） | cron |
|---|---|
| 早上 8:00 | `0 0 * * *` |
| 早上 9:00 | `0 1 * * *` |
| 中午 12:00 | `0 4 * * *` |
| 晚上 20:00 | `0 12 * * *` |
| 早 8 点 + 晚 8 点各一次 | 两条：`0 0 * * *` 和 `0 12 * * *` |

---

## 四、常见调整

编辑 `monitor.py` 顶部的配置区：

```python
DAYS_BACK = 7          # 只推近 N 天的信息，避免推历史旧闻
KEYWORDS = [...]       # 服务端搜索关键词
MATCH_WORDS = [...]    # 本地二次校验词表
```

> 改完后 commit，下次运行自动生效。

---

## 五、本地测试

```bash
pip install -r requirements.txt

export PUSHPLUS_TOKEN="你的token"     # Windows 用 set
python monitor.py
```

首次运行会把现有信息建立为基线，只发一条"监控已启动"通知，不会轰炸。
之后每次运行只推送新增。

---

## 六、说明

- **去重**：`seen.json` 记录已推送条目，同一条不会重复推。
- **心跳**：无新信息时也会推送"今日无更新"，方便确认脚本还活着。
- **容错**：单个数据源失败不影响其他源。

### 当前未接入的源
- 中国招标投标公共服务平台（ctbpsp.com）：纯前端渲染，需浏览器抓包，后续可扩展
- 政采云（zcygov.cn）：与已接入的两源重复度较高，暂未接入
