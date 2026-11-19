# Agent instructions (BabelDOC / TopCircle)

## Pre-commit quality gate

**Always run a strict code-quality review (same bar as `/code-review`) before `git commit` and before `git push`.**

- Do not ship “it works” diffs that grow spaghetti, inflate god files without need, or leave dead/fake APIs.
- Prefer fixing review findings in the same change set over “merge then clean up.”
- If the user explicitly asks to push immediately despite open review issues, call that out and still list residual risks.
- One PR / one concern when possible (do not bundle design docs, unrelated hygiene, and quality fixes in one commit unless asked).

## Dual / operator context

- Primary consumer: PDFMathTranslate-next + DeepLX (non-LLM) dual PDFs.
- Prefer dual visual quality and reproducible midend behavior over large refactors.
- **Output directory convention:** All test renders, rasters, and verification outputs MUST be placed under the project root's git-ignored `tmp/` directory (e.g. `tmp/<task_name>/`), NEVER in the OS root `/tmp/`.
- **Current status / residuals:** `docs/CURRENT-STATUS.md` (index: `docs/PLAN-INDEX.md`).
- **Account handoff prompt:** `GROK_BOT_HANDOFF.md` at repo root — update on every push to `main`.
- Historical wave / layout-first plans live under `docs/archive/` — do **not** schedule from them.

## 排版人工校验与优化铁律 (Manual Layout Audit Rules)

1. **肉眼直接视觉对比是唯一判定标准，严禁盲信脚本与算法工具**
   - 人工校验阶段必须直接肉眼对比中英双栏渲染图。
   - 严禁依赖算法工具（如包围盒交集检测 `bounding box overlap`）盲目判定排版故障。算法常将**行内多 Span 严丝合缝的拼图**或**正常的 L 型自然文字环绕**误报为重叠冲突。
   - **判定准绳**：只有肉眼确凿可见文字碰撞、穿透、重叠遮挡或排版崩坏的，才算缺陷；**肉眼看去版面舒适、文字清晰连贯的，坚决判定为合格**！

2. **坚决杜绝“想当然优化”与“为改而改”，能不动的坚决不动**
   - **视觉无瑕疵，坚决不碰**：凡肉眼视觉无穿帮的页面，100% 保持原版不动，禁止画蛇添足的人工重绘。
   - 盲目擦除重写极易引发连带灾难（如切断周边原本完好的引言字串、破坏原本正确的 L 型环绕、引入省略号截断或字号畸变）。

3. **双栏视觉对照铁律**
   - 封面（Page 1）与目录（Page 2）**绝对原封不动**，严禁擅自修改。
   - 页眉、页脚原始跳过内容**保持原样**，不进行篡改。
   - 严禁任何 `……` 省略号占位或正文截断，译文必须 100% 完整对应英文原版。

4. **外科手术式最小化精准修复**
   - 仅对肉眼确认的真实排版穿帮（如正文横穿侧边栏引言框）做最小范围的手术式修复（精准调整缩进或行间距）。
   - 修复后必须立即渲染全图进行肉眼复核，确认穿帮消除的同时**绝未误伤引言完整性与版面呼吸感**。
