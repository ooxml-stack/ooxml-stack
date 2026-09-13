# 生态仓库清单规格 v3 定稿（实现基线）

状态：**定稿**。相对 v3 的差异集中在 §0；v3 的三项待确认已定稿（§7/§6/§8），
两处契约冲突已按 §2.1 与 §3 消除，tag 检出边界已限定（§4.3）。

范围：只描述 `ooxml-stack/ci/ecosystem-plan.json`（提交）与
`ooxml-stack/ci/reports/scan.json`（不提交）两个产物及其推导规则。
不改任何其他仓库的 CI、Makefile、`pyproject.toml`、`uv.lock`、hook（§11）。

---

## 0. 本版变更（相对 v3）

| # | 变更 | 落点 |
|---|---|---|
| 1 | `version_skew`：先按实际配置的 `(upstream, role)` 全量汇总，policy 只声明"必须一致的范围与例外"，未声明不跳过 | §7 |
| 2 | `corpus data` 边：记录已声明的 release tag 及其来源，同时保留配置中的仓库 SHA，二者分别记录、不做等价比较 | §6 |
| 3 | `ooxml-apps`：纳入节点集合与测试影响图，并保留 `apps → engine` 的 runtime 部分顺序约束；是否参与实际发布由 policy 控制 | §8 |
| 4 | **契约修正 1**：plan 不再表述为"已提交文件内容的纯函数"，改为**选定输入文件路径及其字节内容的确定性函数**；`--write`/`--check` 都读工作区，含未提交修改 | §2.1 |
| 5 | **契约修正 2**：plan 的节点 ID 用**稳定 policy key**；实际 remote / common-dir / checkout 匹配只进 scan；"配置引用未知节点"是结构性错误，"实际仓库与 policy 不一致"是 scan 错误 | §3 |
| 6 | **检出边界**：只有存在已记录的预期 SHA 时才要求检出 tag 指向变化；仅声明 tag 的引用单次扫描只确认当前指向 | §4.3 |

**实现期补充（相对上述定稿，已并入本规格）**

