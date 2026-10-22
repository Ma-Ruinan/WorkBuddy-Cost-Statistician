# WorkBuddy日志来源和字段

默认来源为 `%USERPROFILE%\.workbuddy\projects\项目目录\会话ID.jsonl`，可通过命令行显式覆盖。该说明记录已核实的日志结构，不代表厂商的长期接口承诺。字段变更需要查看实际记录后修改适配器并重新验证。

在 .workbuddy/projects 下查找对应项目的会话 JSONL。工作目录可能位于其他磁盘，不能假设项目日志也保存在工作目录内。读取 message 类型、role=user 中 content.text 的 user_query 内容，保留实际附加的 @scene# 场景参数。

用量读取 providerData.usage，按 conversationRequestId 与 messageId 联合去重。一轮输出可能关联多个工具事件，不能按带 usage 的日志行数直接累加。当前确认的 usage.requests 为 1；每个请求内的 stepSeq 应与去重后的模型消息一一对应。字段语义变化时停止，并核查后再修改采集器。

累计输入直接使用 usage.inputTokens，其中已包含缓存，不能再次加缓存读取量；输出使用 usage.outputTokens；缓存读取量为 usage.inputTokensDetails 各项 cached_tokens 之和。存在 rawUsage 时与 prompt_tokens、completion_tokens、prompt_tokens_details.cached_tokens 交叉核对。

工具调用为 function_call，结果为 function_call_result，按 callId 配对。外层 status=completed 仍可能有 providerData.toolResult.rawResponse.is_error=true、toolResult.isError=true 或 rawResponse.exitCode 非零，均计为工具错误。同一调用只计一次错误。缺少配对结果时工具错误总数保持缺失。

模型失败重试尚未确认独立可靠字段，保持未记录。附带制作PPT等场景参数的任务，实际文件制作工作量属于本次条件，需要在报告中保留。

专用搜索工具为 `WebSearch`。成功交付工具为 `present_files`，从 `output_paths` 或 `files` 数组读取路径。路径相对工作目录解析后去重，逐个核验磁盘存在性；检查过程中的截图、脚本、临时文件不自动算作最终交付。

默认仅统计与题目明确匹配的主会话；独立子会话、后台会话和未匹配用户消息在JSON中单列排除原因。发现与任务相关的子会话时应在报告中记录范围，本版主会话统计不会自动并入其用量。完整输入文本、会话及用户消息标识共同用于关联，不能仅根据目录名称或相近时间配对。

同一批数据默认读取两次并比较。若仍在写入、读取不一致或Token恒等关系变化，脚本停止并返回非零退出码；应查明实际记录后重跑，不能补猜测值。目录时间、session更新时间和数据库费用零值都不替代已核实的字段。
