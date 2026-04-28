# 策略公开后的二阶博弈报告

> 日期：2026-04-28
> 问题：如果越来越多学生都知道“拥挤比边界公式 + 重要性系数 + 尾数避让”，选课系统会变成什么样？

## 1. 结论

策略公开以后，选课系统不会停留在“少数聪明人套利”的状态。它会进入二阶博弈：

- 少数人知道边界策略时，知情者会显著占优：他们少花豆、录取率更高、浪费更少。
- 越多人知道，优势会被竞争重新定价：热门课 cutoff 上移，知情策略的边际收益下降。
- 系统总录取率几乎不变，因为课程容量和选课集合大体固定；变化主要发生在“谁被录取”和“多浪费多少豆子”。
- 新公式公开后，市场整体更节制：平均花豆和 posthoc non-marginal beans 下降。
- 但公共知识会制造新拥挤：如果大家都知道同一套边界，热门课的边界会被共同抬高。
- 尾数避让只在少数人使用时可能有用；如果人人都避开 5/2 结尾，13/17/23/27 也会变成新的拥挤尾数。

一句话：**公式从私有优势变成公共知识后，不是让所有人都“免费变强”，而是让市场进入新的价格发现层。**

## 2. 实验设计

本轮只研究“背景学生掌握投豆策略”对市场的影响，不引入 LLM。

固定：

- 数据集：`research_large` high competition，另补 medium 与 sparse-hotspots。
- 人数/课程：`800` students，`240` course sections。
- 轮次：`T1/T2/T3` 三个 time points。
- 课程选择逻辑：仍沿用 Behavioral Agent 的选课集合选择逻辑。
- 改变项：有多少背景学生在选完课后，用公式重新分配 bids。

策略：

| Policy | 含义 |
| --- | --- |
| `behavioral` | 普通 BA，不知道边界公式 |
| `advanced_boundary_v1` | 会用拥挤比边界公式、重要性系数、预算 cap |
| `advanced_boundary_tail_v1` | 在 `advanced_boundary_v1` 基础上避开 0/2/5 常见尾数 |
| `legacy_formula_v1` | 旧流传公式重分配 |

注意：这不是完整 Nash equilibrium。它是“策略知识扩散”的仿真实验，用来观察当更多学生采用同一投豆规则时，市场指标如何变化。

## 3. 高竞争市场：知识扩散曲线

| Market | Formula students | Outcome | Admission | Beans | Rejected waste | Excess | Non-marginal | Hot cutoff p50/p75/p90 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 0% baseline | 0 | 1082.914 | 0.7184 | 91.987 | 21.773 | 40.766 | 62.539 | 11.0 / 14.25 / 19.8 |
| 30% advanced | 240 | 1074.150 | 0.7184 | 87.715 | 23.310 | 33.242 | 56.553 | 11.0 / 16.0 / 21.9 |
| 70% advanced | 560 | 1062.097 | 0.7184 | 82.838 | 27.117 | 18.799 | 45.916 | 12.5 / 18.25 / 24.9 |
| 100% advanced | 800 | 1053.518 | 0.7184 | 79.230 | 31.604 | 6.775 | 38.379 | 15.0 / 20.0 / 25.9 |

解释：

- 总 admission rate 没变，是因为本实验不改变课程供给，且总选课量几乎相同。
- 平均 beans 从 `91.987` 降到 `79.230`，说明边界策略让大家不再盲目花满。
- posthoc non-marginal beans 从 `62.539` 降到 `38.379`，说明公共策略减少了明显无效多投。
- 但热门课 cutoff 明显上移：p75 从 `14.25` 到 `20.0`，p90 从 `19.8` 到 `25.9`。
- 平均 outcome 从 `1082.914` 降到 `1053.518`，说明同一套公开投豆规则会改变席位分配，未必提高整体匹配质量。

这就是二阶博弈的核心：**边界公式公开后，大家确实更会投，但热门课的边界也被所有人一起抬高。**

## 4. 少数知情者优势与优势消退

在高竞争市场中，30% 和 70% 知情时，知情组与普通组表现如下：

| Market | Agent type | Selected | Admission | Beans / selected | Rejected / selected | Excess / selected |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 30% advanced | behavioral | 3575 | 0.671 | 14.44 | 4.18 | 6.10 |
| 30% advanced | behavioral_formula | 1538 | 0.828 | 12.07 | 2.42 | 3.11 |
| 70% advanced | behavioral | 1525 | 0.625 | 14.47 | 4.96 | 5.82 |
| 70% advanced | behavioral_formula | 3588 | 0.758 | 12.32 | 3.94 | 1.72 |

解释：

- 30% 知情时，公式组 admission `0.828`，普通组 `0.671`，优势很明显。
- 70% 知情时，公式组 admission 降到 `0.758`，普通组也被挤到 `0.625`。
- 知情者仍占优，但优势被稀释；市场边界已经开始重新定价。

这说明“知道公式”在早期像私有信息；一旦足够多人知道，它就变成公共知识，收益被竞争吃掉。

## 5. 尾数避让的公共知识问题

高竞争 100% 知情时，对比普通进阶公式和尾数避让版本：

