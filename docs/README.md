# BabelDOC 文档

**操作入口是 [`CURRENT-STATUS.md`](CURRENT-STATUS.md)（2026-10-20）。** 换账号把仓库根目录 [`GROK_BOT_HANDOFF.md`](../GROK_BOT_HANDOFF.md) 全文贴给新助手。两份冲突时以快照日期更新的一方为准，并立刻同步另一份。

## 2026-10-20 布局快照

- 产品改动在 `/Users/yun/workspace/BabelDOC-layout-paradigms`，分支 `plan/layout-paradigms-20261008`，HEAD `d7c5f92`，另有未提交改动。版本仍是 `0.6.4.95`。
- main 在 `/Users/yun/Nextcloud/Project/PDFMathTranslate-next/BabelDOC`，HEAD `398275a`。当前 Grok worktree 同一提交。`/Users/yun/workspace/BabelDOC` 已不在。
- 当前模块 `step/right_spur` 的小腿框填充已过。审查 f24df175 的四项已修，接受的 dual 没有为此重渲。下一模块是 `bow/right_inset`，还没开始。
- 已过的试页、停着的页、以及 2026-10-07 的 main 中段修复，写在 `CURRENT-STATUS.md`。不要从 [`archive/`](archive/) 排期。
- [`PLAN-INDEX.md`](PLAN-INDEX.md) 仍是 2026-09-04 的 main 索引，这次没有改。布局分支的下一步以 `CURRENT-STATUS.md` 的 2026-10-20 节为准。

## BabelDOC Document Intermediate Language

[il_version_1.rnc](https://github.com/funstory-ai/BabelDOC/blob/main/babeldoc/format/pdf/document_il/il_version_1.rnc): The definition of the intermediate language used between PDF parsing and rendering stages.

For other implementation details, please refer to [Implementation Details](ImplementationDetails/README.md).
