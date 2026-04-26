# MVP 实验运行流程

本文定义单轮 all-pay MVP 的运行时流程。

## 1. 初始化

实验开始时：

1. 读取 `students.csv`。
2. 读取 `courses.csv`。
3. 读取 `student_course_utility_edges.csv`。
4. 读取 `student_course_code_requirements.csv`。
5. 根据 `requirement_penalty_model` 派生每个学生的 `derived_missing_required_penalty`。
6. 根据学生状态 $\mathbf{s}_i$ 派生 `state_dependent_bean_cost_lambda`，作为实验里的 $\lambda_i(\mathbf{s}_i)$。
7. 为每个学生生成 `student_private_context`。
8. 初始化每个学生预算为100。
9. 初始化每个学生对每个教学班的状态为 `selected=false,bid=0`。
10. 初始化每个教学班当前待选人数为0。

MVP 中的 $\lambda_i(\mathbf{s}_i)$ 不是手填常数。当前可执行近似使用：

- `bean_cost_lambda`：基础豆子影子价格。
- `grade_stage`：年级或毕业紧迫程度。
- `risk_type`：风险偏好。
- 课程代码要求压力：由派生出的未完成惩罚汇总得到。
- `remaining_budget`：剩余预算越少，后续每个豆子的机会成本越高。

这只是第一版代理规则，目的是让代码和问题定义里的“状态依赖影子价格”对得上号；后续可以用实验数据校准或替换这套派生函数。

## 2. 时间点循环

设轮内时间点为：

$$
T=\{1,2,\dots,L\}
$$

MVP 默认：

$$
L=5
$$

每个时间点执行：

1. 使用随机种子生成学生决策顺序。
2. 按顺序逐个学生生成 `state_snapshot`。
3. 调用大模型。
4. 校验输出。
5. 将合法输出应用到平台状态。
6. 更新相关教学班当前待选人数。
7. 写入 `bid_events.csv` 和 `llm_traces.jsonl`。

## 3. 随机顺序

每个时间点内，学生按随机顺序依次决策。

要求：

- 顺序由 `random_seed` 和 `time_point` 决定。
- 同一配置和随机种子必须可复现。
- 不使用固定 `student_id` 顺序，避免固定顺序偏差。

效果：

- 第一个学生看到初始待选人数。
- 第二个学生能看到第一个学生加入或撤出后的待选人数。
- 后续学生持续看到更新后的当前待选人数。
- 所有人仍然看不到其他学生投豆。

## 4. 状态更新规则

一次学生输出可能改变多个教学班的状态。

对每个教学班：

- 若之前 `selected=false`，现在 `selected=true`，当前待选人数加1。
- 若之前 `selected=true`，现在 `selected=false`，当前待选人数减1。
- 若前后都 `selected=true`，只修改投豆，不改变待选人数。
- 若前后都 `selected=false`，不改变待选人数。

注意：

- `selected=true,bid=0` 仍计入待选人数。
- `selected=false,bid=0` 不计入待选人数。
- 修改投豆本身不影响待选人数。

## 5. 截止锁定

最后一个时间点结束后：

- 对每个学生、每个教学班读取最后状态。
- 生成 `decisions.csv`。
- 只使用 `decisions.csv` 进行开奖。
- 历史 `bid_events.csv` 只用于复盘，不参与开奖。

## 6. 开奖规则

对每个教学班独立开奖。

申请者集合：

$$
S_c=\{i:selected_{ic}=true\}
$$

若：

$$
|S_c|\le q_c
$$

则全部录取。

若：

$$
|S_c|>q_c
$$

则按最终 `bid` 从高到低录取前 $q_c$ 人。

边界同分时：

- 找到边界投豆。
- 在边界同分集合中用随机种子抽取剩余名额。
- 记录 `tie_break_used=true`。

## 7. All-Pay 支付

单轮 MVP 中：

$$
beans\_paid_i=\sum_c bid_{ic}^{final}
$$

无论中选与否，最终投出的豆子都消耗。

预算结束值：

$$
budget\_end_i=100-beans\_paid_i
$$

所有豆子字段必须是整数。
