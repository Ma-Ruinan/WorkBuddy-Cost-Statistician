# WorkBuddy��־��Դ���ֶ�

Ĭ����ԴΪ `%USERPROFILE%\.workbuddy\projects\��ĿĿ¼\�ỰID.jsonl`����ͨ����������ʽ���ǡ���˵����¼�Ѻ�ʵ����־�ṹ�����������̵ĳ��ڽӿڳ�ŵ���ֶα����Ҫ�鿴ʵ�ʼ�¼���޸���������������֤��

�� .workbuddy/projects �²��Ҷ�Ӧ��Ŀ�ĻỰ JSONL������Ŀ¼����λ���������̣����ܼ�����Ŀ��־Ҳ�����ڹ���Ŀ¼�ڡ���ȡ message ���͡�role=user �� content.text �� user_query ���ݣ�����ʵ�ʸ��ӵ� @scene# ����������

������ȡ providerData.usage���� conversationRequestId �� messageId ����ȥ�ء�һ��������ܹ�����������¼������ܰ��� usage ����־����ֱ���ۼӡ���ǰȷ�ϵ� usage.requests Ϊ 1��ÿ�������ڵ� stepSeq Ӧ��ȥ�غ��ģ����Ϣһһ��Ӧ���ֶ�����仯ʱֹͣ�����˲�����޸Ĳɼ�����

�ۼ�����ֱ��ʹ�� usage.inputTokens�������Ѱ������棬�����ٴμӻ����ȡ�������ʹ�� usage.outputTokens�������ȡ��Ϊ usage.inputTokensDetails ���� cached_tokens ֮�͡����� rawUsage ʱ�� prompt_tokens��completion_tokens��prompt_tokens_details.cached_tokens ����˶ԡ�

���ߵ���Ϊ function_call�����Ϊ function_call_result���� callId ��ԡ���� status=completed �Կ����� providerData.toolResult.rawResponse.is_error=true��toolResult.isError=true �� rawResponse.exitCode ���㣬����Ϊ���ߴ���ͬһ����ֻ��һ�δ���ȱ����Խ��ʱ���ߴ�����������ȱʧ��

ģ��ʧ��������δȷ�϶����ɿ��ֶΣ�����δ��¼����������PPT�ȳ�������������ʵ���ļ��������������ڱ�����������Ҫ�ڱ����б�����

ר����������Ϊ `WebSearch`���ɹ���������Ϊ `present_files`���� `output_paths` �� `files` �����ȡ·����·����Թ���Ŀ¼������ȥ�أ����������̴����ԣ��������еĽ�ͼ���ű�����ʱ�ļ����Զ��������ս�����

Ĭ�Ͻ�ͳ������Ŀ��ȷƥ������Ự�������ӻỰ����̨�Ự��δƥ���û���Ϣ��JSON�е����ų�ԭ�򡣷�����������ص��ӻỰʱӦ�ڱ����м�¼��Χ���������Ựͳ�Ʋ����Զ����������������������ı����Ự���û���Ϣ��ʶ��ͬ���ڹ��������ܽ�����Ŀ¼���ƻ����ʱ����ԡ�

ͬһ������Ĭ�϶�ȡ���β��Ƚϡ�������д�롢��ȡ��һ�»�Token��ȹ�ϵ�仯���ű�ֹͣ�����ط����˳��룻Ӧ����ʵ�ʼ�¼�����ܣ����ܲ��²�ֵ��Ŀ¼ʱ�䡢session����ʱ������ݿ������ֵ��������Ѻ�ʵ���ֶΡ�
