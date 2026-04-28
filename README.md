# 西工大的选课公式，是个骗局吗？

先说边界：这里不是说某个具体学校、具体同学或具体学长在骗人。标题里的“骗局”指的是一种常见幻觉：只要拿到一个投豆公式，学生就能机械算出最优投豆数。

这个项目做的是一个可复现的投豆选课沙盒。我们生成了结构上贴近现实的合成选课市场，包括学生、培养方案、必修压力、课程容量、热门课、冷门课、时间冲突、老师/课程偏好和不同类型的行为学生。它不是教务真实数据，但用于回答一个很现实的问题：

**投豆选课时，怎么估计录取边界，怎么避免在没竞争的课上当“怨种”？**

核心结论很短：

1. 流传公式有用，但它只是拥挤信号，不是最终投豆答案。
2. 更稳定的做法是先看拥挤比 `r = m/n`，估计录取边界，再按课程重要性加安全垫。
3. 必修课、毕业压力、特别喜欢的老师/课程值得加价；普通可替代课不要用高价表达喜欢。
4. 在我们的合成实验里，拥挤比衍生的边界规则明显优于原公式缩放版；CASS-v2 也比机械套公式更稳。

## 流传公式

本项目评估的“流传公式”是：

$$
f(m,n,\alpha)=(1+\alpha)\sqrt{m-n}\,e^{m/n}
$$

<img width="767" height="191" alt="投豆公式截图" src="https://github.com/user-attachments/assets/d60151dd-8bb7-4e3a-81a4-a574f08510c4" />

符号解释：

- `m`：当前可见的排队/待选人数。
- `n`：课程容量。
- `alpha`：人为选择的浮动偏移；我们按 `[-0.25, 0.30]` 看待这个浮动。

这个公式最大的问题不是“完全没用”，而是**只看 `m,n`**。它没有看这门课对你是不是必修、是不是影响毕业、有没有替代 section、你还有多少预算、你是不是真的特别想上这位老师的课。

所以它可以提醒你“这门课挤不挤”，但不能直接替你决定“该投多少豆”。

## 我们怎么做实验

我们在合成市场里比较了几类策略：

| 策略 | 含义 |
| --- | --- |
| BA | 模拟普通学生，带不同 persona 和风险偏好 |
| Formula BA | 普通学生先选课，再用流传公式重分配豆子 |
| LLM | 让大模型在工具约束下选课投豆 |
| LLM + formula | 把流传公式给大模型当参考信号 |
| CASS | 纯规则算法，目标是给定市场下让某个学生选得更好、少浪费豆子 |

我们定义了一个内部效用指标来比较策略：它衡量学生是否拿到喜欢且重要的课，其中重要性包括必修课、毕业压力、培养方案要求、课程/老师偏好等。这个效用只用于沙盒研究，不要求真实学生精确计算。

真实学生更应该记住的是：

```text
先估边界，再决定值不值得追。
```

## 拥挤比边界

我们把所有实验输出汇总成 `run × 教学班` 观测，用 `r = m/n` 预测真实录取边界 `cutoff_bid`。本轮使用 `87` 个 run、`10469` 个教学班观测。

模型比较结果：

| 规则 | Test MAE | Coverage | 含义 |
| --- | ---: | ---: | --- |
| log 饱和模型 | **0.94** | 88.4% | 统计误差最低 |
| 拥挤比分箱 p75 | 1.31 | **93.0%** | 最适合公开执行 |
| 原公式缩放版 | 4.58 | 72.4% | 明显更差 |

这里的 `Coverage` 表示预测边界不低于真实 cutoff 的比例。`p75` 分箱规则不是最精细的模型，但它简单、稳健、好解释。

可执行版本如下：

