<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/brand/logo-white.svg">
    <img src="assets/brand/logo.svg" alt="Prudence" width="120">
  </picture>
</p>

<h1 align="center">Prudence</h1>

<p align="center">
  记录你和 AI 编码代理的开发过程，看清代码后来怎么样了，<br>
  把有效的做法带进下一轮。
</p>

<p align="center">
  <a href="https://pypi.org/project/prudence-dev/"><img alt="PyPI" src="https://img.shields.io/pypi/v/prudence-dev?label=prudence-dev"></a>
  <a href="https://github.com/averatec0773/prudence/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/averatec0773/prudence/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/averatec0773/prudence/actions/workflows/mac-ci.yml"><img alt="Mac app" src="https://github.com/averatec0773/prudence/actions/workflows/mac-ci.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-Apache--2.0-blue"></a>
  <img alt="Python 3.12+" src="https://img.shields.io/badge/python-3.12%2B-3776AB">
  <img alt="macOS 14+" src="https://img.shields.io/badge/macOS-14%2B-000">
</p>

<p align="center">
  <a href="README.md">English</a> | 简体中文
</p>

---

## 正循环

用 AI 代理写代码的开发者交付得比以往都快，但大多数人的开发过程没有反馈回路。代码能跑，却没有任何东西告诉你哪种工作方式产出的代码活得久、哪种会被返工，于是下一个会话还是从上一个会话的习惯开始。独立开发者感受最深：没有同事、没有代码审查、常常也没有用户。

Prudence 把这个回路接上。

```
   记录 ──► 关联 ──► 提炼 ──► 调整
    ▲                          │
    └────────── 下一轮 ◄────────┘
```

- **记录。** 读取 AI 编码代理本来就存在磁盘上的会话，原样归档。
- **关联。** 把这些会话产出的每一行代码沿着 git 追踪下去：7、30、90 天后哪些还活着，哪些被重写，token 和时间花在了什么上。
- **提炼。** 把工作方式和结果对上：在你自己的项目里，你自己的哪些习惯和哪些结果同时出现，每个数字都带覆盖率。
- **调整。** 每个周期一份回顾，说明变了什么、可以试什么；下一份回顾告诉你有没有用。有效的留下，无效的丢掉。

每一轮都让下一轮更有依据。记录属于你，留在你的机器上。

## 你会得到什么

- **属于你的记录。** 每个会话逐字节归档在本地，`show`、`forget`、`export` 覆盖全部内容。
- **结果，而不是印象。** 每个会话：7、30、90 天后仍存活的代码行，被你自己后来的提交返工的行，每个数字都带覆盖率和归因方法。
- **按用途统计的用量。** 每个会话的 token 和活跃小时，分成开发、调研、调试、对话，产出零代码的会话不再看起来像一个空洞。
- **观察。** 同一项目内，有某个行为的会话和没有的会话对比："你压缩过上下文的 16 个会话返工了 28% 的代码行，没压缩的 33 个是 6%。" 只在你自己的数据同时过样本下限和差距下限时才报告。
- **回顾。** `prudence review` 把一段时间变成一份存储的回顾，每个数字都是算出来的；可选的模型段落只能引用这些数字，编造数字或做评价会被拒绝。
- **提问。** `prudence ask "为什么我在这个项目上的重构总被撤回"` 从检索到的证据里作答，并引用会话 id。
- **三个入口。** 命令行；带技能和 MCP 服务的 Claude Code 插件；带图表的 macOS 原生菜单栏应用。

## 原则

1. **记录是你的。** 本地、可见、可导出，不依赖任何 AI 厂商。
2. **你自己的结果才是证据。** 关于你的结论只来自你自己的会话和提交，且限定在它们所属的项目；模型的印象不是证据。
3. **事实带着置信度，从不打分。** 你能核对的计数，每个都带覆盖率和方法；没有分数、连击、徽章或排行榜。
4. **只建议，不命令。** Prudence 从不强迫任何模式、流程或课程。

## 安装

需要 Python 3.12 或更高版本和 [uv](https://docs.astral.sh/uv/getting-started/installation/)。

```
uv tool install --python 3.12 "prudence-dev[mcp,model]"
```

可选组件：`mcp` 提供 Claude Code 插件用的 MCP 服务；`model` 提供 Anthropic SDK，用于 `review --explain` 和 `ask` 的文字回答。不装 `model` 时其余功能照常工作，且永远不会调用模型。

macOS 菜单栏应用单独下载：[最新 release](https://github.com/averatec0773/prudence/releases) 里的 DMG（Developer ID 证书就绪前为未签名版，首次启动请右键 → 打开）。也可以从 [apps/mac](apps/mac/README.md) 自行构建。

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

`init --enable` 一次为一个仓库开启记录，`full` 是完整采集，`metadata-only` 只记形状不记内容（适合不想存代码的仓库）。`hooks install` 会修改 Claude Code 的设置文件，先显示差异，`prudence hooks uninstall` 逐字节还原。每次调用模型之前，Prudence 都会打印它将发送的内容：哪些段落、多少个数字、不含对话文本、大小和预估费用。

## Claude Code 插件

```
claude --plugin-dir ./plugin
```

技能 `/prudence:sessions`、`/prudence:outcomes`、`/prudence:usage`、`/prudence:recall`、`/prudence:review`、`/prudence:ask`，以及代理可以直接查询的 MCP 服务（那里的 `ask` 只返回证据，因为调用它的代理本身就是模型）。见 [plugin/README.md](plugin/README.md)。

## macOS 应用

菜单栏图标，下拉显示今天、本周按用途的 token、最新观察和上次回顾；窗口里有总览（每周按用途的 token、各项目的存活与返工及覆盖率、时间花在了哪里）、回顾（存储的回顾以卡片和图表呈现）、观察和设置。Swift 和 Swift Charts，通过一组带版本号的 `app_*` 视图读取同一个 SQLite 库；应用自己不计算任何数字。支持英文和简体中文。见 [apps/mac/README.md](apps/mac/README.md)。

## 记录什么，永不记录什么

原始会话数据原样归档在本地、仅本用户可读的存储里。派生表只存计数、分类和带密钥的行哈希，任何采集级别下都不存消息文本。`metadata-only` 连文件路径和行哈希也不存。任何东西都不会上传；观察只拿你和你自己比。如果打算在工作仓库上启用，请先确认雇主的政策。

## 工作原理

```
AI 编码代理的记录和钩子 ──► 一个本地 SQLite 库（原始归档 + 派生表）
        ──► 归因（哪个会话产出了哪个提交，带置信度）
        ──► 结果（存活、返工）、事实、观察、回顾
        ──► 命令行 · Claude Code 插件与 MCP · macOS 应用（app_* 视图）
```

目录布局和让它易于修改的规则见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 状态

0.3.0。已支持的代理数据源：Claude Code（数据源层按代理一个模块设计）。Windows 未测试。见 [RELEASES.md](RELEASES.md)。

## 参与贡献

欢迎 issue 和 pull request；见 [CONTRIBUTING.md](CONTRIBUTING.md)（DCO 签名、Conventional Commits、仓库内只用英文、AI 辅助的贡献需说明）。仓库本身是英文的，这份中文 README 是唯一的例外。

## 许可证

Apache-2.0，见 [LICENSE](LICENSE)。Prudence 的名称和标志不在代码许可证范围内，见 [assets/brand/README.md](assets/brand/README.md)。