| # | 补充 | 落点 |
|---|---|---|
| 7 | 新增结构性诊断 `missing_input`（error）：policy 明确声明的输入文件缺失时不再静默降级为可选 | §9 |
| 8 | 新增结构性诊断 `source_override_conflict`（error）：`[tool.uv.sources]` 的 ref/URL 与直接声明或 lock 不一致时报告；`uv.sources` 的 ref 优先于直接声明 | §4/§9 |
| 9 | 新增结构性诊断 `unsupported_constraint`（error）：版本约束无法求值时报告，不再静默跳过 | §9 |
| 10 | policy 节点新增 `inputs` 字段，显式声明该节点应有哪些输入文件（`ooxml-stack`、`ooxml-native-corpus` 不是 Python 包，声明为空） | §1/§12 |
| 11 | 完整 SHA 是**必需**事实：`ls-remote` 无法证明其存在，只能由本地对象或显式 `git fetch <sha>` 确认；两者都不可用即 `unverifiable`（required）并阻断 `--write`/`--check` | §4.2 |
| 12 | scan 查询的是**声明中的 URL**，不是目标 checkout 的 origin；两者规范化后不一致时同时报 `policy_repo_mismatch`（`direction=remote_mismatch`） | §3/§4.1 |
| 13 | workflow `uses:` 的 ref 复用同一套 ref 查询与分类，不再按字符串判断 tag/branch/SHA | §4.1/§9 |
| 14 | 测试影响图对所有 policy 节点各给一份反向闭包，而不只是固定根 | §5 |
| 15 | 版本比较**直接委托 `packaging`**（PEP 440 参考实现），不再自行近似；无法求值时返回 `None`（→ `unsupported_constraint`），绝不静默通过 | §7/§9 |
| 16 | `--check` 同样刷新 `ci/reports/scan.json`（写入本次判定与失败原因），使 scan 始终是"最近一次测量的时点快照" | §2 |
| 17 | `full` 绑定记录 job 级与 step 级 `env`（含块式与 flow 式），使"完整验证命令"可复现其运行环境 | §1 |
| 18 | 显式 `branch`/`tag`/`rev` 选择器按其声明种类分类，不再被同名 tag 掩盖；scan 与 plan 共用同一套分类 | §4.1 |
| 19 | workflow `uses:`/`git clone` 指向本生态 owner 但未命中任何 policy 节点时，报结构性 `policy_node_mismatch`（第三方 action 忽略） | §3/§5 |
| 20 | 离线或远端不可达时，CI 引用与包依赖引用一样进入 `unverifiable`（required），不再静默跳过 | §4.2 |
| 21 | lock 中的 git 条目缺少完整 commit SHA 时报 `lock_missing`（error），不再视为已固定 | §4.3/§9 |
| 22 | corpus data 边的 release tag 与代码引用走同一条 ref 查询路径，仅不参与"预期 SHA 对比" | §4.3/§6 |
| 23 | 边去重键包含**规范化 URL 与声明的 selector**：同一 repo 名的不同 owner、或同一 repo 的不同 selector 是两条独立声明，各自保留验证责任；边序由完整键决定，不随声明顺序变化 | §3/§5 |
| 24 | workflow 解析改用成熟安全 YAML 解析器（PyYAML），不再手写标量扫描：注释、转义引号、flow mapping、块标量折叠与 chomping 都按 YAML 语义处理；只读 inventory 承诺的字段；每条 job/step 绑定带来源行 | §1/§9 |
| 25 | 新增结构性诊断 `unsupported_workflow`（error）：YAML 语法错误、非映射的 job/step、非标量的 env 值、重复键、`<<` 合并键等无法在不猜测前提下读取的结构都报出，不静默丢弃、不伪造合法值 | §1/§9 |
| 26 | 工具依赖显式声明并固定版本（`ci/ecosystem-inventory-requirements.txt`）；该文件是选定输入并计入 `inputs_digest`；运行解释器与声明不一致时，在读写任何产物前失败 | §1/§2/§11 |
| 27 | 实际安装版本等环境观测只进 scan；plan 不含任何环境事实 | §1 |
| 28 | 依赖门禁先校验声明**完整**（`packaging`、`PyYAML`、`tree-sitter`、`tree-sitter-bash` 各一条精确 `==` 固定，按 distribution 名规范化，拒绝空/缺项/重复/别名重复/未知包/非精确语法），再比对实际安装版本；空文件或缺项不得读成"无问题" | §2/§11 |
| 29 | 参数解析、工作区定位与依赖预检的导入链只用标准库；`--help` 不需要第三方依赖或有效工作区；预检通过后才导入 `packaging`/`PyYAML`/`tree-sitter` 并解析输入。缺包退出 2 并给出可执行的准备命令，不产生 traceback | §2/§11 |
| 30 | `git clone` 边从 YAML 解析后的 `run` 标量识别（`tree-sitter` bash 语法树切分命令，不执行、不求值）：引号、转义、跨行引用、shell 注释与 `echo` 文本都不会被读成命令；真正的分隔符之后的 `git clone` 仍被识别；单行/literal/folded 写法语义一致；来源行不越过 `run` 节点，折叠写法报节点行而非伪造精确行号 | §5/§9 |
| 31 | `matrix`、`needs`、`runs-on` 的递归结构化转换复用同一套节点校验：嵌套层的重复键、`<<` 合并键、非标准标量 tag 都报 `unsupported_workflow`（带字段位置），不静默覆盖或剥掉 tag | §1/§9 |
| 32 | Actions 表达式（`${{ … }}`）在交给 bash 语法树之前被替换为占位词：表达式不求值，但**保留其参数位置**，因此动态分支参数不会吞掉后面的静态仓库 URL，前一条命令里的表达式也不会吞掉下一条独立 clone；表达式边界识别跳过表达式内部的字符串，不会遇到第一个 `}}` 就截断；占位内容只存在于临时适配文本中，绝不进入 URL、仓库 ID、边或提交产物 | §5/§9 |
| 33 | shell 参数按 shell 语义解码后再识别仓库 URL：裸词的 `\x` 转义、双引号内 `$ \` " \\` 转义与行继续、单引号字面量都得到正确字面参数；`$VAR`/`${VAR}`/`$(…)`/算术展开等运行期求值仍是动态参数，**加双引号不改变这一点**（`"https://…/${REPO}.git"` 与不加引号同样动态），单引号才是字面量 | §5/§9 |
| 34 | 已识别为 `git clone` 但仓库参数无法静态确定时，报 `unsupported_workflow`（error，带原文与来源位置），不猜测目标、不生成虚构边、不报 `policy_node_mismatch`；掩码后仍无法可靠读取的 Bash 区域同样报 `unsupported_workflow`，不以空结果表示"没有依赖"。该规则只针对 clone 的目标参数，不扩大为所有动态 shell 参数。选项按形状识别：`--opt=value`（含动态值）自包含，只占一个位置，不会把后面的静态 URL 当成选项值而漏掉 | §5/§9 |

---

## 1. 产物与自引用

**`ooxml-stack/ci/ecosystem-plan.json`（提交）** — 稳定契约：

- 节点集合（以 policy key 标识，含无边 meta/data 节点）
- 六类边及各自的 ref、`resolved_commit`（仅 pinned ref）、`purpose`
- 每条 full 的 workflow/job/step 绑定（含 job 级与 step 级 `env`；值按 YAML 标量原样记录，
  引号内的逗号、`${{ }}` 表达式与块标量都不截断），每条绑定带它在 workflow 中的**来源行**
- policy 声明摘要（layer、cadence、experimental、visibility、release 参与与否）
- 结构性诊断（§9）
- `inputs_digest`

**不含**：任何 HEAD、worktree 路径、时间戳、网络结果、ref 解析值、本地路径差异。

**`ooxml-stack/ci/reports/scan.json`（不提交，`.gitignore`）** — 时点观测：