| Policy | Outcome | Beans | Non-marginal | Hot cutoff p50/p75/p90 | 0/2/5 tail share | 3/7 tail share |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| 100% advanced | 1053.518 | 79.230 | 38.379 | 15.0 / 20.0 / 25.9 | 0.2341 | 0.1064 |
| 100% advanced+tail | 1053.835 | 80.323 | 38.996 | 14.5 / 22.0 / 26.0 | 0.0794 | 0.2560 |

尾数避让确实把 0/2/5 结尾从 `23.41%` 压到 `7.94%`，但 3/7 结尾从 `10.64%` 升到 `25.60%`。

这说明：

- 少数人用 13/17/23/27 可能有用。
- 人人都用时，奇怪尾数会变成新的拥挤尾数。
- 因此尾数策略只能作为弱启发，不能写成稳定优势。

## 6. 中等竞争与稀疏热点

| Scenario | Market | Outcome | Admission | Beans | Rejected waste | Excess | Non-marginal | Hot cutoff p50/p75/p90 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| medium | 0% baseline | 1240.038 | 0.8369 | 91.987 | 12.050 | 51.721 | 63.771 | 10.0 / 15.75 / 22.0 |
| medium | 100% advanced | 1207.668 | 0.8369 | 68.986 | 21.381 | 5.947 | 27.329 | 19.0 / 23.0 / 24.5 |
| sparse | 0% baseline | 1347.559 | 0.9218 | 91.987 | 4.920 | 70.341 | 75.261 | 10.0 / 14.0 / 17.8 |
| sparse | 100% advanced | 1329.144 | 0.9218 | 47.965 | 10.916 | 6.189 | 17.105 | 15.0 / 21.0 / 24.2 |

中等和稀疏热点市场里，进阶公式公开后：

- admission rate 不变。
- 平均花豆大幅下降。
- admitted excess 和 non-marginal beans 大幅下降。
- 热门课 cutoff 上升。
- outcome 略降。

这说明低竞争场景里，公式公开最大的价值是减少无意义多投；但少数热点课仍会因为大家更会识别边界而变贵。

## 7. 和旧公式的对照

高竞争 100% 场景：

| Policy | Outcome | Beans | Rejected | Excess | Non-marginal | Hot cutoff p50/p75/p90 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 100% advanced | 1053.518 | 79.230 | 31.604 | 6.775 | 38.379 | 15.0 / 20.0 / 25.9 |
| 100% legacy | 1050.925 | 100.000 | 27.594 | 37.836 | 65.430 | 15.0 / 17.0 / 18.0 |

旧公式公开后的典型问题是：仍然花满预算，admitted excess 很高。进阶公式公开后，学生不再把豆子机械塞满，non-marginal beans 下降很多。

但进阶公式也不是免费午餐：它减少多投，却会让热门课边界更清晰、更硬，导致 rejected waste 在高竞争 100% 场景中上升。

## 8. 机制总结

公开策略会改变博弈层级：

1. **私有信息阶段**：少数学生会估边界，能用更少豆抢到更多课。
2. **扩散阶段**：更多学生开始用同一边界，普通学生被挤压，知情者优势仍在但下降。
3. **公共知识阶段**：所有人都用边界，热门课 cutoff 上移；系统减少浪费，但不保证提高整体 outcome。
4. **反身性阶段**：如果大家还知道“避开 5/2 尾数”，尾数本身也会重新拥挤。

因此公开建议必须写得谨慎：

- 可以说：`m/n` 是最重要的公共竞争信号。
- 可以说：边界公式能减少盲目多投。
- 可以说：少数人使用时优势更明显。
- 不能说：所有人都知道后，公式仍然让每个人都更好。

## 9. 对选课系统设计的启发

如果学校公开更好的边界信息或学生大规模传播边界公式，系统会更像价格发现市场：

- 冷门课低价化：不拥挤的课会越来越接近 1 豆。
- 热门课硬边界化：高竞争课 cutoff 上升，更接近可计算价格。
- 策略优势短期存在，长期被竞争侵蚀。
- 尾数、整数习惯等微观行为会形成新的拥挤点。

这也解释了为什么单一公式永远不够：一旦公式成为公共知识，它就会改变它自己预测的市场。

## 10. 复现命令

示例：

```powershell
python -m src.experiments.run_single_round_mvp `
  --config configs/simple_model.yaml `
  --run-id research_large_advanced_public_share100 `
  --agent behavioral `
  --experiment-group E0_llm_natural_baseline `
  --data-dir data/synthetic/research_large `
  --interaction-mode tool_based `
  --time-points 3 `
  --formula-policy advanced_boundary_v1 `
  --background-formula-share 1.0 `
  --background-formula-policy advanced_boundary_v1
```

尾数避让版本：

```powershell
python -m src.experiments.run_single_round_mvp `
  --config configs/simple_model.yaml `
  --run-id research_large_advanced_tail_public_share100 `
  --agent behavioral `
  --experiment-group E0_llm_natural_baseline `
  --data-dir data/synthetic/research_large `
  --interaction-mode tool_based `
  --time-points 3 `
  --formula-policy advanced_boundary_tail_v1 `
  --background-formula-share 1.0 `
  --background-formula-policy advanced_boundary_tail_v1
```

汇总表生成在本地 `outputs/tables/public_strategy_diffusion_summary.csv`，不提交到仓库。
