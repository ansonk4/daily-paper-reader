<div class="dpr-home-notice-card">
  <h3 class="dpr-home-notice-title">🚀 Start Here</h3>
  <ul class="dpr-home-notice-list">
    <li><a href="#/tutorial/README">使用教程</a></li>
  </ul>
</div>

## 每次日报
- 最新运行日期：2026-06-03 ~ 2026-06-12
- 运行时间：2026-06-12 15:42:44 UTC
- 运行状态：成功
- 本次总论文数：19
- 精读区：9
- 速读区：10

### 今日简报（AI）
今日研究聚焦LLM Agent安全性，精读9篇论文重点剖析内存投毒与跨会话提示注入攻击。  
最值得关注的是《From Untrusted Input to Trusted Memory》对Agent内存投毒的系统性研究（10.0分），以及《What If Prompt Injection Never Left?》对跨会话持久的提示注入攻击的探索（9.0分）。  
建议优先精读这两篇高分论文，深入了解Agent系统的内存安全边界的攻击手法与防御方向。
- 详情：[/20260603-20260612/README](/20260603-20260612/README)

### 精读区论文标签
1. [From Untrusted Input to Trusted Memory: A Systematic Study of Memory Poisoning Attacks in LLM Agents](/20260603-20260612/2606.04329v1-from-untrusted-input-to-trusted-memory-a-systematic-study-of-memory-poisoning-attacks-in-llm-agents)  
   标签：评分：10.0/10、query:agent-safety
   evidence：提出MPBench基准，用于评估LLM智能体记忆投毒攻击
2. [What If Prompt Injection Never Left? Exploring Cross-Session Stored Prompt Injection in Agentic Systems](/20260603-20260612/2606.04425v1-what-if-prompt-injection-never-left-exploring-cross-session-stored-prompt-injection-in-agentic-systems)  
   标签：评分：9.0/10、query:agent-safety
   evidence：跨会话存储提示注入攻击代理系统内存
3. [Membrane: A Self-Evolving Contrastive Safety Memory for LLM Agent Defense](/20260603-20260612/2606.05743v1-membrane-a-self-evolving-contrastive-safety-memory-for-llm-agent-defense)  
   标签：评分：9.0/10、query:agent-safety
   evidence：自进化安全记忆防御越狱，直接相关智能体记忆安全
4. [Beyond Similarity: Trustworthy Memory Search for Personal AI Agents](/20260603-20260612/2606.06054v1-beyond-similarity-trustworthy-memory-search-for-personal-ai-agents)  
   标签：评分：9.0/10、query:agent-safety
   evidence：评估个人AI代理中的对抗性记忆威胁和可信记忆搜索
5. [Data Agents Under Attack: Vulnerabilities in LLM-Driven Analytical Systems](/20260603-20260612/2606.08661v1-data-agents-under-attack-vulnerabilities-in-llm-driven-analytical-systems)  
   标签：评分：9.0/10、query:agent-safety
   evidence：对数据代理的系统安全性研究，包括对记忆和推理的注入攻击
6. [MemVenom: Triggered Poisoning of Multimodal Memories in Web Agents](/20260603-20260612/2606.10742v1-memvenom-triggered-poisoning-of-multimodal-memories-in-web-agents)  
   标签：评分：9.0/10、query:agent-safety
   evidence：网页代理中多模态记忆的触发式投毒
7. [Toward Secure LLM Agents: Threat Surfaces, Attacks, Defenses, and Evaluation](/20260603-20260612/2606.10749v1-toward-secure-llm-agents-threat-surfaces-attacks-defenses-and-evaluation)  
   标签：评分：9.0/10、query:agent-safety
   evidence：全面综述LLM智能体安全，涵盖记忆威胁
8. [Layer-Isolated Evaluation: Gating the Deterministic Scaffold of a Production LLM Agent with a No-LLM, Regression-Locked Test Harness](/20260603-20260612/2606.11686v1-layer-isolated-evaluation-gating-the-deterministic-scaffold-of-a-production-llm-agent-with-a-no-llm-regression-locked-test-harness)  
   标签：评分：9.0/10、query:agent-safety
   evidence：对代理记忆和安全层进行分层隔离评估
9. [Selection Integrity for LLM Graph Memory: An Accumulability Criterion for Information-Flow-Blind Retrieval](/20260603-20260612/2606.12290v1-selection-integrity-for-llm-graph-memory-an-accumulability-criterion-for-information-flow-blind-retrieval)  
   标签：评分：9.0/10、query:agent-safety
   evidence：证明图记忆选择可被不可信结构更改操纵，实现对抗性记忆操控

