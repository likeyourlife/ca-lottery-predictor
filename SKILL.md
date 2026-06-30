---
name: ca-lottery-predictor
summary: "加州天天乐彩票预测 — 从39号(1-39)中预测当期最不可能开出号码，排序Top2/4/10，双模式(避开+回补)，6引擎融合(回测驱动权重)"
triggers:
  - "天天乐预测"
  - "天天乐冷号"
  - "加州彩票"
  - "Fantasy 5 预测"
  - "Fantasy 5 冷号"
  - "彩票分析"
  - "彩票冷号"
  - "lottery predict"
  - "冷热号"
  - "避开号码"
  - "回补号码"
  - "概率最低号码"
  - "天天乐回测"
  - "天天乐优化"
---

# 🍡 加州天天乐彩票预测分析 Skill

## 功能说明

从 California Fantasy 5 的39个号码(1-39)中，预测当期最不可能开出的中奖号码。

- **预测逻辑**: 计算每个号码的"不出现概率(P_low)"，按P_low从高到低排序
- **输出层级**: Top2 / Top4 / Top10
- **双模式**:
  - 🔴 **避开模式**: P_low最高的号码 = 最不可能出现（用来排除）
  - 🟢 **回补模式**: 冷号加分 = 长期未出现的号码可能即将回补（用来捕捉）

## 引擎架构

6引擎融合(回测驱动权重 v2):
- **E1 频次偏差引擎**: 历史频次 vs 理论期望 → Z-score → P_low (权重8%)
- **E2 贝叶斯概率引擎**: Beta-Binomial后验(理论概率先验5/39) → P_low (权重22%)
- **E3 马尔可夫链引擎**: 一阶状态转移概率矩阵 → P_low (权重36% ⭐)
- **E4 连号联合引擎**: 号码间共现/排斥偏差矩阵 → P_low (权重34% ⭐)
- **E5 FFT周期引擎**: 频谱周期性检测 → 周期相位 → P_low (权重1%)
- **E6 蒙特卡洛引擎**: N次随机排除+偏差敏感性叠加 → P_low (权重0%, 回测验证不提供增量信号)

**回测验证结果(100期)**: Top10命中率80.00% > 基线79.37% (+0.63%)

## ⚠️ 免责声明

本软件**不声称能预测彩票中奖号码**。彩票开奖本质为随机过程，模型输出仅为**统计参考**，不构成投注建议。

---

## 执行流程

当用户触发此 Skill 时，按以下步骤执行：

### Step 1: 运行预测

```bash
cd /Users/ioorule/Desktop/天天乐/ca-lottery-predictor
/Users/ioorule/.workbuddy/binaries/python/envs/default/bin/python run_predictor.py fantasy5 full
```

快速模式:
```bash
/Users/ioorule/.workbuddy/binaries/python/envs/default/bin/python run_predictor.py fantasy5 quick
```

JSON模式(供程序调用):
```bash
/Users/ioorule/.workbuddy/binaries/python/envs/default/bin/python run_predictor.py fantasy5 json
```

### Step 2: 输出报告

将终端报告展示给用户。

### Step 3: 回测验证(可选)

```bash
/Users/ioorule/.workbuddy/binaries/python/envs/default/bin/python run_predictor.py fantasy5 backtest
```

### Step 4: 权重优化(可选)

```bash
/Users/ioorule/.workbuddy/binaries/python/envs/default/bin/python run_predictor.py fantasy5 optimize
```

### Step 5: 数据更新(可选)

如果用户要求获取最新数据，使用 WebFetch 从以下源获取:
- `https://california.lottonumbers.com/fantasy-5/past-numbers`
- `https://fantasy-5.com/california/past-numbers`
- `https://www.lottery.net/california/fantasy-5/numbers`

---

## 使用示例

用户输入: "天天乐预测"
 → 执行预测流程，输出 Fantasy 5 避开/回补模式 Top2/4/10

用户输入: "Fantasy 5 冷号"
 → 同上，侧重回补模式

用户输入: "天天乐回测"
 → 执行100期回测，输出命中率对比基线报告

用户输入: "天天乐优化"
 → 执行随机搜索+局部微调权重优化，输出最优权重

## 当前数据状态

- 历史数据: 682期 (2022年8月-2026年6月)
- 数据源限制: 1-7月数据获取困难(API封锁/动态网页截断)
- 后续可扩充: 使用浏览器自动化(Puppeteer)抓取完整历史
