<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/brand/logo-white.svg">
    <img src="assets/brand/logo.svg" alt="Prudence" width="120">
  </picture>
</p>

<h1 align="center">Prudence</h1>

<p align="center">
  Prudence 把你和 AI 编码代理的每一次合作变成一个成长的正循环：<br>
  看懂代理写的代码，看清时间和 token 花在了哪里、换来的代码后来怎么样了，<br>
  从中学到哪些做法有效，再把它交给下一轮的代理，<br>
  同时留下一份属于你的记录。
</p>

<p align="center">
  <a href="https://pypi.org/project/prudence-core/"><img alt="PyPI" src="https://img.shields.io/pypi/v/prudence-core?label=prudence-core"></a>
  <a href="https://github.com/averatec0773/prudence/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/averatec0773/prudence/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/averatec0773/prudence/actions/workflows/desktop-ci.yml"><img alt="Desktop app" src="https://github.com/averatec0773/prudence/actions/workflows/desktop-ci.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-Apache--2.0-blue"></a>
  <img alt="Python 3.12+" src="https://img.shields.io/badge/python-3.12%2B-3776AB">
  <img alt="macOS 14+" src="https://img.shields.io/badge/macOS-14%2B-000">
</p>

<p align="center">
  <a href="README.md">English</a> | 简体中文
</p>

---

## 要解决的问题

用 AI 代理写代码的开发者交付得比以往都快，但很多人并没有变强。

- 代码能跑，但交付它的人常常解释不了它。
- 没有任何东西告诉他们哪种工作方式产出的代码活得久、哪种会带来返工和 bug。独立开发者没有同事、没有代码审查、常常也没有用户，现实的反馈到不了他们那里。
- 更好的方法是存在的，但他们不知道哪些适用于自己这周正在做的事。
- 他们的进步主要来自模型变强，而不是自己变强，而且他们能感觉到。

## 正循环

你和代理的每一次合作，都成为下一次的依据。

```
   看懂 ──► 看清 ──► 学到 ──► 交给下一轮
    ▲                            │
    └────── 属于你的记录 ◄────────┘
```

- **看懂代理写的代码。** `prudence ask` 用你自己的会话回答关于你自己工作的问题，并引用会话；回顾说明每个周期的会话做了什么、被要求做什么。把代理的工作讲回给你听，是愿景里的第二个承诺，这里是它的起点。
- **看清时间和 token 花在了哪里，换来的代码后来怎么样了。** 每个会话按用途统计 token 和活跃小时；每一行代码沿着 git 追踪：7、30、90 天后是否还活着，是否被你自己后来的提交返工，每个数字都带覆盖率。
- **学到哪些做法有效。** 同一项目内，有某个行为的会话和没有的会话对比，只在你自己的数据同时过样本下限和差距下限时才报告。
- **交给下一轮的代理。** 每个周期一份回顾，说明变了什么、可以试什么，下一份回顾告诉你有没有用；Claude Code 插件和 MCP 服务把这份记录放到代理下一次会话的面前。
- **留下一份属于你的记录。** 每个会话逐字节归档在你的机器上，`show`、`forget`、`export` 覆盖全部内容，不由任何厂商保管。

## 你会得到什么

- **提问。** `prudence ask "为什么我在这个项目上的重构总被撤回"` 从检索到的证据里作答，并引用会话 id。
- **回顾。** `prudence review` 把一段时间变成一份存储的回顾，每个数字都是算出来的；可选的模型段落只能引用这些数字，编造数字或做评价会被拒绝。
- **结果，而不是印象。** 每个会话：7、30、90 天后仍存活的代码行，被你自己后来的提交返工的行，每个数字都带覆盖率和归因方法。
- **按用途统计的用量。** 每个会话的 token 和活跃小时，分成开发、调研、调试、对话，产出零代码的会话不再看起来像一个空洞。
- **观察。** 同一项目内，有某个行为的会话和没有的会话对比："你压缩过上下文的 16 个会话返工了 28% 的代码行，没压缩的 33 个是 6%。" 只在你自己的数据同时过样本下限和差距下限时才报告。
- **三个入口。** 命令行；带技能和 MCP 服务的 Claude Code 插件；一套代码同时面向 macOS 和 Windows 的带图表的桌面菜单栏应用。
- **属于你的记录。** 每个会话逐字节归档在本地，`show`、`forget`、`export` 覆盖全部内容。

## 愿景

三个承诺决定路线图：

1. **把现实的反馈送到你面前。** 哪些活了下来、哪些被重写、哪些坏了、时间和 token 花在了哪里：这是你没有的那个同事和代码审查。
2. **属于你的成长。** 你和 AI 协作的方式在几个月里怎样演变，哪些东西你交付了却没理解，并且只在你需要时帮你补上。建议会被追踪：下一份回顾说明它有没有用，没用的建议被淘汰。
3. **通向外部的窗口。** 知道你此刻在和什么较劲，去看看这个领域今天是怎么解决它的，带着来源解释哪些适用于你的项目。

工具会一直变。这份记录的设计是：新的代理是一个新的数据源，新的分析方法是一个新的视角，新的触达方式是一个新的界面。三年之后，一个开发者应该拥有一份诚实、有证据的记录：每个项目、习惯怎样变化、哪些建议对自己有效，跨越用过的每一代 AI 工具。他们不会放弃它，就像不会放弃自己的 git 历史。

## 原则

1. **记录是你的。** 本地、可见、可导出，不依赖任何 AI 厂商。
2. **你自己的结果才是证据。** 关于你的结论只来自你自己的会话和提交，且限定在它们所属的项目；模型的印象不是证据。
3. **事实带着置信度，从不打分。** 你能核对的计数，每个都带覆盖率和方法；没有分数、连击、徽章或排行榜。
4. **只建议，不命令。** Prudence 从不强迫任何模式、流程或课程。

