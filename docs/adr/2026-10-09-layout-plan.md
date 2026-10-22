# ADR: LayoutPlan 是翻译前冻结的布局契约

## Status

Accepted — 2026-10-09。本切片不切换线上渲染，不修改 `rect_column_reflow.py`。

## Context

`PlacementParadigm` 是三个值的运行时标签。`select_paradigm` 只打标签，不移动字形。未提交的 `rect_column_reflow.py` 在这个标签之外又做了栏填充、翻译前合并段落、展示带、译后挪字，并用模块级 `id()` 缓存。Typesetting 在缩放和渲染时再次调用 `uses_rect_column_fill`。

这和「翻译前扫描、冻结计划、渲染时只消费计划」是反的。语料是 Gabrielle Moore 目录下的英文原稿：递归 131 个 PDF、顶层 101 个目录。文件名含 `.zh` 或 `no_watermark` 的是已生成或手改过的译文，不进扫描。深度受限的 134 份计数不再作为基线。

## Decision

1. 架构中心是不可变的 `LayoutPlan`，不是 `PlacementParadigm`。
2. 管线是只读的：`LayoutFacts` → `Region` → 插件 `PlanContribution` → resolver → 冻结的 `LayoutPlan` → `Typesetting.consume_layout_plan`。
3. `region_id` 由 `source_fingerprint + page_index + source_order + geometry_digest` 的 SHA-256 生成。不使用 `id()`。
4. 第一批插件只提出两种基础策略：`rect_flow`、`shaped_pocket`。几何函数仍用 `placement_paradigm` 里已有的满行、极差和单调性，不复制一套阈值。
5. 没有达到置信度 0.6 的基础策略、角色不是正文或绕图栏、字在图上、输入门不是 `single_page`、或两条基础策略优先级和置信度打平，resolver 一律写成 `preserve`。短锥形、空行、悬挂缩进不再降级成激进的矩形重排。`select_paradigm` 的旧返回值保持不变，供已有测试使用。
6. `fixed_box`、`overlay` 和修饰器只在模型和 resolver 里留接口。本切片没有对应插件，不实现展示带。
7. 插件、resolver、扫描器不得修改 IL、box、段落或字形，不得合并或删除段落。
8. `Typesetting.consume_layout_plan` 仍是唯一的策略读取。它按 `region_id` 返回已冻结的策略，不看角色，不看几何。渲染可以读这个结果，用于 `rect_flow` 和 `list`。栏内顺序来自冻结的 `flow_next_id` 和 `column_chain_id`，列表顺序来自冻结的 `flow_next_id` 和 `list_chain_id`，都不来自 `above_id` / `below_id`。本步不移动 `shaped_pocket`。
9. 语料扫描只读。第一份锁定产物是相对路径加 SHA-256 的 manifest，并校验 131 个原稿 PDF、101 个顶层目录。锁定文件不含本机绝对路径，也不含 `.zh` / `no_watermark` 译文。
10. 逐句重译、术语清洗、项目符号和 CJK 断行不属于本变更集，维持原状，不在这里扩展。

## Consequences

- 新增一种范式时增加插件、gold label 和 resolver 规则，不在 `typesetting.py` 加角色分支。
- `rect_flow` 段落按冻结的栏链接堆叠。`list` 段落按冻结的列表链接往下叠。`shaped_pocket` 保持原位。第 7、9 页不是特例，代码里也不写死这两页。OA p19 / p59 / p91 的冻结测量仍以 `docs/CURRENT-STATUS.md` 为准，本步不重译全书。
- 旧的 `rect_column_reflow.py` 继续留在工作区，直到单独的变更集隔离或撤出它的越界行为。本 ADR 不授权往该文件加功能。

## Acceptance

- 单元测试覆盖稳定栏、四行锥形、过短锥形、悬挂缩进、保留角色、输入门、冲突打平、`region_id` 稳定和消费入口。
- 扫描器对锁定 manifest 计数不一致时非零退出。
- `rect_column_reflow.py` 无本切片差异。