- 每个 policy key 对应的实际 remote（规范化）、common-dir、主 checkout 路径
- 全部仓库 HEAD；浮动 ref 当前解析值
- ref 查询结果与失败原因、查询耗时、扫描时间与执行环境
- 瞬时诊断（§9）、alternate worktree 与去重记录

自引用由此消除：提交 plan 只改变 `ooxml-stack` 的 HEAD，而 plan 不记录 HEAD。
`inputs_digest` 覆盖所有选定输入，**排除 `ecosystem-plan.json` 自身**；路径一律相对
`ooxml-projects` 根。选定输入由 policy 显式声明：

- 每个节点用 `nodes[].inputs` 声明该节点应有哪些文件（通常是 `pyproject.toml` + `uv.lock`；
  `ooxml-stack` 与 `ooxml-native-corpus` 不是 Python 包，声明为空）。声明了却不存在 → `missing_input`（error）。
- 各节点的 `.github/workflows/*.yml`，以及 `edge_sources` 指向的 `ci/*.json`。
- `dynamic = {attr = ...}` 的版本源文件（如 `src/docx/__init__.py`）在解析 pyproject 后一并纳入，
  因此只改版本源文件也会改变 `inputs_digest`。
- `ci/ecosystem-inventory-requirements.txt`：固定工具自身的运行依赖版本。它是必需输入，
  因此换一个工具链就必须重新生成 plan（§11）。

---

## 2. `--write` 与 `--check`

```
--write   读取选定输入并写 plan（含结构性诊断）。除非读取/生成失败，退出 0。
          重新生成不会消除诊断——诊断由事实推导，漂移还在就还在。

--check   退出 0 当且仅当：
            (a) 重新生成 plan 与已提交 plan 逐字节一致
            (b) 结构性诊断无 error
            (c) 瞬时诊断无 error，且必需事实无 unverifiable
          --strict 额外把 warning 升级为失败
```

严重级别：

| 级别 | 含义 | `--check` | `--strict` |
|---|---|---|---|
| `error` | 必须修复 | 失败 | 失败 |
| `warning` | 违反政策但可复现 | 通过 | 失败 |
| `unverifiable` | 无法判定（远端不可达、SHA 无法验证等） | 必需事实失败；可选事实通过 | 失败 |
| `info` | 观测 | 通过 | 通过 |

必需事实测量失败时**不覆盖已有 plan**，只写失败 scan report 并非零退出。
`--check` 也刷新 scan report：它是"最近一次测量"的时点观测，写入本次判定（`check.result`、
`check.problems`）与失败原因，无论通过与否。当前生态首次 `--check` 预期失败（§9 有真实 error）；
正向验收必须用无漂移 fixture。

### 2.1 修正 1 — plan 的确定性定义

> **plan 是选定输入文件路径及其字节内容的确定性函数。`--write` 和 `--check` 均读取主
> checkout 的工作区文件，包括未提交修改。**

稳定性要求是**相同输入产生相同输出**，不要求输入已经提交。由此：

- 反例"未提交的 pin 修改必须被 `--check` 检出"成立：plan 由工作区字节推导，
  工作区改了、plan 就不同，逐字节比较即失败（§10 反例 1）。
- 但"提交后的 plan 字节不变"只在**工作区字节不变**时成立。有人在工作区里改动
  未提交内容，重新生成的 plan 就可能不同——这正是 `--check` 要报的漂移，不是缺陷。
- 首次新增、尚未提交的 policy 可以参与生成（否则无法自举）。
- plan 里仍不得出现任何 git/网络/本地状态（§1）：读工作区字节 ≠ 记录 git 状态。

---

## 3. 修正 2 — 节点身份

plan 的节点 ID = **稳定的 policy key**（policy 中声明的逻辑仓库名，默认等于主 checkout
目录名 `<root>/<name>`）。因此：

| 事实 | 归属 |
|---|---|
| 节点 ID（policy key） | plan |
| 依赖边（按 policy key 引用） | plan |
| 实际 remote（规范化）、common-dir、主 checkout、worktree 列表与去重结果 | scan |

诊断按"是否需要看实际 checkout"划分：

- **结构性错误（plan，纯文件推导）**
  - `policy_node_mismatch`（error）：**配置中的依赖引用出现 policy 未声明的节点**，
    即 policy 声明与配置文件推导出的节点集合不一致。反例"从 policy 删除仓库 → 检出"仍成立。
- **scan 错误（进 scan report，同样阻断 `--check`）**
  - `policy_repo_mismatch`（error）：**实际发现的仓库与 policy 不一致**——policy 声明的
    节点缺本地 checkout、出现 policy 未声明的本地仓库、或 remote 规范化结果与 policy 期望不符。
  - `policy_node_mismatch` **不再**依赖 Git 仓库发现结果；凡需实际 checkout 才能判定的，
    一律归 scan。scan 里 `policy_repo_mismatch` 附带 `direction`
    （`missing_checkout` / `undeclared_local` / `remote_mismatch`）与 policy key。