### 速读区论文标签
1. [Channel Fracture: Architectural Blind Spots in Scheduled Cross-Agent Memory Injection for Multi-Agent Orchestration Systems](/20260603-20260612/2606.04896v2-channel-fracture-architectural-blind-spots-in-scheduled-cross-agent-memory-injection-for-multi-agent-orchestration-systems)  
   标签：评分：8.0/10、query:agent-safety
   evidence：研究跨代理记忆注入中的失效模式
2. [When Should Memory Stay Silent: Measuring Memory-Use Boundaries in Memory-Augmented Conversational Agents](/20260603-20260612/2606.06055v1-when-should-memory-stay-silent-measuring-memory-use-boundaries-in-memory-augmented-conversational-agents)  
   标签：评分：8.0/10、query:agent-safety
   evidence：RBI-Eval评估何时应使用敏感记忆内容，解决对话代理中的记忆安全问题
3. [Deployment-Time Memorization in Foundation-Model Agents](/20260603-20260612/2606.10062v1-deployment-time-memorization-in-foundation-model-agents)  
   标签：评分：8.0/10、query:agent-safety
   evidence：研究智能体记忆中的隐私-效用权衡，涵盖提取风险和删除保真度
4. [Domain-Conditioned Safety in Frontier Computer-Using Agents: A 793-Episode Browser Benchmark, a Coding-Domain Cross-Reference, and a Reproducibility Audit of Recent Red-Teaming](/20260603-20260612/2606.05233v1-domain-conditioned-safety-in-frontier-computer-using-agents-a-793-episode-browser-benchmark-a-coding-domain-cross-reference-and-a-reproducibility-audit-of-recent-red-teaming)  
   标签：评分：7.0/10、query:agent-safety
   evidence：面向计算机使用代理的提示注入攻击基准
5. [VESTA: A Fully Automated Scenario Generation and Safety Evaluation Framework for LLM Agents](/20260603-20260612/2606.08531v1-vesta-a-fully-automated-scenario-generation-and-safety-evaluation-framework-for-llm-agents)  
   标签：评分：7.0/10、query:agent-safety
   evidence：LLM智能体自动安全评估框架，在场景生成中包含记忆风险
6. [AgentCanary: A Security Evaluation Framework for Autonomous AI Agents in Real Executable Environments](/20260603-20260612/2606.10484v1-agentcanary-a-security-evaluation-framework-for-autonomous-ai-agents-in-real-executable-environments)  
   标签：评分：7.0/10、query:agent-safety
   evidence：自主AI智能体安全评估框架，可潜在应用于记忆安全
7. [RAMPART: Registry-based Agentic Memory with Priority-Aware Runtime Transformation](/20260603-20260612/2606.04628v1-rampart-registry-based-agentic-memory-with-priority-aware-runtime-transformation)  
   标签：评分：6.0/10、query:agent-safety
   evidence：具有块级所有权和溯源标签的权限记忆模型
8. [Channel Fracture: Architectural Blind Spots in Scheduled Cross-Agent Memory Injection for Multi-Agent Orchestration Systems](/20260603-20260612/2606.04896v1-channel-fracture-architectural-blind-spots-in-scheduled-cross-agent-memory-injection-for-multi-agent-orchestration-systems)  
   标签：评分：6.0/10、query:agent-safety
   evidence：跨代理记忆注入中的架构盲点
9. [MalSkillBench: A Runtime-Verified Benchmark of Malicious Agent Skills](/20260603-20260612/2606.07131v1-malskillbench-a-runtime-verified-benchmark-of-malicious-agent-skills)  
   标签：评分：6.0/10、query:agent-safety
   evidence：恶意代理技能基准，与代理安全相关
10. [H2HMem: A Multimodal Memory Benchmark for Agents in Human-Human Interactions](/20260603-20260612/2606.09461v1-h2hmem-a-multimodal-memory-benchmark-for-agents-in-human-human-interactions)  
   标签：评分：6.0/10、query:agent-safety
   evidence：面向人机交互中智能体的多模态记忆基准


<div class="dpr-home-promo-card">
  <h3 class="dpr-home-promo-title">💬 社区与支持</h3>
  <ul class="dpr-home-promo-list">
    <li>欢迎 Star / Fork / Issue / PR</li>
    <li>QQ群：583867967（欢迎交流，已有：1151人）</li>
  </ul>
</div>
