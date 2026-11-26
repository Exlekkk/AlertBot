# Draft: Replay live AMST product surface onto main

PR：**#50**（Draft）。分支：`draft/replay-live-product-to-main`。

- **PR URL**：https://github.com/Exlekkk/AlertBot/pull/50
- **产品面提交**：`3f79e8242c4bb02916514e75075f846af5c5ac59`（`Replay live AMST product surface onto main`）
- **本详稿/changelog 提交**：本文件与 CSV 新行一并提交后的分支 HEAD（见该提交 SHA）

## 目的

从当前 `origin/main` 回退已丢弃的 #36–#42 产品线，再重放已经上机的 #43–#49 产品面，让 main 的产品树对齐当前 LIVE `a9075d73d5512ff8aa16678b05f21ef99cf120c9`（短 `a9075d7`，#49）。

这是仓库同步，不是一次新的上机。合入后 LIVE 仍停在 `a9075d7`，本次不改 LIVE、不发上机脚本。

## 为什么不能原样合 #49

#49 对当时 main 是 ahead 16 / behind 8，merge-base 是 #35 金锚 `8e3dbead13eebe32731984bcaa3d77f6fcdb31cf`。直接 merge #49 或把 16 个 LIVE 提交重放到未 revert 的 main 上，会把已丢弃的 #36–#42 缠回来。因此从当前 main 新开分支，先 revert，再按文件取 LIVE 树。

## 做法

1. 起点：`origin/main` `a7ea7a59bb0af73ca75ca83baff667ffd8e1639d`（#46）。
2. 反序 revert 六个已丢弃 squash：#42 `b343966` → #41 `fefc93f` → #40 `65a447e` → #38 `5235ebb` → #37 `c1b7e60` → #36 `bab0440`，再 squash 成一个短英文提交：`Revert discarded product line from #36-#42`。
3. 检出 LIVE 树 `a9075d7`，显式 `git rm` 三个仍留在树上的 `systemd/smct-*`，从 `origin/main` 恢复 `.github/workflows/tests.yml`，保留 #45 的 `docs/drafts/pr-41`…`pr-44` 详稿，changelog 用 LIVE 版。第二个短英文提交：`Replay live AMST product surface onto main`。
4. 开 Draft PR；PR 号出来后再追加本 PR 的 changelog 行和本详稿定名提交。

不要原样 merge #43/#44/#47/#48/#49，也不要顺手合 #39。这些旧 Draft 等本 PR 合进 main 后再标 superseded 关闭。

## 基线 / 回滚

- **LIVE tip（产品面对齐目标）**：`a9075d73d5512ff8aa16678b05f21ef99cf120c9`
- **main 起点**：`a7ea7a59bb0af73ca75ca83baff667ffd8e1639d`
- **代码回滚金锚**：`8e3dbea`（`8e3dbead13eebe32731984bcaa3d77f6fcdb31cf`，#35）
- 更名回滚仍是搬回目录 + 恢复旧 unit / cron / env 副本，**不是**把 tip 滚到 `8e3dbea`

## 合入后 main 应有的样子

- 产品代码面等于 LIVE `a9075d7`（含 AMST 显示名、默认路径和 `amst-*` unit）。
- 两棵树不必完全相等。应留在 main、不必回写 LIVE 的差异：
  - `.github/workflows/tests.yml`（与合入前 `origin/main` 相同 blob）
  - `docs/drafts/pr-41`…`pr-44`（#45 卫生）
  - 本 PR 详稿 `docs/drafts/pr-50-replay-live-product-to-main.md`，以及 changelog 里 #50 的新行
- `systemd/` 只有 `amst-*`，没有 `smct-*`
- #45/#46 文档卫生保留；LIVE 带过来的 `pr-47`…`pr-49` 也保留
- 合入不动 LIVE

## 验收

- `git diff a9075d7 HEAD`：除有意保留项（`tests.yml`、`pr-41`…`pr-44`、本详稿、CSV 新行）外，没有产品代码差异
- `python3 -m unittest discover -s tests -p 'test_*.py' -q` 全绿（193）
- 公开仓纪律：AMST 四字可以出现；不要把策略内容、参数表、交易理念、图表指标、Pine 源码写进仓库或 PR 首页

## Homepage hygiene

PR 标题与合入 `main` 的提交说明保持短英文。长说明只放本文件。