两张图（§5）在 plan 内以 policy key 连接；scan 提供 key → 实际仓库/路径的映射，
供人把诊断落到具体检出目录。common-dir 只用于 scan 内的本地 worktree 去重。

---

## 4. ref 分类与检出边界

### 4.1 按查询结果分类（不看名字）

| 类型 | 判定 | reproducible | 级别 |
|---|---|---|---|
| `annotated_tag` | `refs/tags/X` 存在且 `refs/tags/X^{}` 存在，取 `^{}` 为 commit | 是 | — |
| `lightweight_tag` | `refs/tags/X` 存在、无 `^{}` | 是 | — |
| `full_commit` | 40 位十六进制且对象存在 | 是 | `non_release_ref` warning |
| `branch` | `refs/heads/X` 存在 | 否 | `unreproducible_ref` error |
| `no_ref` | 声明了 git 依赖但无 tag/rev | 否 | `unpinned_dependency` error |
| 查询失败 | 网络/认证失败 | 未知 | `unverifiable` |

### 4.2 确认不存在 vs 无法查询

| 情形 | 判定 | 级别 |
|---|---|---|
| 查询成功，目标 tag 确认不存在 | `missing_ref` | error |
| 查询成功，ref 是分支 | `unreproducible_ref` | error |
| 查询成功，ref 是完整 SHA | `non_release_ref` | warning |
| 网络或认证失败 | `unverifiable` | error（必需事实） |

完整 SHA 的存在性不能用 `ls-remote` 判定（它不列出历史 commit）。验证路径只有两条：
本地仓库已含该对象，或显式 `git fetch <sha>` 成功。两条都不可用 → `unverifiable`，
**绝不报 `missing_ref`**。

### 4.3 检出边界（限定 tag 指向变化）

`lock_commit_mismatch`（error）只在**存在已记录的预期 SHA** 时才可判定：预期 SHA 来自
`uv.lock`、`ci/environment.json` 或 policy 显式 pin；当 ref（含 tag）当前解析 commit
≠ 该预期 SHA 时报出。

仅有 tag 声明、**没有任何预期 SHA** 的引用（例如只写 tag 的 CI 引用、corpus data 引用）：
单次扫描只能**确认当前指向**并记录"无预期 SHA"这一事实，**不声称能检出历史移动**，
不报 `lock_commit_mismatch`。第一阶段保持这个边界，不引入历史快照机制。

---

## 5. 边模型与两张图

边分六类：`runtime`、`dev`、`codegen`、`ci`、`data`、`release`。

底层只写一个 `traverse(graph, start, edge_filter)`，两张图是同一份图上的不同筛选视图：

- **测试影响图**：`kind ∈ {runtime, dev, codegen, ci, data}`，反向闭包，**允许环**。
- **部分发布顺序图**：`kind ∈ {runtime, codegen}`，正向，断言无环。

不写两套重复遍历代码；语义差异只体现在 edge filter 上。两图均以 policy key 表达节点。

---

## 6. 定稿 2 — `ci/environment.json` 与 corpus data 边

`ooxml-operation-engine/ci/environment.json` 固定的是 engine CI 使用的仓库快照，
**归入 `ci` 类**，附 `purpose: engine_ci_snapshot`，**进入测试影响图**（因此
`python-xlsx → engine` 这类影响关系不会丢）。该文件以 SHA 固定 10 个仓库
（`ooxml-apps`、`ooxml-core`、`ooxml-native-corpus`、`ooxml-spec`、`ooxml-stack`、
`ooxml-stubs`、`ooxml-test-framework`、`python-docx`、`python-pptx`、`python-xlsx`），
这些边全部计入。

**`ooxml-native-corpus` 的 `data` 边**（定稿）：

- 记录**已声明的 release tag 及其来源**：tag 名（如 `native-corpus-2026-08-15.1`）、
  声明它的文件与字段路径（来源可复核）。
- **同时保留配置中的仓库 SHA**（engine `environment.json` 里的 corpus commit）。
- **数据发布标识与 Git commit 分别记录，不默认二者代表同一件事**：
  plan 记 `{policy_key, purpose, declared_release_tag, tag_source, pinned_commit}`。
- 第一阶段只记存在性与来源，**不把 tag 与 SHA 做等价比较**，因此不派生
  `lock_commit_mismatch`；scan 只记该 tag 当前能否解析、解析结果，以及"不是 ref"的区分。

**发布顺序表述收紧**：runtime + codegen 图只保证这两类依赖的先后关系；实际发版可能还要求
dev pin 对应的上游 tag 先存在。因此第一步只称其为**部分顺序约束**，不称完整发布顺序。

---

## 7. 定稿 1 — `version_skew` 的比较范围

删除 `dev_runtime_skew`，统一为带作用域的 `version_skew`：

- **先按实际配置中的 `(upstream, role)` 全量汇总**（role ∈ `runtime`/`dev`/`codegen`/`ci`）。
  同组内不同仓库版本不一致 → `version_skew`，级别 **warning**。