## 安装

需要 Python 3.12 或更高版本和 [uv](https://docs.astral.sh/uv/getting-started/installation/)。

```
uv tool install --python 3.12 "prudence-core[mcp,model]"
```

可选组件：`mcp` 提供 Claude Code 插件用的 MCP 服务；`model` 提供 Anthropic SDK，用于 `review --explain` 和 `ask` 的文字回答。不装 `model` 时其余功能照常工作，且永远不会调用模型。

桌面应用单独下载：[最新 release](https://github.com/averatec0773/prudence/releases) 里的 DMG（Developer ID 证书就绪前为未签名版，首次启动请右键 → 打开）。也可以从 [apps/desktop](apps/desktop/README.md) 自行构建。

## 快速开始

```
prudence init --scan                      # 列出代理历史里的仓库
prudence init --enable <repo> --level full
prudence ingest                           # 读取代理的记录；第一次会打印"第一眼"
prudence sessions --last 30d
prudence outcomes --project <repo>        # 每个会话的代码行后来怎么样了
prudence usage --last 30d                 # 按用途统计的 token 和小时
prudence observations --project <repo>   # 你的行为对照你自己的结果
prudence review --project <repo>          # 自上次回顾以来这段时间的存储回顾
prudence review --explain                 # 加一段模型写的文字，逐个数字核对
prudence ask "上周的 token 都花在了什么上"
prudence hooks install                    # 可选：通过 Claude Code 钩子记录每轮的 git 状态
prudence export
```

`init --enable` 一次为一个仓库开启记录，`full` 是完整采集，`metadata-only` 只从会话里派生形状、不派生内容（会话原文仍然会被完整归档，见下面"记录了什么、永远不记录什么"）。`hooks install` 会修改 Claude Code 的设置文件，先显示差异，`prudence hooks uninstall` 逐字节还原。每次调用模型之前，Prudence 都会打印它将发送的内容：哪些段落、多少个数字、不含对话文本、大小和预估费用。

## Claude Code 插件

```
claude --plugin-dir ./plugin
```

技能 `/prudence:sessions`、`/prudence:outcomes`、`/prudence:usage`、`/prudence:recall`、`/prudence:review`、`/prudence:ask`，以及代理可以直接查询的 MCP 服务（那里的 `ask` 只返回证据，因为调用它的代理本身就是模型）。见 [plugin/README.md](plugin/README.md)。

## 桌面应用

菜单栏图标，面板显示今天、本周按用途的 token、最新观察和上次回顾；窗口里有总览（每周按用途的 token、各项目的存活与返工及覆盖率、时间花在了哪里）、回顾（存储的回顾以卡片和图表呈现）、观察和设置。它能找到 `prudence` 可执行文件并替你运行采集或回顾，并且跟随数据库的变化，一次运行产生的新数字会自己出现。

macOS 和 Windows 共用一套代码：Rust 外壳包着设计系统自己的 HTML，通过一组带版本号的 `app_*` 视图读取同一个 SQLite 库。**应用自己不计算任何数字**：界面上的每个数字要么是引擎算出的，要么是某个视图若干列的和，要么是同一行两列的比值，没有别的来源。支持英文和简体中文，句子按语言各自组合而不是翻译。见 [apps/desktop/README.md](apps/desktop/README.md)。

## 记录什么，永不记录什么

原始会话数据原样归档在本地、仅本用户可读的存储里。**任何采集级别下都是这样**：级别决定从你的会话里派生出什么，而不是决定保留什么，所以 `metadata-only` 的仓库，会话原文同样被完整归档。

派生表在任何采集级别下都不存消息文本。`full` 级别下，它们确实保存了执行过的命令、被修改文件的路径和工作目录；`metadata-only` 这些都不派生，行哈希也不派生，所以那些表里只有形状和计数。

桌面应用不上传任何内容，观察也只拿你和你自己比。有三个 CLI 命令会触达你配置里指定的模型，每个都需要你主动要求：`prudence review --explain` 和 `prudence explain` 发送的是一次回顾自己的数字，不含会话文本；`prudence ask` 发送的是它检索到的证据，加上 `--with-content` 时还会发送你会话原文的简短摘录。

如果打算在工作仓库上启用，请先确认雇主的政策。

## 工作原理

```
AI 编码代理的记录和钩子 ──► 一个本地 SQLite 库（原始归档 + 派生表）
        ──► 归因（哪个会话产出了哪个提交，带置信度）
        ──► 结果（存活、返工）、事实、观察、回顾
        ──► 命令行 · Claude Code 插件与 MCP · 桌面应用（app_* 视图）
```

目录布局和让它易于修改的规则见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 状态

0.1.0，以 `prudence-core` 名义的第一个版本（引擎此前以 `prudence-dev` 发布的版本在 [RELEASES.md](RELEASES.md) 末尾有概述）。已支持的代理数据源：Claude Code（数据源层按代理一个模块设计）。桌面应用目前只构建了 macOS 版；Windows 未测试。

## 参与贡献

欢迎 issue 和 pull request；见 [CONTRIBUTING.md](CONTRIBUTING.md)（DCO 签名、Conventional Commits、仓库内只用英文、AI 辅助的贡献需说明）。仓库本身是英文的，这份中文 README 是唯一的例外。

## 许可证

Apache-2.0，见 [LICENSE](LICENSE)。Prudence 的名称和标志不在代码许可证范围内，见 [assets/brand/README.md](assets/brand/README.md)。
