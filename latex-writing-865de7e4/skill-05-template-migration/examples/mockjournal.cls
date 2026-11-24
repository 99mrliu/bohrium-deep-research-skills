%% ============================================================================
%% mockjournal.cls
%% 合成示例（synthetic example），非正式案例材料：自造期刊模板类。
%% 仅用于演示模板迁入流程的接口解析、必填项检查与编译验证。
%% ============================================================================
\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{mockjournal}[2026/11/24 v0.1 Mock journal class (synthetic example)]

%% ---- 文档选项 ----
\DeclareOption{twocolumn}{\PassOptionsToClass{\CurrentOption}{article}}
\DeclareOption*{\PassOptionsToClass{\CurrentOption}{article}}
\ProcessOptions\relax

\LoadClass[11pt]{article}

%% ---- 类自带宏包（稿件侧重复加载即构成差异/冲突点）----
\RequirePackage[margin=2.5cm]{geometry}
\RequirePackage{booktabs}
\RequirePackage{graphicx}

%% ---- 禁用宏包（加载期检查）----
\@ifpackageloaded{titlesec}{%
  \ClassError{mockjournal}{Package `titlesec' is not allowed with this class}{%
    The mockjournal class formats section titles itself.}}{}

%% ---- 模板必填字段：期刊名与关键词，缺失时在 \begin{document} 处报错 ----
\newcommand{\journalname}[1]{\gdef\@journalname{#1}}
\let\@journalname\@empty
\newcommand{\keywords}[1]{\gdef\@keywords{#1}}
\let\@keywords\@empty

\AtBeginDocument{%
  \ifx\@journalname\@empty
    \ClassError{mockjournal}{Missing required field: \protect\journalname}{%
      State the journal name in the preamble, e.g. \protect\journalname{Journal Name}.}%
  \fi
  \ifx\@keywords\@empty
    \ClassError{mockjournal}{Missing required field: \protect\keywords}{%
      Provide keywords in the preamble, e.g. \protect\keywords{one, two}.}%
  \fi
}

%% ---- 标题页附印期刊名与关键词 ----
\let\mj@maketitle\maketitle
\renewcommand{\maketitle}{%
  \mj@maketitle
  \begin{center}\small
    \textbf{Journal:} \@journalname\\[2pt]
    \textbf{Keywords:} \@keywords
  \end{center}\vspace{1em}}

\endinput