- **policy 只声明"必须一致的范围"与"例外"**，例如
  `require_uniform: [{upstream, role, repos?}]`、`exceptions: [{upstream, role, repos, reason}]`。
  未在 policy 声明的分组**不跳过**：仍全部列出并 warning，避免"没配置的分歧被漏报"。
- 记录字段：`upstream`、`role`、`repos[]`（含各自 version/ref）、`scope`
  （是否被 policy 要求一致）、`exceptions_matched[]`。
- **不跨 role 直接判定**：只有违反该仓库声明的版本约束，或与 lock 冲突时才升级为
  `constraint_violation`（error）。

例：core 的 `test-framework v0.5.21` 与 apps 的 `v0.5.37`——docx 的 framework 位于 dev
依赖组（`python-docx/pyproject.toml:38`），由 `uv.sources`（`python-docx/pyproject.toml:133`）
固定，两边都是 dev 角色，只是不同仓库 → `version_skew`（warning），不是 dev/runtime 分歧。

---

## 8. 定稿 3 — `ooxml-apps` 的纳入范围

- **纳入节点集合与测试影响图**（它是实际消费者）。
- **保留 `apps → engine` 的 runtime 部分顺序约束**，即该边进入部分发布顺序图。
- **是否参与实际发布由 policy 控制**（policy 显式声明 release 参与与否）；
  `ooxml-core/scripts/release_stack_support.py` 的 `REPOS`（ooxml-spec、
  ooxml-test-framework、ooxml-core、ooxml-stubs、python-pptx、python-docx）
  **不决定依赖事实**——它是一份内部执行清单，不含 `ooxml-apps`；
  `AUXILIARY_WORKTREES`（`ooxml-native-corpus`、`ooxml-stack`）同理。

---

## 9. 诊断分类表

**结构性诊断（进 plan）**

| code | 级别 | 触发 |
|---|---|---|
| `unpinned_dependency` | error | git 依赖未声明 ref（`ooxml-apps` → engine） |
| `version_skew` | warning | 同 `(upstream, role)` 在不同仓库版本不同（§7 范围） |
| `constraint_violation` | error | pin 违反声明约束或与 lock 冲突 |
| `unsupported_constraint` | error | 版本约束无法求值（如 `^1.0`），不得静默跳过 |
| `lock_missing` | error | 声明了依赖但 lock 中缺失；或 lock 的 git 条目没有完整 commit SHA（无法固定） |
| `source_override_conflict` | error | `uv.sources` 的 ref/URL 与直接声明或 lock 记录的 URL 不一致 |
| `policy_node_mismatch` | error | 配置引用出现 policy 未声明的节点（纯文件推导） |
| `missing_input` | error | policy 明确声明的输入文件缺失（不得降级为可选） |
| `command_source_mismatch` | error | 声明的 full 与 workflow 步骤不一致 |
| `unsupported_workflow` | error | workflow 结构无法在不猜测的前提下读取（YAML 语法错误、非映射的 job/step、非标量的 env 值、重复键、`<<` 合并键、`matrix`/`needs`/`runs-on` 等结构化字段嵌套层里的同类问题、非标准标量 tag、未闭合的 `${{ … }}`、掩码后仍无法解析的 Bash 区域，以及无法静态确定的 `git clone` 仓库参数） |

**瞬时诊断（进 scan report）**

| code | 级别 | 触发 |
|---|---|---|
| `missing_ref` | error | 查询成功且 ref 确认不存在 |
| `unreproducible_ref` | error | ref 是分支 |
| `non_release_ref` | warning | ref 是完整 SHA |
| `lock_commit_mismatch` | error | ref 解析 commit ≠ 已记录的预期 SHA（§4.3） |
| `floating_ci_ref` | error | workflow `uses: ...@main` |
| `policy_repo_mismatch` | error | 实际仓库与 policy 不一致（§3，含 direction） |
| `unverifiable` | error（必需）/ warning（可选） | 查询失败或 SHA 无法验证；离线运行时 CI 引用与包依赖引用同样适用 |
| `duplicate_repo_identity` | info | worktree 去重 |
| `alternate_worktree` | info | 非主 checkout |

**首次扫描的历史漂移（修复前 `--check` 预期失败，见 §10 反例 9）**

修复前 `make ecosystem-plan` 的实测计数（不作为当前诊断数量的断言）：

| code | 级别 | 数量 | 明细 |
|---|---|---|---|
| `unpinned_dependency` | error | 1 | `ooxml-apps` → `ooxml-operation-engine` 无 ref |
| `version_skew` | warning | 2 | `ooxml-core` runtime `0.3.51`/`0.6.0`；`ooxml-test-framework` dev `0.5.21`/`0.5.37` |
| `missing_ref` | error | 3 | `python-docx`/`python-pptx`/`python-xlsx` pin 的 `v0.5.37` 远端不存在（远端最高 `v0.5.35.post1`） |
| `lock_commit_mismatch` | error | 2 | `python-docx`、`ooxml-stubs` 的 lock 记 `b0edf01`，`v0.6.0` 现解析为 `cde719c` |
| `floating_ci_ref` | error | 5 | `ooxml-apps`、`ooxml-stack`、`python-docx`、`python-pptx`、`python-xlsx` 的 `uses: ooxml-stack/...@main` |
| `alternate_worktree` | info | 41 | 本机多 worktree 检出 |

