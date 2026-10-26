---
name: layout-paradigm-workflow
description: >-
  BabelDOC 布局范式开发、缺陷排查与验证的标准化工作流程。
  当用户要求测试新范式、调试排版缺陷（如段落重叠、假居中、排除区错位、钉边不合流、样式标记丢失）、
  运行 dual 试页渲染、核对光栅图或推进范式验收时使用本 Skill。
---

# BabelDOC 布局范式与排版调试工作流程 (Layout Paradigm Workflow)

本指南规范了 BabelDOC 版式范式（`select_paradigm` / `taper` / `spur` / `light_column` / `rect_reflow`）的开发、排查定位、真实双语渲染与验证全过程。

---

## 一、排版范式基本原则与架构定位

1. **范式定位**：
   - 范式是段落放置策略（`RECT_REFLOW`, `SHAPED_POCKET`, `KEEP_CURRENT`），由 `select_paradigm` 根据 `LayoutIntentRole`、`WrapMode` 和源行几何特征计算得出。
   - 不新增平行角色系统，不按范式名称硬编码排版业务分支。低置信度统一落回 `rect_reflow`。
2. **核心管线顺序**：
   `LayoutIntentExtractor`（角色与几何特征识别） 
   → `ExclusionZone` 构建（图文障碍物、CALLOUT 排除区） 
   → `select_paradigm`（标记范式） 
   → `ILTranslator`（翻译并保留 `〖B0〗` 等样式标记） 
   → `Typesetting`（行区间分配、避障排版、段落垂直重叠消解、对齐吸附）。

---

## 二、双语渲染运行环境标准

渲染双语试页时必须遵循以下规范，严防环境污染或缓存失真：

```bash
# 1. 切换到当前布局工作树并设置 PYTHONPATH 指向当前代码
cd /Users/yun/workspace/BabelDOC-layout-paradigms
export PYTHONPATH=/Users/yun/workspace/BabelDOC-layout-paradigms

# 2. 调用专用 Python 虚拟环境执行渲染
/Users/yun/Nextcloud/Project/PDFMathTranslate-next/BabelDOC/.venv/bin/pdf2zh_next \
  --config-file ~/.config/pdf2zh/oa-deeplx.toml \
  --pages <页码> \
  --output <输出目录> \
  "<PDF源路径>"
```

### 渲染纪律：
- 试页默认朝向为 **EN 左 | ZH 右**（Canonical 整本则为 ZH 左 | EN 右，切勿混淆）。
- 绝不要传 `--ignore-cache`，不要 `cat` 大体量翻译日志，不要打印 settings。
- 磁盘空间敏感：严禁整本跑样，输出目录定向到临时目录，验证完毕后清理不必要的过程文件。

---

## 三、常见排版异常排查切入点 (Checklist)

当用户反馈具体页面的排版瑕疵时，按以下树状路径快速归因：

| 异常现象 | 可能根因 | 关键排查位置 |
| :--- | :--- | :--- |
| **标题与正文单行黏连/重叠** | 下方段落向上推移时侵入上方标题锚点 | `midend/typesetting.py` 中的 `_resolve_paragraph_vertical_overlaps`，检查 `is_heading` 锚点保护 |
| **标题或段落被强行居中/推向右侧** | 前序单行小标题误判为 `CALLOUT`，生成了侧栏排除区（ExclusionZone） | `utils/layout_intent_extractor.py`（检查 Rule 8 判定，要求 `n_lines >= 2`） |
| **粗体样式丢失或变成普通文本** | 译后清洗正则过早剥离了 `〖B0〗` 标记 | `utils/mt_token_sanitize.py` 与 `il_translator.py`（检查 `keep_style_markers`） |
| **列宽被右侧无关障碍物截断** | 段落吸附回原始左列时未保留参考宽度 | `midend/typesetting.py` 中的 `_cap_available_with_reference` |
| **锥形（taper）未贴边或短行提前截断** | 源几何波动超出判定阈值或满行数不足 4 行 | `utils/placement_paradigm.py` 与 `line_interval_plan.py` |

---

## 四、目视验证与光栅比对流程

不要仅依赖日志或终端输出，必须生成图片进行视觉审查：

1. **导出测试页光栅图**：
   ```bash
   pdftoppm -png -r 150 -f <页码> -l <页码> "<生成的dual.pdf>" "<输出前缀>"
   ```
2. **截取关注区域（Crop）**：
   利用 Python PIL 或脚本将有问题的段落/小节（如第 4 页底部、第 18 页小标题）单独切片。
3. **Artifact 审查**：
   将切片或高清渲染图写入 Artifact 目录并在会话中查看，重点确认：
   - 中英对齐度与左右栏间距（gutter）；
   - 字符无叠字、下坠或基线错位；
   - 标题粗体及小节序号层级正常；
   - 译文完整无漏译或多余外来语碎屑。

---

## 五、回归测试与代码质量门禁

在提交任何修复或新范式前，必须通过双重门禁：

1. **单元测试与排版测试**：
   ```bash
   /Users/yun/Nextcloud/Project/PDFMathTranslate-next/BabelDOC/.venv/bin/pytest tests/test_placement_paradigm.py tests/test_typesetting.py -q
   ```
2. **代码风格与静态检查**：
   ```bash
   /Users/yun/Nextcloud/Project/PDFMathTranslate-next/BabelDOC/.venv/bin/ruff check .
   ```
3. **严格遵守 `AGENTS.md` 规范**：
   - 实行 Pre-commit 严格代码质量审查，拒绝引入临时补丁或死 API；
   - 相同关注点合并为单个高质量 PR/Commit，遵循 Conventional Commits 规范；
   - 已通过用户确认（“过”）的历史试页目录绝对不要覆盖或重新渲染。

---

## 六、归档与状态同步机制

当范式或缺陷修复完成并得到确认：
1. **同步更新状态文档**：在 `docs/CURRENT-STATUS.md` 中记录本次修复或通过的范式、commit hash、特征与遗留项。
2. **交接文档更新**：若涉及合并到 `main`，同步更新根目录 `GROK_BOT_HANDOFF.md`。
3. **保持基线整洁**：清理本地除通过依据外的无用临时 dual 文件以保留可用磁盘空间。
