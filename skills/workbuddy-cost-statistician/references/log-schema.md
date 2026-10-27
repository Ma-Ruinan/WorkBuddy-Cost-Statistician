# WorkBuddy日志来源和字段

默认来源为 `%USERPROFILE%\.workbuddy\projects\项目目录\会话ID.jsonl`，可通过命令行显式覆盖。该说明记录已核实的日志结构，不代表厂商的长期接口承诺。字段变更需要查看实际记录后修改适配器并重新验证。

在 .workbuddy/projects 下查找对应项目的会话 JSONL。工作目录可能位于其他磁盘，不能假设项目日志也保存在工作目录内。先按主日志头部的cwd和sessionId选择工作空间与会话，再读取其完整日志及所属子日志。工具结果包含未转义换行时按完整JSON对象读取，证据行号保留原文件的物理行；真正截断或无法解析的所选日志报出路径和行号，不跳过记录补零。

读取 message 类型、role=user 中 content.text 的 user_query 内容。带引号的 @scene# 标签可以位于题目前后，只移除标签本身；旧式未加引号的尾部场景说明仍单独保留。附件引用单独去除后能与完整题目唯一匹配时自动关联，原始场景及附件保留为测试条件。

用量读取 providerData.usage，按 conversationRequestId 与 messageId 联合去重。一轮输出可能关联多个工具事件，不能按带 usage 的日志行数直接累加。当前确认的 usage.requests 为 1；每个请求内的 stepSeq 应与去重后的模型消息一一对应。字段语义变化时停止，并核查后再修改采集器。

累计输入直接使用 usage.inputTokens，其中已包含缓存，不能再次加缓存读取量；输出使用 usage.outputTokens；缓存读取量为 usage.inputTokensDetails 各项 cached_tokens 之和。存在 rawUsage 时与 prompt_tokens、completion_tokens、prompt_tokens_details.cached_tokens 交叉核对。

工具调用为 function_call，结果为 function_call_result，按 callId 配对。外层 status=completed 仍可能有 providerData.toolResult.rawResponse.is_error=true、toolResult.isError=true 或 rawResponse.exitCode 非零，均计为工具错误。同一调用只计一次错误。缺少配对结果时工具错误总数保持缺失。

模型失败重试尚未确认独立可靠字段，保持未记录。附带制作PPT等场景参数的任务，实际文件制作工作量属于本次条件，需要在报告中保留。

搜索调用包括 `WebSearch` 和经 `DeferExecuteTool` 的 `arguments.toolName=domain_search` 发出的检索，失败调用也计数。包装调用在工具总数中仅计一次，JSON保留原name和实际effective_name；其他延迟工具不自动归类为搜索。成功交付工具为 `present_files`，从 `output_paths` 或 `files` 数组读取路径。路径相对工作目录解析后去重，逐个核验磁盘存在性；检查过程中的截图、脚本、临时文件不自动算作最终交付。

原始题目仅用于定位主任务，实际委派的各层子Agent继承对应独立测试归属，不新增测试次数。通过Agent/Task调用结果中的toolResult.subAgent.sessionId关联同一主日志所属subagents目录的文件；兼容结构化agentId、agent_id及resume字段。providerData.isMeta为true、startsNewUserRequest为false或isCompactInternal为true的内部消息不作为新用户测试边界，压缩和恢复后的实际调用仍归属原测试。只有isCompacted标记的真实用户消息仍保留。具名SendMessage消息通过Agent的name或descriptor.role定位子会话，并划分本次继续执行窗口。子日志收到拆分后的任务，不要求它再次匹配原始题目。明确引用但缺少文件、无法关联的子日志或循环关系均记录为覆盖问题。同一子会话被再次调用时，按委派调用界定新的执行窗口，避免将旧历史计入下一次测试；继续执行段仍并入原测试。

模型记录按原始消息或请求标识去重；工具按调用标识及调用时间去重，防止同一执行在父摘要、子日志中重复累计，也避免不同时间复用局部标识被合并。父工具结果中的汇总Token不重复累加。无法唯一归属或标识内容冲突时停止猜测值。

同一批数据默认读取两次并比较。若仍在写入、读取不一致或Token恒等关系变化，脚本停止并返回非零退出码；应查明实际记录后重跑，不能补猜测值。目录时间、session更新时间和数据库费用零值都不替代已核实的字段。