首次扫描只记录问题，不自动修改 pin。2026-09-13 用户另行授权修复这些漂移并提交：

- docx/pptx/xlsx 的 framework 改用原 lock 的完整 SHA
  `347808e0b41cd88a8cb257e809276ec8c35acd0d`，对应 0.5.37，保留现有功能；
  该 commit 已在远端可获取，不依赖尚未发布的本地 tag。
- apps 的 engine 固定为原 lock 的完整 SHA
  `289eee5bac8fb38bc0e589f00a06ceb65293488b`，不升级 engine。
- docx/stubs 的 core lock 由 uv 重新解析为远端 `v0.6.0` 的实际 commit
  `cde719c0c6625da903a38c66752d2fe30995e5b7`，不移动 tag。
- 共享 action 与 reusable workflow 的调用固定为完整 SHA；发布这些本地提交时，
  先推送 stack 的共享 CI 修复提交，再推送调用方。

修复后重新生成 plan，正常在线 `--check` 应退出 0。完整 SHA 仍按既有规则报告
`non_release_ref` warning，版本差异仍报告 `version_skew` warning，未降低检查级别；
`--strict` 因这些 warning 仍可失败。首次扫描的历史失败不能用于解释新的 error。

---

## 10. 验收标准

**正向（无漂移 fixture）**

1. `--write` → 提交 plan → `--check` 退出 0（自引用回归）。
2. annotated tag 正确剥离到 commit。
3. 主 checkout 之外增删 worktree（含同仓库 N 个 worktree）→ plan 字节不变；去重只出现在 scan。
4. 节点集合含无边 meta/data 节点。
5. 连续两次 `--write` 输出逐字节一致。
6. 更换工作区根目录 → plan 字节不变。
7. 增加 alternate worktree → plan 字节不变。
8. **工作区含未提交修改时**连续两次 `--write` 输出一致（相同输入→相同输出）。
9. **plan 结构断言**：不含 remote/common-dir/HEAD/时间/ref 解析字段（§1 的排除项）。
10. **干净环境**：从不继承系统 site-packages 的临时 venv 开始，只按 §11 的步骤准备，
    依赖版本正确、CLI 可启动、无漂移 fixture 的 `--write` → `--check` 返回 0；
    依赖缺失或版本不符时明确失败并保留原 plan。
11. **YAML 端到端**：带行尾注释、转义引号、折叠块与 chomping 的 `env` 完整写入 plan，
    断言具体字段值而不只是退出码。
12. **clone 语义一致**：同一静态 `git clone` 命令写成单行、literal block、folded block 时，
    产生相同的 CI 边，被依赖仓库的反向影响集合都包含消费者；三者都能通过 `--check --strict`。
13. **结构化字段**：合法 `matrix`（含 `include`/`exclude`、anchor/alias、Actions 表达式）
    原样保留；`needs`/`runs-on` 走同一套递归校验。

**反例（必须被拒绝）**

1. 工作区里改了 pin（未提交）→ 重新生成 plan 与已提交 plan 不一致 → `--check` 失败。
2. **存在已记录的预期 SHA 时，tag 指向变化必须检出**（`lock_commit_mismatch`）。
3. lock SHA 与 tag 解析 commit 不一致 → 检出。
4. 分支 ref → `unreproducible_ref`。
5. 无 ref → `unpinned_dependency`。
6. 从 policy 删除仓库 → `policy_node_mismatch`（结构性）。
7. 伪造不存在的 tag → `missing_ref`（查询成功确认不存在），不是 `unverifiable`。
8. 远端网络失败 → `unverifiable`，且必需事实默认失败。
9. 修复前现网首次 `--check` 预期失败，保留历史证据；修复后正常在线 `--check` 必须通过。
10. policy 声明的仓库缺本地 checkout / 出现未声明本地仓库 → `policy_repo_mismatch`（scan，error，阻断）。
11. **边界**：只声明 tag、无预期 SHA 的引用被移动 → **不报** `lock_commit_mismatch`，
    scan 只记录当前指向与"无预期 SHA"；不声称检出历史移动。
12. 非法的 `env` 结构（如值为嵌套映射）→ `unsupported_workflow`，不猜测成字符串。
13. YAML 语法错误 → `unsupported_workflow`，不静默当成空 workflow。
14. 运行解释器的依赖版本与声明不符 → 退出 2，且不覆盖已有 plan。
15. **声明不完整**：空文件、仅注释、缺 `packaging`/`PyYAML`/`tree-sitter`/`tree-sitter-bash`
    任一项、重复项（含 `PyYAML`/`pyyaml` 别名重复）、未知包、非精确语法 → 退出 2，
    plan 与 scan 字节都不变，且不创建新产物。
