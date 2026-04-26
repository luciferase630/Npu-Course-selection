# synthetic

放第一阶段合成数据，例如模拟学生、模拟课程班、模拟教师、学生-课程班效用边表和模拟培养方案。合成数据用于在没有真实教务数据时跑通模型。

当前仓库不再提交旧样例 CSV。运行实验前先用生成器复现数据：

```powershell
.venv\Scripts\python -m src.data_generation.generate_synthetic_mvp --config configs/simple_model.yaml --preset medium
```

小规模在线 LLM 测试可生成独立目录，避免覆盖默认数据：

```powershell
.venv\Scripts\python -m src.data_generation.generate_synthetic_mvp --config configs/simple_model.yaml --preset custom --n-students 10 --n-course-sections 20 --n-profiles 3 --seed 42
```
