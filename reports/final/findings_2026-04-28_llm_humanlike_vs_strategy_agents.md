# 大模型学生与策略 Agent 的关键发现

## 一句话结论

在当前 `research_large` 选课竞技场里，CASS 更会赢，LLM 更像人。

## 关键发现

### 1. CASS 是更好的优化器

同一批 80 个被替换学生中：

- behavioral baseline mean outcome：`996.3`
- CASS mean outcome：`1520.2`
- LLM plain mean outcome：`844.5`

CASS 明显提高了课程结果效用，而且没有依赖真实 API。它的价值在于把需求优先级、课程拥挤度、低成本宽松供给组合成稳定策略。

### 2. LLM 更像普通学生

LLM 的行为指标接近 behavioral 学生：

- behavioral mean beans：`92.0`
- LLM mean beans：`89.6`
- behavioral mean selected：`6.40`
- LLM mean selected：`6.18`
- behavioral HHI：`0.210`
- LLM HHI：`0.198`

这说明 LLM 会像学生一样接近花完预算、选有限数量的课、在若干课程上分配注意力，而不是像 CASS 那样系统性铺开低价课程。

### 3. LLM 的“拟人”不等于“更优”

LLM 的 pooled admission rate 高于 behavioral，但 outcome 更低：

- behavioral pooled admission：`0.647`
- LLM pooled admission：`0.715`
- behavioral mean outcome：`996.3`
- LLM mean outcome：`844.5`

这说明 LLM 倾向买到更安全的组合，但不一定买到价值最高或需求最关键的组合。它更像谨慎学生，而不是最优竞价器。

### 4. CASS 的行为很算法化

CASS 的结果好，但行为不像人：

- CASS mean beans：`38.6`
- CASS mean selected：`11.39`
- CASS HHI：`0.117`

普通学生通常不会只花 39 豆、选 11 门课、用很分散的低价覆盖策略。CASS 利用了市场宽松供给结构，这是算法优势，也是拟人性弱点。

### 5. Search 被真实激活，但成本高

在 clean 的 10% LLM run 中：

- 80 个 LLM interaction
- 69 个至少调用一次 `search_courses`
- 平均工具轮数 `6.40`
- total tokens `4,610,224`

这不是形式化 search，而是模型确实在找课、查状态、修正冲突。但这也说明大规模 LLM 市场模拟非常贵。

### 6. Round limit 是真实实验参数

默认 `max_tool_rounds=10` 时，80 个 LLM 学生里有 3 个触发 round limit。提高到 `15` 后干净通过。

这说明后续 LLM cohort 实验必须显式报告工具轮数上限。否则失败率可能是实验壳子造成的，而不是模型能力本身。

## 对 CASS 的启发

CASS 现在不缺 outcome，缺的是拟人性。

下一版可以考虑做 `humanized CASS`：

- 保留 required/progress-blocking 的高优先级判断。
- 增加接近学生的预算使用目标，比如花 75-95 豆，而不是 35-45 豆。
- 控制选课数量，避免过度铺开。
- 提高 bid 集中度，让投豆看起来更像学生在几个关键课程上下注。
- 保留少量探索和次优选择，模拟真实学生的不完全理性。

这会形成三类 agent：

- behavioral：便宜、拟人 proxy、但策略弱。
- CASS：强优化器、可解释、但不像人。
- humanized CASS：介于二者之间，用于拟人市场模拟。

## 对 LLM 的启发

LLM 不适合作为默认选课优化器，但适合做三件事：

- 拟人市场样本：生成学生式预算、搜索、犹豫和修正行为。
- 策略审阅器：解释为什么某个策略不像人，或者为什么某些学生会失败。
- 参数建议器：对 CASS tier table 或 humanized CASS 的参数提出候选，再用 no-API backtest 验证。

## 下一步实验

优先级建议：

1. 写 `humanlikeness_score` 脚本，把拟人性指标自动化。
2. 跑 no-API 的 10% cohort 对照：behavioral_formula、CASS、humanized CASS。
3. 用 20 个学生 x 3TP 跑 LLM，观察动态调整是否更拟人。
4. 如果 primary GPT-5.4 provider 恢复，再重跑小样本，区分 provider 差异与 agent 类型差异。
5. 暂不跑 10% x 3TP LLM 全量，除非先确认成本预算和 provider 稳定性。

## 最终判断

当前竞技场已经能区分两种能力：

- 策略能力：CASS 强。
- 拟人能力：LLM 强。

这对 CASS 后续开发是好消息：我们不需要让 LLM 替代策略 agent，而是可以用 LLM 帮我们定义“人味”，再把这种人味压缩进更便宜、更稳定、更可控的 agent。
