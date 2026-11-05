# Research Agent Lab V0.3：GitHub 云端真实实验配置

本说明对应 Public 仓库 Hu-py/research-agent-lab。**不会改动原科研工作台。**

## 1. GitHub Secrets

进入 GitHub 仓库 Settings → Secrets and variables → Actions → Repository secrets：

| Secret | 用途 |
| --- | --- |
| DEEPSEEK_API_KEY | DeepSeek API 模型调用 |
| LANGFUSE_PUBLIC_KEY | Langfuse 项目 Public Key |
| LANGFUSE_SECRET_KEY | Langfuse 项目 Secret Key |
| OPENALEX_API_KEY | OpenAlex 实时论文检索 |
| SUPABASE_URL | 专用实验 Supabase 项目的 URL |
| SUPABASE_SECRET_KEY | 推荐：新 sb_secret_*，服务器使用 |
| SUPABASE_SERVICE_ROLE_KEY | 兼容旧名称；如果已存 sb_secret_* 在此名称下，也能识别 |

Supabase 后端密钥只需要后两种密钥名的其中一种。若两者都有，
SUPABASE_SECRET_KEY 优先。不要将任何真实密钥提交到 GitHub 源代码。

进入 Actions 的 Variables 页面，可以选填：

- LANGFUSE_BASE_URL：Europe 为 https://cloud.langfuse.com，美国为 https://us.cloud.langfuse.com，日本为 https://jp.cloud.langfuse.com；须与创建的项目区域一致。
- DEEPSEEK_MODEL：默认 deepseek-flash，后续可选择 deepseek-v4-pro。

注意：**GitHub Actions Secrets 不会自动使 CI 执行模型调用**。
真实实验必须手动运行独立工作流。

## 2. Supabase 建表和权限

创建一个与生产数据库隔离的实验项目。

在 Supabase SQL Editor 执行 sql/002_frontier_tables.sql。
运行成功时出现 Success. No rows returned 属正常现象。

新版密钥 sb_secret_* 在 HTTP 请求中使用 apikey 请求头；
**不可用 Authorization: Bearer sb_secret_...**。
本版本已适配，旧版 service_role JWT 继续支持。

真实实验在收费的 DeepSeek 调用前先检查：
- GitHub Secrets 非空
- 服务器端 Supabase Key 类型正确
- 实验表 lab_frontier_runs 可通过 PostgREST 读取
- lab_frontier_feedback 可以读取历史评价

如果表或者密钥错误，实验提前失败，不执行模型推理。

## 3. 第一次云端实验（公开通用画像）

1. 打开 GitHub 仓库 → Actions。
2. 左侧选择 Live Research Agent Lab (manual)。
3. 点击 Run workflow，分支选择 main。
4. 推荐首次参数：

| 参数 | 首次推荐 | 含义 |
| --- | --- | --- |
| evidence_source | public_demo | 只用公开、通用的城市科研画像 |
| max_generations | 0 | 暂不追加进化，先验证完整首次竞赛 |
| max_papers | 6 | OpenAlex 论文数量上限 |
| max_pairs | 2 | 两组假设成对比较，各执行正反顺序两次 |
| save_supabase | true | 保存到独立的实验数据库 |

5. 再点击绿色 Run workflow，打开本次运行记录，查看每一步日志。

**不会自动扣费**：只有手动运行本工作流才会实际调用 DeepSeek。
每次运行限制最多 30 个模型调用、保守 Token 预留 350000。
请注意这不是精确的美元费用上限。即使第一次模型调用失败也可能产生费用。

## 4. 查看结果

**GitHub Actions：** 本次运行页面的 Artifacts 中找到
live-frontier-public-report，下载后打开 JSON。包含候选选题、比赛记录、
版本树、监督决策、文献评审和科学验证结果。
公共模式的 Artifact 在 Public 仓库中可能对其他人可见。

**Langfuse：** 打开对应项目 → Tracing，找到 research-frontier-run
根观察，展开子级 Generation，可看到各 Agent 的调用次数与脱敏结构信息。
**默认不会上传完整 Prompt、论文摘要或模型生成全文**，用于保护数据。

**Supabase：** 在 SQL Editor 中执行以下只读查询：

    select id, line_id, strategy, status, model_calls, created_at,
           results ->> 'winner_title' as winner_title
    from public.lab_frontier_runs
    order by created_at desc
    limit 10;

完整候选和成对竞赛记录存在表的 results JSONB 字段中。RLS 已启用，
代码默认未设置匿名访问策略。

## 5. 人工反馈后，下一轮实验如何改进

人工只在实验结束后参与。找到 run_id，SQL Editor 里可以写入：

    insert into public.lab_frontier_feedback
        (run_id, reviewer_tag, decision, novelty, feasibility, comment)
    values
        ('替换为实际 UUID', 'expert-01', 'revise', 70, 65, '需要补充外部效度实验');

reviewer_tag 同一轮要保持唯一。下一次执行时系统会读取相同科研主线的
历史实验与反馈，用 UCB 策略选择器调整 balanced/novelty/feasibility 权重。
这属于人工反馈驱动的策略学习，不是模型参数微调或已验证的强化学习收益。

## 6. 使用真实团队研究画像

当前仓库的 examples/public_urban_profile.json 是通用城市研究画像，
不是主科研工作台数据库中经过核对的团队画像。真实科研实验必须提供
从原数据库经过脱敏审核的结构化研究主线、论文元数据和数据字段目录。

不要将私有原始数据、未公开研究内容、内部文档或敏感团队画像写进 Public 仓库。
若仅包含允许传输的公开信息，可将与 examples/public_urban_profile.json 同结构、
provenance=approved_export 的完整 JSON 放入 GitHub Secret：

RESEARCH_SNAPSHOT_JSON

随后手动运行时选择 evidence_source=approved_secret。
这会通过 OpenAlex 继续发现真实论文，但不会上传 Public Artifact；
经筛选的最终研究报告会按 save_supabase 选项写入私有实验数据库。
若涉及真正敏感信息，建议改用私有 GitHub 仓库或受控后端环境。

## 7. 下一步科研评估

真实流水线成功执行后，保持同一冻结论文快照，对比 V0.1 的
single/fixed/adaptive 与 V0.3 frontier，并进行盲审、参考文献真实性核验、
成本和消融实验。**Mock 测试通过不代表科学创新性得到验证。**
