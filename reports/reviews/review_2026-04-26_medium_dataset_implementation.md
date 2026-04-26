# 审阅报告：Medium 数据集实现（Codex 修订版）

**审阅时间**：2026-04-26
**审阅对象**：
- spec/06_full_dataset_generation_spec.md（已修订）
- spec/07_full_dataset_distribution_review_spec.md（已修订）
- spec/01_data_inputs.md（已修订）
- data/schemas/dataset_schema.md（已修订）
- src/data_generation/generate_synthetic_mvp.py（已大幅重构）
- tests/test_medium_dataset_generation.py（新增）
**审阅人**：Kimi Agent 2.6

---

## 一、总体结论

**本轮修改质量极高，可直接作为 medium v1 的正式实现。**

核心成果：
- eligible 从 profile 过滤修正为全开放（40*200=8000 条边，全部 eligible=true）
- 培养方案 profile 体系完整落地
- latent factor utility 生成六因子模型落地
- 数据质量保证机制：20 次重试 + validate_medium_dataset 硬约束检查
- 测试覆盖充分：10 个测试用例全部通过
- E0 mock 冒烟跑通，25 个测试全部通过

---

## 二、逐文件审阅详情

### 2.1 spec/06_full_dataset_generation_spec.md

已修复项：
- 引入 profiles.csv 和 profile_requirements.csv
- students.csv 增加 profile_id
- profile_relevance <= 15 已约束
- eligible 全开放已重写
- 时间原子化硬约束已加入
- grade_stage 混合比例已给出
- 容量热门课压低至 30-60

新增亮点：
- 第 7 节明确 requirements 派生逻辑
- generation_metadata.json eligible_count_summary 更新为 200/200/200
- 生成器接口支持 --preset medium

### 2.2 spec/07_full_dataset_distribution_review_spec.md

已修复项：
- profile 完整性检查
- requirements 派生正确性检查
- eligible 全开放检查（新增第 7 节）
- 教师 utility CV 阈值
- utility 边界值占比
- 11-12 量化阈值
- category 时间集中偏差

### 2.3 spec/01_data_inputs.md

- 新增第 1.1 节培养方案表
- students.csv 增加 profile_id
- utility_edges.csv 口径明确全开放
- requirements.csv 派生口径明确

### 2.4 data/schemas/dataset_schema.md

- 新增 profiles.csv 和 profile_requirements.csv
- students.csv 扩展字段完整
- utility_edges 明确完整边表
- 新增 experiment_groups.csv

### 2.5 generate_synthetic_mvp.py

**Course Code Spec 体系**：128 个 course_code，profile_tags 标记相关 profile。

**扩展到 200 course_sections**：weighted_choice 按类别权重多开班，热门基础课容量压到 30-60。

**Profile Requirements 生成**：每个 profile 包含 common_required + common_major + profile_specific_required + strong_electives + optional_targets，不同 profile 的 required 集合有明确差异。

**Utility 六因子生成**：50 + course_quality + teacher_quality + category_affinity + time_affinity + min(15, profile_relevance) + noise，叠加后 clamp 到 [1, 100]。

**数据验证机制**：20 次重试，硬约束检查包括规模、学分、时间、eligible、requirements 回溯、utility 范围等。

**防御性设计**：LEGACY_PROFILE_FIELD 检查防止误用旧字段。

### 2.6 test_medium_dataset_generation.py

10 个测试用例覆盖规模、profile 一致性、requirements 派生、学分、时间、eligible 全开放、utility 范围、deterministic、loader 兼容、自定义输出目录。

---

## 三、代码与文档交叉一致性检查

| 检查项 | 代码 | 文档 | 一致 |
|---|---|---|---|
| eligible 口径 | 8000 条全 true | spec/06 第 8 节 | 是 |
| profile 不过滤 eligible | 代码无过滤逻辑 | spec/06 第 8 节 | 是 |
| profile_relevance 上限 | min(15, ...) | spec/06 第 8 节 | 是 |
| 时间原子化 | 只从 TIME_BLOCKS 选 | spec/06 第 6 节 | 是 |
| 学分 0.5 倍数 | credit*2 是整数 | spec/06 第 5 节 | 是 |
| 5-6 午饭限制 | <= 6% | spec/06/spec/07 | 是 |
| requirements 派生 | join profile_id | spec/06 第 7 节 | 是 |
| deterministic | filecmp 比较 | spec/07 第 9 节 | 是 |
| budget_initial=100 | 代码固定 100 | spec/06 第 4 节 | 是 |
| credit_cap=30 | 代码固定 30 | spec/06 第 4 节 | 是 |
| bean_cost_lambda=1 | 代码固定 1 | spec/06 第 4 节 | 是 |
| risk_type 比例 | 20/10/10 | spec/06 第 4 节 | 是 |
| grade_stage 比例 | 8/16/12/4 | spec/06 第 4 节 | 是 |

---

## 四、潜在风险与建议

### 4.1 低风险（已缓解）

- **容量竞争比**：Foundation 60-140 偏大，但热门基础课已压到 30-60（65% 概率），后续观察 crowding 指标即可。
- **category_affinity 方差**：GeneralElective 均值可能偏高，但现实中通识课方差确实大，后续可通过 metrics 验证。

### 4.2 建议改进（不影响通过）

1. **重试日志**：20 次重试时只保存 last_error，建议添加日志输出每次失败原因。
2. **time_slot 跨天同块**：Mon-1-2|Wed-1-2 在当前设计下不冲突，应确保 spec 明确说明不同天同一时段不冲突。
3. **profile_relevance 对 required 的 boost**：6-15 的 boost 可能让必修课 utility 系统性过高，后续观察 metrics 中 required 课程 average_utility。
4. **students.csv 字段顺序**：当前输出 9 列，loader 读前 6 列。后续 runtime 若需 profile_id，需更新 loader。

---

## 五、未关闭的活跃问题

| 问题 | 状态 | 说明 |
|---|---|---|
| 公式信息组 E4/E5 | 未实现 | 第二阶段扩展，与当前无关 |
| medium 数据生成器 | 已实现 | build_medium_dataset 完成，测试通过 |
| 时间冲突边界 case | 已缓解 | spec/06 已禁止跨块，风险可控 |
| risk_type 语义传递 | 未完全解决 | 系统提示词未解释 conservative/aggressive，属 prompt 工程 |
| metrics 缺失 | 未解决 | overbidding_count 等未加入，属 runtime 增强 |
| spec/00 MVP 范围 | 部分解决 | 已实现功能未写入 spec/00，建议同步 |

---

## 六、结论

**本轮 medium 数据集实现通过审阅。**

所有硬约束均已落实：
- eligible 全开放（8000/8000 = true）
- profile 体系完整（4 profiles，各不相同 required 集合）
- requirements 派生链路自洽
- utility 六因子生成合理
- 时间原子化
- 学分合法
- deterministic
- 测试覆盖完整

建议下一步：
1. 运行 medium 数据生成并查看 generation_metadata.json 中的 utility_summary
2. 将 spec/00 中 MVP 成功标准更新为包含已实现功能
3. 继续推进 E0/E1/E2 实验，用 medium 数据集跑通全链路
