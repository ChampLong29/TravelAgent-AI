---
name: hotel_recommender
description: 【SKILL】根据用户需求搜索并推荐合适的酒店，包含价格、位置、评分等关键信息。
version: 1.0.0
author: Travel_Agent_Architect
tags: [hotel, accommodation, search]
---

# hotel_recommender

## Description
根据用户需求搜索并推荐合适的酒店，包含价格、位置、评分等关键信息。

## When to use
当用户需要在某个城市寻找住宿时使用此 Skill。

## Steps

### Step 1: 收集需求
- 确认目标城市、入住日期、天数、人数
- 询问价格档次偏好（经济/商务/豪华）
- 询问位置偏好（市中心/景区附近/商圈）

### Step 2: 搜索酒店
使用 `search_hotel` 工具搜索：
- `city`: 目标城市
- `budget_level`: 根据用户偏好选择 economy/mid/luxury
- `keyword`: 位置关键词（如 "市中心"、"机场附近"）
- `max_results`: 建议 5~8 个

### Step 3: 展示推荐
为每个酒店提供：
- 名称和评分（⭐）
- 地址和位置说明（距主要景点距离）
- 价格区间参考
- 1~2 句推荐理由

### Step 4: 收集反馈
询问用户是否有进一步需求（换一批、筛选条件调整等）

## Output Format
```markdown
## 酒店推荐 - {城市}

### 1. {酒店名称} ⭐{评分}
- 📍 地址：{地址}
- 💰 参考价格：{价格}元/晚
- 🏷️ {推荐理由}

### 2. ...
```

## Notes
- 若 `search_hotel` 返回为空，降低筛选条件重新搜索
- 价格信息可能不完整，提示用户以实际预订价为准
