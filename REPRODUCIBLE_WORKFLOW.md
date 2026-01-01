# 可重复研究流程：从原始XLSX到假设验证

本指南详细说明如何从原始血糖监测数据（XLSX格式）到最终假设验证结果的完整可重复流程，确保研究主张的科学性和透明度。

## 📋 目录

1. [数据来源与格式](#数据来源与格式)
2. [数据导入与验证](#数据导入与验证)
3. [创建事件标注](#创建事件标注)
4. [计算事件指标](#计算事件指标)
5. [假设可答性评估](#假设可答性评估)
6. [可视化分析](#可视化分析)
7. [报告生成](#报告生成)

## 数据来源与格式

### 原始文件结构

典型的CGM导出文件（如Freestyle Libre、Dexcom等）包含以下列：

| 列名 | 说明 | 示例 |
|------|------|------|
| 血糖时间 | 测量时间戳 | 2024/1/1 8:00 |
| 血糖值 | 葡萄糖浓度 | 95.2 |

> ⚠️ **注意**：不同设备和软件导出的列名可能不同。本系统使用中文列名"血糖时间"和"血糖值"，如您的文件使用英文，请先在Excel中修改列名。

### 数据质量检查

在导入前，建议检查：

- **时间戳连续性**：是否存在大的时间间隔
- **数值范围**：是否在生理合理范围内（20-600 mg/dL）
- **缺失值**：是否有空白单元格或"--"等标记
- **异常值**：是否有明显错误的数据（如"NaN"、"错误"）

## 数据导入与验证

### 步骤1：导入CGM数据

```bash
# 基本命令
python -m cgm_importer.cli 原始数据.xlsx \
  --subject-id demo_subject_001 \
  --device-id libre_3_sn12345 \
  --timezone Asia/Shanghai

# 带验证的完整命令
python -m cgm_importer.cli 原始数据.xlsx \
  --subject-id demo_subject_001 \
  --device-id libre_3_sn12345 \
  --timezone Asia/Shanghai \
  --output cgm_data.json \
  --validate \
  --pretty
```

### 步骤2：生成数据质量报告

```bash
python -m cgm_importer.sanity_cli cgm_data.json \
  --output sanity_report.json \
  --pretty
```

**报告关键指标解读**：

- **覆盖率**：应 > 90%，否则数据缺口影响分析
- **采样规律性**：变异系数应 < 10%
- **极值**：检查是否有生理不合理的数值
- **可疑变化**：标记快速升降（可能传感器误差）

### 步骤3：人工验证

```python
# 快速检查代码示例
import json

with open('cgm_data.json', 'r') as f:
    cgm = json.load(f)

print(f"总样本数: {len(cgm['samples'])}")
print(f"时间范围: {cgm['samples'][0]['timestamp']} 到 {cgm['samples'][-1]['timestamp']}")
print(f"血糖范围: {min(s['glucose_value'] for s in cgm['samples']):.1f} - {max(s['glucose_value'] for s in cgm['samples']):.1f} mg/dL")
print(f"缺失数据: {sum(1 for s in cgm['samples'] if 'quality_flags' in s and s['quality_flags'])}")
```

## 创建事件标注

### 事件标注原则

**重要概念**：事件是**暴露声明**，不是客观测量

- **主观性**：依赖于受试者记忆和记录
- **质量差异**：不同来源（手动/app）可信度不同
- **时间偏差**：可能存在±15分钟误差
- **剂量不确定性**：碳水化合物估算误差可达±30%

### 步骤1：交互式创建事件

```bash
python -m cgm_events.cli events.json \
  --subject-id demo_subject_001 \
  --timezone Asia/Shanghai \
  --multiple
```

**推荐的事件类型**：
- `meal` - 主要餐食
- `snack` - 零食
- `exercise` - 运动
- `medication` - 用药
- `fasting` - 禁食

### 步骤2：事件质量检查

```python
import json

with open('events.json', 'r') as f:
    events = json.load(f)

for event in events['events']:
    print(f"\n事件: {event.get('label', event['event_id'])}")
    print(f"  时间: {event['start_time']}")
    print(f"  类型: {event['event_type']}")
    print(f"  质量: {event.get('annotation_quality', 'N/A')}")
    if event.get('exposure_components'):
        carbs = [c for c in event['exposure_components'] if 'carb' in c.get('name', '').lower()]
        if carbs:
            print(f"  碳水: {carbs[0]['value']} {carbs[0]['unit']}")
```

### 步骤3：标记问题事件

**低质量事件特征**（annotation_quality < 0.5）：

- 缺少关键信息（如碳水化合物量）
- 时间不确定（例如"大约中午"）
- 无上下文信息（如"在公司"）
- 手动录入（非app自动记录）

**处理策略**：
- 要求受试者补充信息
- 标记为低可信度，分析时加权处理
- 在无法改进时排除

## 计算事件指标

### 步骤1：运行指标计算

```bash
python -m cgm_metrics.cli cgm_data.json events.json \
  --metric-set-id study_week_1 \
  --output metrics.json \
  --verbose
```

### 步骤2：理解各项指标

#### 1. 基线血糖 (baseline_glucose)

```json
{
  "metric_name": "baseline_glucose",
  "value": 96.5,
  "unit": "mg/dL",
  "coverage_ratio": 1.0,
  "window": {
    "relative_to": "event_start",
    "start_offset_minutes": -30,
    "end_offset_minutes": 0
  }
}
```

**解读要点**：
- 窗口：事件前30分钟至事件开始
- 覆盖度：应 > 0.7（即70%期望样本存在）
- 用途：作为后续变化的参照基准

#### 2. 峰值变化 (delta_peak)

```json
{
  "metric_name": "delta_peak",
  "value": 74.0,
  "unit": "mg/dL",
  "quality_summary": {
    "peak_glucose": 170.5,
    "baseline_glucose": 96.5,
    "peak_time": "2024-01-01T08:22:00+08:00"
  }
}
```

**解读要点**：
- 正值：峰值高于基线
- 负值：可能表示血糖下降（罕见）
- 时间戳：帮助判断血糖反应延迟

#### 3. 曲线下面积 (iAUC)

```json
{
  "metric_name": "iAUC",
  "value": 6280,
  "unit": "mg/dL * minutes",
  "quality_summary": {
    "baseline_glucose": 96.5,
    "positive_area": 6280
  }
}
```

**解读要点**：
- 单位：mg/dL × 分钟
- 只计算高于基线的区域
- 代表总血糖暴露量
- 常用于比较不同食物/剂量的影响

#### 4. 达峰时间 (time_to_peak)

```json
{
  "metric_name": "time_to_peak",
  "value": 22,
  "unit": "minutes"
}
```

**解读要点**：
- 从事件开始到血糖峰值的时间
- 反映碳水化合物吸收速度
- 个体差异较大（15-90分钟均正常）

#### 5. 恢复斜率 (recovery_slope)

```json
{
  "metric_name": "recovery_slope",
  "value": -0.85,
  "unit": "mg/dL per minute",
  "quality_summary": {
    "return_toward_baseline_percentage": 82.4
  }
}
```

**解读要点**：
- 负值：血糖正在下降（恢复中）
- 正值：血糖持续上升（未恢复）
- 接近0：稳定平台期

### 步骤3：数据质量检查

**低覆盖度警告**（< 70%）可能原因：
- CGM传感器断连
- 用户手动停止记录
- 事件发生在数据收集边界

**处理策略**：
```python
# 筛选高质量指标
high_quality_metrics = [
    m for m in metrics['metrics']
    if m['quality_summary']['coverage_percentage'] >= 70
]
```

## 假设可答性评估

### 步骤1：定义研究问题

**良好问题的特征**：
- 具体明确："高碳水早餐导致血糖 >180 mg/dL"
- 可测量：有明确的阈值或比较标准
- 时间边界：明确的时间窗口
- 可证伪：存在可能推翻假设的结果

**模糊问题的例子**：
- ❌ "我的血糖控制得好吗"（主观，无标准）
- ✅ "日均血糖变异系数 < 36%的天数占比"

### 步骤2：评估框架

系统从四个维度评估：

#### 1. 数据可用性（Data Availability）

**检查清单**：
- [ ] 足够的事件数量（通常n≥10）
- [ ] 时间跨度充足（至少2周）
- [ ] 变异程度足够（不同条件/剂量）
- [ ] CGM覆盖率 >70%

```json
"data_availability": [
    "已收集12天的早餐事件",
    "CGM覆盖率良好(>90%)",
    "碳水化合物标注完整"
]
```

#### 2. 方法论可行性（Methodology）

**检查清单**：
- [ ] 有明确的分析方法
- [ ] 样本量足够统计功效
- [ ] 可控制混杂因素
- [ ] 效应量可检测

```json
"methodology": [
    "可计算每个事件的ΔPeak值",
    "有足够统计效力判断180mg/dL阈值"
]
```

#### 3. 局限性（Limitations）

**必须记录的限制**：
- 样本量不足
- 缺乏对照组
- 混杂变量未控制
- 无法盲法测量

```json
"limitations": [
    "个体差异可能影响结果",
    "仅包含自我选择的受试者"
]
```

#### 4. 主要问题（Issues）

**导致无法回答的具体障碍**：
- 数据覆盖天数不足
- 缺少关键标注（如运动强度）
- 时间戳不准确
- 混杂变量太多

```json
"issues": [
    "缺少高强度运动数据",
    "运动时长不一致可能干扰"
]
```

### 步骤3：可答性状态判定

**算法逻辑**：

```python
if not all(data_requirements_met):
    status = "unanswerable"
elif methodology_feasible and limitations_minor:
    status = "answerable"
elif can_partially_answer:
    status = "partial"
else:
    status = "unknown"
```

### 步骤4：置信度评分

**多维度加权计算**：

| 维度 | 权重 | 评估标准 |
|------|------|----------|
| 数据完整性 | 40% | 覆盖率、样本量 |
| 方法可靠性 | 30% | 统计功效、效应大小 |
| 控制混杂 | 20% | 混杂因素数量 |
| 时间准确性 | 10% | 时间戳质量 |

**示例**：
- 数据完整性 90% × 0.4 = 0.36
- 方法可靠性 80% × 0.3 = 0.24
- 控制混杂 60% × 0.2 = 0.12
- 时间准确性 70% × 0.1 = 0.07
- **总置信度**：0.36 + 0.24 + 0.12 + 0.07 = **0.79**

## 可视化分析

### 网页应用使用指南

#### 启动应用

```bash
cd /path/to/glyco-map
python3 -m http.server 8000
```

浏览器访问：`http://localhost:8000`

#### 1. 加载数据文件

**上传顺序**：
1. `cgm_data.json` - 血糖时间序列
2. `events.json` - 事件标注
3. `hypotheses.json` - 研究假设（可选）
4. `metrics.json` - 计算指标（可选）

#### 2. 解读可视化

**时间序列图**：
- 蓝色曲线：血糖变化
- 黄色三角：数据质量问题
- 彩色竖线：事件标注
  - 🟢 绿色：餐食
  - 🔵 蓝色：运动
  - 🟡 黄色：用药

**事件详情面板**：
- 事件标签、时间、类型
- 碳水化合物含量（如可用）
- 标注质量百分比
- 上下文标签和备注

**假设面板**：
- 状态标识：可回答/部分/无法/未知
- 置信度条形图
- 点击查看详细推理

**指标面板**（如上传metrics.json）：
- 基线血糖、ΔPeak、iAUC
- 达峰时间、恢复斜率
- 覆盖度警告（<70%显示⚠️）

### 交互式探索

**缩放功能**：
- 滚轮缩放时间轴
- 拖拽平移视图
- 双击重置缩放

**悬停提示**：
- 显示精确血糖值
- 显示时间戳
- 质量问题警告

## 报告生成

### 完整研究报告结构

```
研究_001_报告/
├── 00_数据质量报告.pdf          # 来自sanity_report.json
├── 01_原始数据/
│   ├── cgm_original.xlsx         # 原始导出文件
│   └── cgm_processed.json        # 处理后数据
├── 02_事件标注/
│   ├── events.json               # 所有事件
│   └── events_readme.md          # 标注质量说明
├── 03_计算指标/
│   ├── metrics.json              # 所有指标
│   └── metrics_quality_check.pdf # 低覆盖度事件列表
├── 04_假设验证/
│   ├── hypotheses.json           # 所有研究问题
│   ├── hypothesis_1_detailed.pdf # 可回答问题的完整结果
│   └── hypothesis_3_limitations.pdf # 无法回答的原因
└── 05_可视化/
    ├── chart_interactive.html     # 可交互图表
    └── screenshot_overview.png     # 概览截图
```

### 关键声明的可重复性

#### 示例："高碳水早餐（>60g）导致血糖峰值 >180 mg/dL"

**完整可重复步骤**：

1. **数据准备**（5分钟）：
   ```bash
   # 命令记录在 analysis_commands.sh
   python -m cgm_importer.cli subject_001_jan.xlsx \
     --subject-id subj_001 \
     --device-id libre_3_ab123 \
     --timezone America/Los_Angeles \
     --output cgm_subj_001.json
   ```

2. **事件标注**（10分钟）：
   ```bash
   # 使用交互式工具
   python -m cgm_events.cli events_subj_001.json \
     --subject-id subj_001 \
     --timezone America/Los_Angeles \
     --multiple
   # 标注了23个早餐事件，其中12个碳水>60g
   ```

3. **指标计算**（2分钟）：
   ```bash
   python -m cgm_metrics.cli cgm_subj_001.json events_subj_001.json \
     --metric-set-id breakfast_analysis \
     --output metrics_subj_001.json
   ```

4. **数据筛选**（手动检查）：
   ```python
   import json

   with open('metrics_subj_001.json') as f:
       metrics = json.load(f)

   high_carb_metrics = [
       m for m in metrics['metrics']
       if m['metric_name'] == 'delta_peak'
       and m['event_id'] in ['evt_breakfast_high_carb_list...']  # 高碳水事件ID
   ]

   peak_values = [m['quality_summary']['peak_glucose'] for m in high_carb_metrics]
   baseline_values = [m['quality_summary']['baseline_glucose'] for m in high_carb_metrics]
   exceed_180 = sum(1 for peak in peak_values if peak > 180)

   print(f"高碳水早餐次数: {len(high_carb_metrics)}")
   print(f"峰值>180 mg/dL次数: {exceed_180}")
   print(f"占比: {exceed_180/len(high_carb_metrics)*100:.1f}%")
   ```

5. **统计分析**（Python）：
   ```python
   import scipy.stats as stats

   # 零假设：峰值 ≤ 180 mg/dL
   # 备择假设：峰值 > 180 mg/dL
   t_stat, p_value = stats.ttest_1samp(peak_values, 180)

   print(f"t统计量: {t_stat:.3f}")
   print(f"p值: {p_value:.4f}")

   if p_value < 0.05:
       print("结论：统计显著，高碳水早餐确实导致血糖>180 mg/dL")
   else:
       print("结论：证据不足，不能拒绝零假设")
   ```

6. **可视化验证**（网页）：
   - 打开 `index.html`
   - 上传 `cgm_subj_001.json`
   - 上传 `events_subj_001.json`
   - 在图表上验证高碳水事件对应的血糖峰值

### 版本控制与可重复性清单

**原始数据**：
- [ ] 原始XLSX文件MD5：`md5sum subject_001_jan.xlsx > checksum.txt`
- [ ] 软件版本记录：`pip freeze > requirements.txt`

**处理数据**：
- [ ] 每次处理后更新JSON版本号
- [ ] JSON包含schema版本："schema_version": "1.0.0"
- [ ] 记录所有命令参数

**代码版本**：
- [ ] Git提交所有脚本
- [ ] 标记关键分析节点（git tag -a "v1.0-analysis"
- [ ] 代码仓库公开或提供访问权限

**分析文档**：
- [ ] 记录所有主观决策（如阈值选择）
- [ ] 记录排除的数据及原因
- [ ] 记录软件版本和环境

## 常见问题与解决方案

### 问题1：时间戳时区错误

**症状**：事件时间和血糖数据对不上

**检查**：
```python
# 检查时间戳
with open('cgm_data.json') as f:
    cgm = json.load(f)

for sample in cgm['samples'][:5]:
    print(sample['timestamp'])  # 应有+08:00或+00:00
```

**解决方案**：在导入时使用正确的`--timezone`参数

### 问题2：事件窗口无数据

**症状**：计算指标时提示"No CGM data in window"

**原因**：
- 事件时间戳错误（时区问题）
- CGM数据在该时间段确实有缺失
- 窗口定义过大或过小

**解决方案**：
```bash
# 手动检查特定时间段
python -c "
import json
from datetime import datetime, timedelta

cgm = json.load(open('cgm_data.json'))
event_time = datetime.fromisoformat('2024-01-01T08:00:00+08:00')
window_start = event_time - timedelta(minutes=30)
window_end = event_time + timedelta(minutes=180)

samples = [
    s for s in cgm['samples']
    if window_start <= datetime.fromisoformat(s['timestamp']) <= window_end
]

print(f'窗口内样本数: {len(samples)}')
print(f'期望样本数: {(180+30)/5+1:.0f}')
print(f'覆盖度: {len(samples)/((180+30)/5+1):.1%}')
"
```

### 问题3：指标值异常

**症状**：baseline_glucose或delta_peak不合理

**检查步骤**：
1. 查看窗口覆盖度（coverage_percentage）
2. 检查原始数据点
3. 验证事件时间

**调试代码**：
```python
# 检查特定事件
import json

cgm = json.load(open('cgm_data.json'))
metrics = json.load(open('metrics.json'))

# 找到特定事件的所有指标
event_id = 'evt_breakfast_001'
event_metrics = [m for m in metrics['metrics'] if m['event_id'] == event_id]

for m in event_metrics:
    print(f"{m['metric_name']}: {m['value']} {m['unit']}")
    if m['quality_summary']['coverage_percentage'] < 70:
        print(f"  ⚠️ 警告: 覆盖度仅{m['quality_summary']['coverage_percentage']:.1f}%")
```

## 最佳实践建议

### 数据收集阶段

1. **标准化流程**：
   - 每日固定时间检查CGM装置
   - 事件发生后30分钟内记录
   - 使用统一的食物计量工具

2. **详细标注**：
   ```json
   {
     "label": "燕麦粥配坚果",
     "estimated_carbs": 45,
     "context_tags": ["早餐", "家中", "餐后运动"],
     "notes": "使用电子秤称量30g燕麦",
     "annotation_quality": 0.95
   }
   ```

3. **连续监测**：
   - 至少2周的数据以捕捉周内模式
   - 8周以上以评估周末差异
   - 避免中途更换设备

### 分析阶段

1. **迭代分析**：
   - 先分析简单问题验证流程
   - 逐步增加复杂度
   - 每次分析后更新文档

2. **记录决策**：
   ```markdown
   ## 分析决策日志

   ### 2024-01-15
   - 决定排除annotation_quality < 0.6的事件
   - 理由：低质量标注影响结果可信度
   - 影响：从23个事件中排除5个
   ```

3. **同行评议**：
   - 分享JSON文件而非仅图表
   - 提供完整的reproducible workflow
   - 公开代码和数据（去除隐私信息后）

## 完整示例案例

### 研究问题："高纤维早餐是否降低血糖波动"

#### 1. 数据准备
```bash
# 执行命令（记录在commands.sh）
python -m cgm_importer.cli subject_002_feb.xlsx \
  --subject-id subj_002 \
  --device-id dexcom_g7_def456 \
  --timezone Asia/Shanghai \
  --output cgm_subj002.json

# 质量检查
python -m cgm_importer.sanity_cli cgm_subj002.json \
  --output sanity_subj002.json
```

#### 2. 事件标注
```bash
# 交互式标注，创建高低纤维对比
python -m cgm_events.cli events_subj002.json \
  --subject-id subj_002 \
  --timezone Asia/Shanghai \
  --multiple

# 共标注28个早餐事件：
# - 高纤维（>5g/100g）：15个
# - 低纤维（<2g/100g）：13个
```

#### 3. 指标计算
```bash
python -m cgm_metrics.cli cgm_subj002.json events_subj002.json \
  --metric-set-id fiber_comparison \
  --output metrics_fiber.json
```

#### 4. 统计分析
```python
import json
import scipy.stats as stats

with open('metrics_fiber.json') as f:
    metrics = json.load(f)

# 提取iAUC指标
high_fiber_iauc = []
low_fiber_iauc = []

for m in metrics['metrics']:
    if m['metric_name'] == 'iAUC':
        # 根据事件标签判断纤维含量（简化示例）
        if '高纤维' in m.get('event_label', ''):
            high_fiber_iauc.append(m['value'])
        else:
            low_fiber_iauc.append(m['value'])

# t检验
stat, p_value = stats.ttest_ind(high_fiber_iauc, low_fiber_iauc)

print(f"高纤维早餐平均iAUC: {sum(high_fiber_iauc)/len(high_fiber_iauc):.0f}")
print(f"低纤维早餐平均iAUC: {sum(low_fiber_iauc)/len(low_fiber_iauc):.0f}")
print(f"p值: {p_value:.4f}")

if p_value < 0.05:
    print("结论：高纤维显著降低血糖波动")
else:
    print("结论：无显著差异")
```

#### 5. 可视化报告
```bash
# 生成图表
python -m cgm_metrics.viz_cli cgm_subj002.json events_subj002.json \
  metrics_fiber.json \
  --output report_fiber.pdf \
  --highlight-events high_fiber
```

#### 6. 完整文档
```markdown
## 研究结论

**假设**：高纤维早餐降低餐后血糖波动30%以上

**结果**：
- 高纤维早餐iAUC平均：4,280 mg/dL·min (n=15)
- 低纤维早餐iAUC平均：6,950 mg/dL·min (n=13)
- 降幅：38.4% (p=0.003)

**可重复性**：
- 原始数据：subject_002_feb.xlsx (MD5: abc123...)
- 处理代码：commit d452b72
- 所有中间文件：data/processed/subj002/
```

## 总结

完整可重复流程确保：

1. **透明性**：每个步骤都可追溯
2. **可验证性**：独立研究者可复制
3. **可信度**：数据质量问题显性化
4. **持续改进**：清晰识别需要补充的数据

**核心原则**：研究主张必须从原始数据开始，通过明确定义的中间步骤，最终到达结论。任何环节的跳跃都会降低科学可信度。

---

*本流程遵循FAIR数据原则（可查找、可访问、可互操作、可重用），确保您的研究成果具有持久的科学价值。*