16. **真正缺包**：不继承系统 site-packages 的临时 venv 里跑 CLI → 退出 2，打印可执行的准备命令，
    无 traceback，plan/scan 不变；`--help` 仍退出 0。
17. **clone 误报**：`run` 之外的 `name`/`with`、YAML 注释、shell 注释、`echo` 中的普通文本、
    引号内的示例命令（含引号里的 `;`/`&`/`|` 与跨行引用）、非 URL 的 `git clone ../local`
    → 不产生 clone 边，也不产生 `policy_node_mismatch`；同一 `run` 中真正的分隔符之后
    紧跟的 `git clone` 仍必须被识别。
18. `matrix` 重复键或自定义 tag（含 `needs`/`runs-on`）→ `unsupported_workflow`（error），
    `--write` 记录该诊断，随后的 `--check` 与 `--check --strict` 都失败。
19. **Actions 表达式适配**：`git clone --branch ${{ inputs.ref }} <url>` 仍产生该 `<url>` 的
    clone 边；`|-`（去掉末尾换行）与 `|` 两种 chomping 下，前一条命令里的
    `${{ format('{0}', github.ref) }}` 都不吞掉下一条独立 `git clone`；表达式内部的字符串
    含 `}}` 时边界不提前截断。以上均无 `unsupported_workflow`，`--check --strict` 退出 0。
20. **静态参数解码**：`git clone https://…/ooxml\-native-corpus.git` 解析为
    `https://…/ooxml-native-corpus.git`，产生正确 clone 边，无 `policy_node_mismatch`。
21. **动态 clone 目标**：仓库参数含 `${REPO}` 或 `${{ inputs.repo }}` → 不产生边、不产生
    `policy_node_mismatch`，产生一条 `unsupported_workflow`（error，含原文与来源位置）；
    `--write` 退出 0 并记录该诊断，`--check` 退出 1。同一 `run` 中独立的静态 `git clone`
    仍保留其边。掩码后仍无法解析的 Bash 区域（如未闭合的 `if`）同样报 `unsupported_workflow`。
22. **引号与等号形式**：`git clone "https://…/${REPO}.git"` 与不加引号一致，报
    `unsupported_workflow`，不报 `policy_node_mismatch`（双引号内的展开仍是动态）；
    `git clone "https://…/ooxml-native-corpus.git"` 仍是静态边。
    `git clone --branch=${{ inputs.ref }} <url>` 与 `--depth=${{ … }}` 一样把 `--opt=value`
    读成自包含选项，仍产生 `<url>` 的 clone 边，`--check --strict` 退出 0。

---

## 11. 范围边界

以下边界针对清单工具本身。§9 记录的 pin/lock/CI 修复另获用户授权；
生成器仍保持只读扫描，不自动修复其他仓库，也不引入 runner、hook、锁或并发机制。

**允许修改**

- `ooxml-stack/Makefile`：新增 `ecosystem-plan` 与 `ecosystem-plan-check`。
- `ooxml-stack/.gitignore`：忽略 `ci/reports/`（scan report 不提交）与工具 venv。
- 新增 `ooxml-stack/ci/ecosystem-policy.json`。
- 新增 `ooxml-stack/ci/ecosystem-inventory-requirements.txt` 与
  `ooxml-stack/ci/ecosystem-inventory-test-requirements.txt`：固定本工具的依赖版本。
- 新增 `ooxml-stack/scripts/ooxml_ci/`。
- 新增 `ooxml-stack/tests/` 下的生态清单测试。
- 生成 `ooxml-stack/ci/ecosystem-plan.json`。
- 本规格文档本身。

**不允许修改**

- 其他任何仓库的 CI、Makefile、`pyproject.toml`、`uv.lock`、hook。
- 不修 pin，不装 hook，不建 runner，不加锁，不做并发。

**运行时依赖**

生成器不自实现版本比较，也不手写 YAML 解析，也不手写 shell 分词。它导入四个第三方包：

- `packaging`（PEP 440 参考实现）——版本约束求值。
- `PyYAML`——workflow 解析。用 `yaml.compose` 只取节点树，不构造对象、不执行任何内容。
- `tree-sitter` + `tree-sitter-bash`——`run` 脚本文本的命令切分。用 bash 语法树定位真正的
  `command` 节点，只读取 `command_name` 与参数子节点，不执行、不求值。

四者都固定版本，声明在 `ci/ecosystem-inventory-requirements.txt`：

```
packaging==26.0
PyYAML==6.0.3
tree-sitter==0.26.0
tree-sitter-bash==0.25.1
```

**为什么 clone 识别用语法树而不是 `shlex`**：`shlex` 会先剥掉引号再切词，于是
`echo ';' git clone …` 里的 `;` 被当成命令分隔符；按行切分还会丢掉跨行引用的上下文，
使多行引号里的示例文本被读成真实命令。语法树保留了引号、转义、分隔符与跨行结构，因此
引号内的 `git clone`、`echo` 文本、shell 注释都不会变成边，而真正的分隔符之后紧跟的
`git clone` 仍然会被识别。