| 拥挤比 `m/n` | 中位边界 p50 | 安全边界 p75 | 高安全边界 p90 |
| --- | ---: | ---: | ---: |
| `< 1.0` | 0 | 0 | 0 |
| `1.0 - 1.2` | 6 | 8 | 12 |
| `1.2 - 1.5` | 8 | 13 | 15 |
| `1.5 - 2.0` | 10 | 12 | 15 |
| `2.0 - 3.0` | 16 | 22 | 28.5 |
| `>= 3.0` | 14 | 17 | 18.4 |

怎么用：

- 普通可替代课：看 p50 或更低，不要硬追。
- 重要但有替代的课：看 p75。
- 必修、毕业压力大、特别想上且替代很差的课：才考虑 p90 或额外安全垫。
- `m/n < 1` 时，绝大多数课程边界是 0；这时高投往往只是浪费。

完整统计细节见 [拥挤比边界公式拟合报告](reports/interim/report_2026-04-28_crowding_boundary_formula_fit.md)。

## CASS 的发现

CASS 是 `Competition-Adaptive Selfish Selector`，不是多智能体博弈算法，也不是全市场福利优化。它解决的是单个学生的最优响应问题：

```text
给定其他人怎么投，我这个学生怎么选课和投豆，才能拿到更高结果并减少无效多投？
```

我们测试了至少 6 种 CASS 策略族，并做了敏感度分析，避免只靠拍脑袋调分段阈值。当前最稳的是 `cass_v2`：它不把豆子平均撒出去，而是用拥挤信号、课程重要性和替代性一起决定是否追价。

重要发现：

- 只省豆不是目标；省过头会损失好课。
- 只追热门也不是目标；很多低竞争课 1 豆就够。
- 好策略应该先保证课程结果，再减少拒录浪费和明显过度投豆。

相关报告：

- [CASS 策略族与敏感度分析](reports/interim/report_2026-04-28_cass_sensitivity_analysis.md)
- [CASS 多学生回测](reports/interim/report_2026-04-28_cass_multifocal_llm_batch.md)
- [拥挤比边界公式拟合报告](reports/interim/report_2026-04-28_crowding_boundary_formula_fit.md)

## 给学生的简洁策略

```text
第一步：看拥挤比
  m/n < 1：通常别多投
  m/n 接近或略大于 1：轻保护
  m/n 明显大于 1：才进入真正竞争

第二步：看课程重要性
  必修/毕业压力 > 核心强需求 > 特别喜欢 > 一般想上 > 可替代课

第三步：看替代品
  有替代 section 或替代课，就不要和大热课死磕
  没竞争但很喜欢，也不要用高价表达喜欢
```

一句话：**先用 `m/n` 猜边界，再用课程重要性决定安全垫。**

## 快速复现

安装本地开发版：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e .
python -m bidflow --help
```

生成合成市场：

```powershell
bidflow market generate --scenario research_large_high --output data/synthetic/research_large
bidflow market validate data/synthetic/research_large
```

运行 baseline：

```powershell
bidflow session run `
  --market data/synthetic/research_large `
  --population "background=behavioral" `
  --run-id research_large_800x240x3_behavioral `
  --time-points 3
```

回测 CASS：

```powershell
bidflow replay run `
  --baseline outputs/runs/research_large_800x240x3_behavioral `
  --focal S048 `
  --agent cass `
  --policy cass_v2 `
  --data-dir data/synthetic/research_large `
  --output outputs/runs/research_large_s048_cass_replay
```

拟合拥挤比边界：

```powershell
bidflow analyze crowding-boundary
```

跑 CASS 策略族与敏感度分析：

```powershell
bidflow analyze cass-sensitivity --quick
bidflow analyze cass-sensitivity
```

## 项目结构

```text
bidflow/     新 CLI 和平台包装层：agent / market / session / replay / analyze
src/         兼容旧入口和核心实验实现
configs/     生成器、模型和场景配置
docs/        使用说明和复现实验
reports/     interim/final/reviews 报告
tests/       单元测试与 CLI smoke tests
```

生成数据和实验输出默认不入库；请在本地用命令复现。
