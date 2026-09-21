/* UI strings and the number formatters, en and zh-Hans.

   Observation sentences are composed here from the numbers on the row, in each
   language, exactly as the Swift app will have to compose them: the engine's English
   sentence is a fallback for checking, never the thing translated. */

(function (global) {
  "use strict";

  var PURPOSE_ORDER = [
    "development",
    "research",
    "debugging",
    "conversation",
    "mixed",
    "unknown",
  ];

  var STRINGS = {
    en: {
      app: "Prudence",
      language: "Language",
      theme: "Theme",
      material: "Material",
      standard: "Standard",
      glass: "Glass",
      light: "Light",
      dark: "Dark",
      system: "System",
      gallery: "All screens",
      variant: "Variant",

      overview: "Overview",
      review: "Review",
      observations: "Observations",
      settings: "Settings",

      today: "Today",
      thisWeek: "This week",
      latestObservation: "Latest observation",
      lastIngest: "Last ingest",
      lastReview: "Last review",
      openPrudence: "Open Prudence",
      reviewNow: "Review now",
      ingestNow: "Ingest now",
      settingsEllipsis: "Settings...",
      quit: "Quit",
      sessionsCommits: "{s} sessions, {c} commits",
      noSessionsYet: "No session recorded today",
      minutesAgo: "{n} minutes ago",
      hoursAgo: "{n} hours ago",

      allProjects: "All projects",
      project: "Project",
      range: "Range",
      weeks8: "8 weeks",
      days90: "90 days",
      all: "All",
      sessionsInRange: "Sessions in range",
      activeHours: "Active hours",
      commitsInRange: "Commits in range",
      edits: "{n} edits",
      sittingsNote: "sum of each session's sittings",
      factInferred: "{f} fact, {i} inferred",
      tokensByPurpose: "Tokens by purpose, per week",
      tokensByPurposeSub:
        "Summed from app_usage_by_purpose_day into the ISO week each local day falls in. Click a week to hold its values.",
      whatBecame: "What became of each week's work",
      whatBecameSub:
        "alive_30d / measured_30d and reworked / lines, from app_outcomes_by_week. A week whose 30-day mark has not arrived is a gap, never a zero.",
      whereTime: "Where the hours went",
      whereTimeSub: "One cell per day, shade is active hours. From app_usage_by_purpose_day.",
      aliveAt30: "alive at 30 days",
      lineKey: "solid: alive at 30 days · dashed: reworked later · pale wide: coverage",
      reworkedLater: "reworked later",
      coverageWide: "coverage (pale)",
      coverage: "coverage",
      noWeek: "no measurement",
      week: "Week of {d}",
      tokens: "tokens",
      sessions: "sessions",
      hours: "hours",
      commits: "commits",
      lines: "lines",
      purpose: "Purpose",
      selectWeek: "Week selected: {d}. Click again to release.",
      hoverHint: "Point at a week for its values.",

      writtenBy: "Written by {m}",
      whatThisMeans: "What this means",
      earlierReviews: "Earlier reviews",
      writeAnyway: "Write anyway",
      notReady: "Not enough new work for a review yet",
      notReadySub:
        "The rule waits for 7 days and at least 3 sessions since the last review. You have {d} days and {s} sessions.",
      cancel: "Cancel",
      scope: "scope",
      written: "written",
      figures: "figures",
      outcomeWindow: "outcome window",
      didTitle: "What you did",
      becameTitle: "What became of earlier work",
      observationsTitle: "Observations",
      comparedTitle: "Compared with the previous period",
      suggestionsTitle: "Last time's suggestions",
      thisPeriod: "this period",
      previousPeriod: "previous",
      change: "change",
      showTable: "Show the table",
      hideTable: "Hide the table",
      modelNote:
        "Written by a model over the computed numbers above. Every figure in it appears in this review's numbers list.",

      didSessions: "{n} sessions",
      pooled: "pooled",
      pooledNote:
        "Pooled rows are computed across your projects, for behaviours no single project had the sessions to answer, and are not a finding about any one of them.",
      sortedByGap: "Sorted by the gap between the two medians.",
      did: "did",
      didNot: "did not",
      gap: "gap {n} points",
      methodLine: "coverage {c}, method: {f} fact, {i} inferred",
      nSessions: "{n} sessions",
      medianOf: "median of {n} sessions",
      observationFloor:
        "An observation splits your own sessions in two at one threshold and takes each side's median. It is kept only with at least 5 sessions on each side and at least 10 points between the medians. These are descriptions, not advice.",

      enginePath: "Prudence engine",
      enginePathNote: "Looked for in uv's bin directories, then Homebrew, then your login shell.",
      databasePath: "Database",
      databasePathNote: "Reading {p} (the standard location).",
      foundAutomatically: "found automatically",
      choose: "Choose...",
      clear: "Clear",
      timedIngest: "Ingest every 30 minutes",
      timedIngestNote:
        "Runs prudence ingest in the background. The hooks already spool events; this is what turns them into rows.",
      openAtLogin: "Open at login",
      openAtLoginNote: "Allow Prudence in System Settings > General > Login Items.",
      languageSetting: "Language",
      languageNote:
        "The app's own strings. Engine sentences and the CLI stay English; the app rebuilds observation sentences from the numbers.",
      restartNote: "Takes effect immediately.",
      general: "General",
      data: "Data",
      appearance: "Appearance",

      abTitle: "About Prudence",
      abLede:
        "A local-first, open-source growth coach for developers who build software with AI coding agents. It links how you worked, session by session, to what became of that work in git.",
      abProblem: "The problem",
      abProblem1: "The code works, but the person who shipped it often cannot explain it.",
      abProblem2:
        "Nobody tells them which of their habits lead to good results and which lead to rework. A solo developer has no colleagues, no code review and often no users, so reality's feedback never arrives.",
      abProblem3:
        "Better methods and new techniques exist, but they do not know about them, or do not know how to apply them to what they are doing this week.",
      abProblem4:
        "Their improvement comes mostly from the model getting better, not from themselves. They can feel it, and it is unsettling.",
      abWho: "Who it is for",
      abWhoText:
        "Developers who write software with AI coding agents and whose work lives in git. Solo builders, students and early-career engineers feel the problem most, because they have the least outside feedback.",
      abPromises: "What you get",
      abPromise1: "Reality's feedback, delivered",
      abPromise1Text:
        "It connects how you worked to what happened afterwards: what survived, what was rewritten, where your time and your tokens went. This replaces the colleague and the code review you do not have.",
      abPromise2: "Growth that is yours",
      abPromise2Text:
        "It tracks how your way of working with AI changes, points out what you shipped but did not understand, and helps you close that gap only when you actually need to.",
      abPromise3: "A window to the outside",
      abPromise3Text:
        "It knows what you are working on now, goes out to research how the field solves it today, and explains how that applies to your project, with sources.",
      abHow: "How it works",
      abHowNote:
        "Everything between the sources and the surfaces runs on your machine. Nothing leaves it unless you ask for a model-written paragraph, and then only the computed numbers are sent.",
      abRecord: "Recorded",
      abStoreTitle: "One local store",
      abDerive: "Derived from it",
      abSurfaces: "Read through",
      abSource1: "Claude Code transcripts",
      abSource2: "git hooks",
      abStore: "SQLite, on your machine",
      abD1: "attribution",
      abD2: "outcomes",
      abD3: "session facts",
      abD4: "observations",
      abD5: "reviews",
      abS1: "the CLI",
      abS2: "Claude Code plugin and MCP",
      abS3: "the Mac app",
      abPrinciples: "Four principles",
      abPr1: "The record is yours",
      abPr1Text: "Local, visible, exportable, and dependent on no AI vendor.",
      abPr2: "Your own results are the evidence",
      abPr2Text:
        "Claims about you come only from your own sessions and commits, in the project they came from; a model's impression is not evidence.",
      abPr3: "Facts with their confidence, never scores",
      abPr3Text:
        "Report what happened in counts you can check, each with its coverage and method; say less when the data is thin; never grade, rank, or compare you with other people.",
      abPr4: "Suggestions, never orders",
      abPr4Text:
        "Prudence may suggest; it never forces a mode, a workflow or a curriculum, and it retires advice that does not help.",
      abNot: "What it is not",
      abNot1: "Not a usage dashboard as the selling point.",
      abNot2: "Not surveillance and not a score.",
      abNot3: "Not a forced curriculum.",
      abThis: "This prototype",
      abThis1: "Frozen on 2026-09-20, the M4 design round.",
      abThis2:
        "Every number on the five screens is real: read once from the app_* views on a copy of the founder's store, engine 0.3.0, app contract 2.",
      abThis3:
        "The chosen variants: menu bar C with its block captions, Overview A, Review B, Observations C, Settings B.",
      abThis4: "The mark is A1 at 22.5 degrees, from assets/brand.",
      abThis5:
        "Liquid Glass sits on the control and navigation layer only; cards, tables and charts stay opaque so the figures keep their contrast.",
      abThis6:
        "This file is a record. A later design round makes a new dated file rather than editing this one.",
      purpose_development: "development",
      purpose_research: "research",
      purpose_debugging: "debugging",
      purpose_conversation: "conversation",
      purpose_mixed: "mixed",
      purpose_unknown: "other",
    },

    "zh-Hans": {
      app: "Prudence",
      language: "语言",
      theme: "外观",
      material: "材质",
      standard: "标准",
      glass: "玻璃",
      light: "浅色",
      dark: "深色",
      system: "跟随系统",
      gallery: "全部界面",
      variant: "方案",

      overview: "总览",
      review: "回顾",
      observations: "观察",
      settings: "设置",

      today: "今天",
      thisWeek: "本周",
      latestObservation: "最新观察",
      lastIngest: "上次采集",
      lastReview: "上次回顾",
      openPrudence: "打开 Prudence",
      reviewNow: "立即回顾",
      ingestNow: "立即采集",
      settingsEllipsis: "设置...",
      quit: "退出",
      sessionsCommits: "{s} 个会话，{c} 次提交",
      noSessionsYet: "今天还没有记录到会话",
      minutesAgo: "{n} 分钟前",
      hoursAgo: "{n} 小时前",

      allProjects: "全部项目",
      project: "项目",
      range: "范围",
      weeks8: "8 周",
      days90: "90 天",
      all: "全部",
      sessionsInRange: "范围内会话",
      activeHours: "活跃小时",
      commitsInRange: "范围内提交",
      edits: "{n} 次编辑",
      sittingsNote: "每个会话各次连续工作时长之和",
      factInferred: "{f} 条确证，{i} 条推断",
      tokensByPurpose: "按用途统计的每周 token",
      tokensByPurposeSub:
        "由 app_usage_by_purpose_day 按本地日期所属的 ISO 周汇总。点击某一周可固定显示它的数值。",
      whatBecame: "每周的成果后来怎样了",
      whatBecameSub:
        "alive_30d / measured_30d 与 reworked / lines，来自 app_outcomes_by_week。30 天标记尚未到达的周是断口，不是零。",
      whereTime: "时间花在了哪里",
      whereTimeSub: "每天一格，深浅表示活跃小时。来自 app_usage_by_purpose_day。",
      aliveAt30: "30 天后仍存活",
      lineKey: "实线：30 天后仍存活 · 虚线：后来被返工 · 浅色宽线：覆盖率",
      reworkedLater: "后来被返工",
      coverageWide: "覆盖率（浅色）",
      coverage: "覆盖率",
      noWeek: "无测量",
      week: "{d} 当周",
      tokens: "token",
      sessions: "会话",
      hours: "小时",
      commits: "提交",
      lines: "代码行",
      purpose: "用途",
      selectWeek: "已选中 {d} 当周。再次点击可取消。",
      hoverHint: "把指针移到某一周即可看到数值。",

      writtenBy: "由 {m} 写成",
      whatThisMeans: "这说明了什么",
      earlierReviews: "更早的回顾",
      writeAnyway: "仍然写入",
      notReady: "新的工作量还不足以写一次回顾",
      notReadySub: "规则要求距上次回顾满 7 天且至少 3 个会话。现在是 {d} 天、{s} 个会话。",
      cancel: "取消",
      scope: "范围",
      written: "写于",
      figures: "数字",
      outcomeWindow: "成果窗口",
      didTitle: "你做了什么",
      becameTitle: "更早的工作后来怎样了",
      observationsTitle: "观察",
      comparedTitle: "与上一周期相比",
      suggestionsTitle: "上次的建议",
      thisPeriod: "本周期",
      previousPeriod: "上一周期",
      change: "变化",
      showTable: "显示表格",
      hideTable: "隐藏表格",
      modelNote:
        "由模型基于上面已算出的数字写成。其中出现的每个数字都在这次回顾的数字清单里。",

      didSessions: "{n} 个会话",
      pooled: "跨项目",
      pooledNote:
        "跨项目的行是把你所有项目合在一起算的，用于单个项目样本不足以回答的行为，它不是关于其中任何一个项目的结论。",
      sortedByGap: "按两个中位数之间的差距排序。",
      did: "做了",
      didNot: "没做",
      gap: "相差 {n} 个百分点",
      methodLine: "覆盖率 {c}，方法：{f} 条确证，{i} 条推断",
      nSessions: "{n} 个会话",
      medianOf: "{n} 个会话的中位数",
      observationFloor:
        "一条观察把你自己的会话按某个阈值分成两边，各取中位数。只有两边各至少 5 个会话、且中位数相差至少 10 个百分点时才保留。这些是对已发生事情的描述，不是建议。",

      enginePath: "Prudence 引擎",
      enginePathNote: "依次在 uv 的 bin 目录、Homebrew、你的登录 shell 中查找。",
      databasePath: "数据库",
      databasePathNote: "正在读取 {p}（标准位置）。",
      foundAutomatically: "自动找到",
      choose: "选择...",
      clear: "清除",
      timedIngest: "每 30 分钟采集一次",
      timedIngestNote:
        "在后台运行 prudence ingest。钩子已经把事件排入队列，这一项负责把它们变成记录。",
      openAtLogin: "登录时打开",
      openAtLoginNote: "请在“系统设置 > 通用 > 登录项”中允许 Prudence。",
      languageSetting: "语言",
      languageNote:
        "只影响 App 自己的文案。引擎生成的句子和命令行仍是英文；App 会用数字在界面层重新组织观察句。",
      restartNote: "立即生效。",
      general: "通用",
      data: "数据",
      appearance: "外观",

      abTitle: "关于 Prudence",
      abLede:
        "一个本地优先、开源的成长教练，面向用 AI 编码代理写软件的开发者。它把你一次次会话里的工作方式，和这些工作在 git 里的去向连起来。",
      abProblem: "问题",
      abProblem1: "代码能跑，但交付它的人往往讲不清它。",
      abProblem2:
        "没有人告诉他们，哪些习惯带来好结果，哪些带来返工。独立开发者没有同事、没有代码评审，常常也没有用户，现实的反馈始终到不了他们手里。",
      abProblem3: "更好的方法和新技术是存在的，但他们不知道，或者不知道怎么用到本周手上的活儿里。",
      abProblem4: "他们的进步主要来自模型变强，而不是来自自己。这一点他们能感觉到，而且不安。",
      abWho: "写给谁",
      abWhoText:
        "用 AI 编码代理写软件、工作沉淀在 git 里的开发者。独立开发者、学生和刚入行的工程师感受最深，因为他们能拿到的外部反馈最少。",
      abPromises: "你会得到什么",
      abPromise1: "把现实的反馈送到你面前",
      abPromise1Text:
        "它把你怎么做的，和后来发生了什么连起来：哪些活了下来，哪些被重写，时间和 token 到底花在了哪里。这替代了你没有的同事和代码评审。",
      abPromise2: "属于你自己的成长",
      abPromise2Text:
        "它跟踪你与 AI 协作方式的变化，指出你交付了却没真正理解的部分，并且只在你确实需要时帮你补上。",
      abPromise3: "一扇朝外的窗",
      abPromise3Text:
        "它知道你现在在啃什么，会去查这个领域今天怎么解决它，并说明这些做法怎么用到你的项目上，附来源。",
      abHow: "它怎么工作",
      abHowNote:
        "从来源到出口之间的一切都在你自己的机器上跑。除非你主动要一段模型写的文字，否则没有任何东西离开这台机器；即便那时，送出去的也只是已经算好的数字。",
      abRecord: "记录来源",
      abStoreTitle: "一个本地存储",
      abDerive: "从中推导",
      abSurfaces: "通过这些读取",
      abSource1: "Claude Code 会话记录",
      abSource2: "git 钩子",
      abStore: "SQLite，就在你的机器上",
      abD1: "归属",
      abD2: "成果",
      abD3: "会话事实",
      abD4: "观察",
      abD5: "回顾",
      abS1: "命令行",
      abS2: "Claude Code 插件与 MCP",
      abS3: "Mac App",
      abPrinciples: "四条原则",
      abPr1: "记录是你的",
      abPr1Text: "本地、可见、可导出，不依赖任何 AI 厂商。",
      abPr2: "你自己的结果才是证据",
      abPr2Text:
        "关于你的结论只来自你自己的会话和提交，并且只在它们所属的项目里；模型的印象不算证据。",
      abPr3: "带着置信度的事实，而不是评分",
      abPr3Text:
        "用你能自己核对的计数报告发生了什么，每个数字都带着覆盖率和方法；数据薄的时候就少说；绝不打分、排名，也不拿你和别人比。",
      abPr4: "只做建议，不下命令",
      abPr4Text: "Prudence 可以建议，但从不强制某种模式、流程或课程，并且会淘汰无效的建议。",
      abNot: "它不是什么",
      abNot1: "不以用量看板为卖点。",
      abNot2: "不是监控，也不是评分。",
      abNot3: "不是强制课程。",
      abThis: "关于这份原型",
      abThis1: "冻结于 2026-09-20，M4 这一轮设计。",
      abThis2:
        "五个界面上的每个数字都是真的：从创始人存储副本上的 app_* 视图读出一次，引擎 0.3.0，App 契约 2。",
      abThis3: "选定的方案：菜单栏 C（保留每块的小标签）、总览 A、回顾 B、观察 C、设置 B。",
      abThis4: "标志是 22.5 度的 A1，取自 assets/brand。",
      abThis5:
        "Liquid Glass 只用在控件与导航层；卡片、表格和图表保持不透明，让数字留住对比度。",
      abThis6: "这个文件是一份记录。后面的设计轮次会新建一个带日期的文件，而不是改这一个。",
      purpose_development: "开发",
      purpose_research: "调研",
      purpose_debugging: "调试",
      purpose_conversation: "对话",
      purpose_mixed: "混合",
      purpose_unknown: "其他",
    },
  };

  /* The behaviour split phrases, one per fact in the engine's SPLITS table. The English
     side is word for word what `store/observations.phrases` returns. */
  var SPLIT_PHRASES = {
    en: {
      sittings: "that ran over three or more sittings",
      files_edited_unread: "that edited more files before reading them than your median here",
      formatter_runs: "that ran a formatter",
      test_runs: "that ran tests",
      tests_before_commit: "that ran tests before at least half of their commits",
      commit_attempts_per_commit:
        "that attempted more than two commits for each commit counted",
      repeated_errors: "that hit the same error three times or more",
      subagent_used: "that dispatched a subagent",
      compactions: "that compacted their context",
      context_resets: "that replayed an earlier session's records",
      prompts_per_active_hour:
        "that prompted more often per active hour than your median here",
      hand_edits_between_turns: "that changed the tree by hand between two turns the hooks saw",
    },
    "zh-Hans": {
      sittings: "分三次或更多次进行",
      files_edited_unread: "在阅读之前就改动了较多文件（多于你在这里的中位数）",
      formatter_runs: "运行过格式化工具",
      test_runs: "运行过测试",
      tests_before_commit: "在至少一半的提交之前运行过测试",
      commit_attempts_per_commit: "为每个计入的提交尝试了两次以上提交",
      repeated_errors: "三次或更多次遇到同一个错误",
      subagent_used: "调度过子代理",
      compactions: "压缩过上下文",
      context_resets: "重放过更早会话的记录",
      prompts_per_active_hour: "每活跃小时的提问次数高于你在这里的中位数",
      hand_edits_between_turns: "在钩子看到的两个回合之间手动改动过工作区",
    },
  };

  var SHORT_SPLIT = {
    en: {
      sittings: "3+ sittings",
      files_edited_unread: "edited before read",
      formatter_runs: "ran a formatter",
      test_runs: "ran tests",
      tests_before_commit: "tests before commit",
      commit_attempts_per_commit: "3+ commit attempts",
      repeated_errors: "same error 3 times",
      subagent_used: "used a subagent",
      compactions: "compacted context",
      context_resets: "replayed records",
      prompts_per_active_hour: "above your median",
      hand_edits_between_turns: "hand edits",
    },
    "zh-Hans": {
      sittings: "分三次以上",
      files_edited_unread: "先改后读",
      formatter_runs: "跑了格式化",
      test_runs: "跑了测试",
      tests_before_commit: "提交前跑测试",
      commit_attempts_per_commit: "提交尝试 3 次以上",
      repeated_errors: "同一错误 3 次",
      subagent_used: "用了子代理",
      compactions: "压缩了上下文",
      context_resets: "重放了记录",
      prompts_per_active_hour: "高于你的中位数",
      hand_edits_between_turns: "手动改动",
    },
  };

  var OUTCOME_LABEL = {
    en: { alive_head: "still at head", rework: "reworked later" },
    "zh-Hans": { alive_head: "仍留在 head", rework: "后来被返工" },
  };

  var state = { lang: "en" };

  function lang() {
    return state.lang;
  }

  function setLang(next) {
    state.lang = STRINGS[next] ? next : "en";
    document.documentElement.setAttribute("lang", state.lang === "en" ? "en" : "zh-Hans");
  }

  function t(key, vars) {
    var table = STRINGS[state.lang] || STRINGS.en;
    var text = table[key];
    if (text === undefined) text = STRINGS.en[key];
    if (text === undefined) return key;
    if (!vars) return text;
    return text.replace(/\{(\w+)\}/g, function (whole, name) {
      return Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : whole;
    });
  }

  function purposeLabel(key) {
    return t("purpose_" + key);
  }

  /* --- numbers ---------------------------------------------------------------------- */

  function percent(value) {
    if (value === null || value === undefined) return "-";
    return Math.round(value * 100) + "%";
  }

  function points(value) {
    return Math.round(value * 100);
  }

  function tokens(value) {
    if (value === null || value === undefined) return "-";
    if (value >= 1e9) return (value / 1e9).toFixed(1) + "B";
    if (value >= 1e6) return (value / 1e6).toFixed(1) + "M";
    if (value >= 1e3) return Math.round(value / 1e3) + "k";
    return String(Math.round(value));
  }

  function count(value) {
    return String(value).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }

  function oneDecimal(value) {
    return (Math.round(value * 10) / 10).toFixed(1);
  }

  var MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function shortDate(iso) {
    var parts = String(iso).slice(0, 10).split("-");
    var month = Number(parts[1]);
    var day = Number(parts[2]);
    if (state.lang === "en") return day + " " + MONTHS_EN[month - 1];
    return month + "月" + day + "日";
  }

  function tinyDate(iso) {
    var parts = String(iso).slice(0, 10).split("-");
    return Number(parts[1]) + "/" + Number(parts[2]);
  }

  function longDate(iso) {
    var d = String(iso).slice(0, 10);
    if (state.lang === "en") return d;
    var parts = d.split("-");
    return parts[0] + "年" + Number(parts[1]) + "月" + Number(parts[2]) + "日";
  }

  /* The review headline, composed in the UI layer. `app_review.headline` is built in
     SQL and is always English; the app rebuilds it from the row's own fields so that it
     follows the interface language, exactly as it does with observation sentences. */
  function reviewHeadline(entry) {
    if (state.lang === "zh-Hans") {
      return (
        "回顾 " +
        entry.id +
        "：" +
        entry.project +
        "，" +
        longDate(entry.range_start) +
        " 至 " +
        longDate(entry.range_end)
      );
    }
    return (
      "Review " +
      entry.id +
      ": " +
      entry.project +
      ", " +
      longDate(entry.range_start) +
      " to " +
      longDate(entry.range_end)
    );
  }

  function reviewOption(entry) {
    if (state.lang === "zh-Hans") {
      return "回顾 " + entry.id + " · " + entry.project + " · " + longDate(entry.created_at);
    }
    return "Review " + entry.id + " · " + entry.project + " · " + longDate(entry.created_at);
  }

  function dateRange(a, b) {
    if (state.lang === "en") return longDate(a) + " to " + longDate(b);
    return longDate(a) + " 至 " + longDate(b);
  }

  /* --- observation sentences, composed from the numbers ------------------------------ */

  function observationSentence(row) {
    var lg = state.lang;
    var did = (SPLIT_PHRASES[lg] || SPLIT_PHRASES.en)[row.fact];
    var withText = percent(row.with_value);
    var withoutText = percent(row.without_value);
    if (lg === "zh-Hans") {
      var where = row.pooled ? "在你的各个项目中" : "在 " + row.project + " 项目中";
      var body =
        row.outcome === "rework"
          ? "它们的代码行中位数有 " + withText + " 后来被返工；没有这样做的 " +
            row.without_n + " 个会话为 " + withoutText
          : "它们的代码行中位数有 " + withText + " 仍留在 head；没有这样做的 " +
            row.without_n + " 个会话为 " + withoutText;
      return where + "，你有 " + row.with_n + " 个会话" + did + "，" + body + "。";
    }
    var whereEn = row.pooled ? "Across your projects" : "In " + row.project;
    var bodyEn =
      row.outcome === "rework"
        ? "reworked " + withText + " of their lines (median); the " + row.without_n +
          " that did not, " + withoutText
        : "still have " + withText + " of their lines at head (median); the " + row.without_n +
          " that did not, " + withoutText;
    return whereEn + ", your " + row.with_n + " sessions " + did + " " + bodyEn + ".";
  }

  function observationCaveat(row) {
    return t("methodLine", {
      c: percent(row.coverage),
      f: count(row.fact_commits),
      i: count(row.inferred_commits),
    });
  }

  function splitShort(fact) {
    return (SHORT_SPLIT[state.lang] || SHORT_SPLIT.en)[fact] || fact;
  }

  function outcomeLabel(outcome) {
    return (OUTCOME_LABEL[state.lang] || OUTCOME_LABEL.en)[outcome] || outcome;
  }

  global.I18N = {
    PURPOSE_ORDER: PURPOSE_ORDER,
    STRINGS: STRINGS,
    lang: lang,
    setLang: setLang,
    t: t,
    purposeLabel: purposeLabel,
    percent: percent,
    points: points,
    tokens: tokens,
    count: count,
    oneDecimal: oneDecimal,
    shortDate: shortDate,
    tinyDate: tinyDate,
    longDate: longDate,
    dateRange: dateRange,
    reviewHeadline: reviewHeadline,
    reviewOption: reviewOption,
    observationSentence: observationSentence,
    observationCaveat: observationCaveat,
    splitShort: splitShort,
    outcomeLabel: outcomeLabel,
  };
})(window);