**Actions 表达式不是 shell**：`${{ … }}` 直接交给 bash 语法树会让错误恢复不稳定——
`${{ inputs.ref }}` 会被整段丢掉，于是 `--branch` 吞掉后面的仓库 URL；`|-` 去掉末尾换行
后，前一条命令里的表达式甚至会把下一条 `git clone` 一起吞进 ERROR 节点。因此在解析前把
每个表达式替换成一个普通占位词：表达式不求值，但占位词占据原来的参数位置，语法树因此
始终看到结构良好的命令。占位词只活在临时适配文本里，映射回原文后才用于诊断，绝不进入
URL、仓库 ID、边或提交产物。掩码之后仍有语法错误的区域按 `unsupported_workflow` 报出，
不再容忍——真实生态的 452 个 `run` body 在掩码后全部干净解析。

**不要假设 `pip`/`setuptools` 会提供可导入的顶层 `packaging`**：在 `python -m venv` 创建的
干净环境里 `pip` 存在但 `packaging` 不存在。必须显式准备。

干净环境准备（在**工作区根目录**执行；命令本身会切到 host 仓库）：

```bash
cd ooxml-stack && make ecosystem-inventory-deps
# 等价于：
#   python3 -m venv .venv-ecosystem-inventory
#   .venv-ecosystem-inventory/bin/python -m pip install -r ci/ecosystem-inventory-test-requirements.txt
```

运行（Makefile 目标已指向准备好的解释器，不要用系统 `python3` 直接跑）：

```bash
make ecosystem-plan          # .venv-ecosystem-inventory/bin/python -m scripts.ooxml_ci --write
make ecosystem-plan-check    # .venv-ecosystem-inventory/bin/python -m scripts.ooxml_ci --check
make ecosystem-inventory-test
```

`ci/ecosystem-inventory-test-requirements.txt` 在运行依赖之上加 `pytest==9.0.2`。
`--write`/`--check` **不会**隐式安装或修改环境：解释器与声明不一致时，在任何读写之前退出 2，
打印缺哪个包、哪个版本不符，以及上面的准备命令。失败不覆盖已有 plan，也不创建 scan。

门禁的**第一步是校验声明本身完整**，第二步才比对实际安装版本。声明必须是这两个包各一条精确
`name==version`：空文件、仅注释、缺任一项、重复项（含 `PyYAML`/`pyyaml` 这类别名重复）、
未知包、范围/`===`/extras/marker/`-r` 等非精确语法都报错并退出 2。包名按 distribution 名
规范化后比较。这一步只用标准库，不依赖尚未验证的 `packaging` 导入。

导入链本身也只用标准库：参数解析、工作区定位和依赖预检在 `packaging`/`PyYAML` 可用之前完成，
`--help` 不需要第三方依赖、也不需要有效工作区。因此真正缺包时报的是准备命令，而不是
`ModuleNotFoundError` traceback。预检通过后才导入解析层。

版本漂移会改变判定（例如 `0.7rc1` 是否满足 `>=0.6` 在 `packaging` 21.3 与 26.0 下不同），
所以固定版本是契约的一部分，而不是便利措施。实际安装的版本只进 scan report。

---

## 12. 实现顺序

1. `ci/ecosystem-policy.json`：节点（含 `ooxml-apps` 与 meta/data）、六类边的来源声明、
   `require_uniform`/`exceptions`（§7）、release 参与声明（§8）。
2. `scripts/ooxml_ci/`：输入选定与 digest、policy/config 解析、节点与边推导、
   `version_skew` 分组（§7）、结构性诊断（§9 上半）、plan 序列化（§1/§2.1）。
   模块划分（每文件 ≤300 行、每函数 ≤50 行）：`paths`（工作区布局与根定位，只用标准库，
   供预检使用）、`inputs`（读一次、选输入、digest）、
   `parsers`（pyproject/lock/environment 字节解析）、`yamlnodes`（安全 YAML 节点访问与来源行）、
   `workflows`（workflow 字段提取）、`bashwords`（`run` 的 shell 命令切分、表达式掩码与
   参数解码）、`deps`（固定依赖声明、门禁与 scan 观测，只用标准库）、
   `facts`（facts 容器）、`edges`/`ciedges`（依赖边与 CI 边）、`versions`（约束求值与 skew）、
   `graphs`（两张图）、`full`（full 绑定）、`plan`（plan 组装）、
   `gitfacts`（唯一触碰 git/网络的模块）、`scan`（瞬时诊断）、`cli`（`--write`/`--check`，
   预检前只导入标准库与 `paths`/`deps`）。
3. scan 侧：ref 查询与分类（§4.1–4.2）、预期 SHA 比对（§4.3）、
   `policy_repo_mismatch` 与 worktree 去重（§3）、瞬时诊断（§9 下半）。
4. 两张图的 edge filter 与无环断言（§5）。
5. 测试：§10 全部正向与反例；当前生态的首次 `--check` 作为**预期失败**用例固化成文档说明。
