# 文献统筹搜索 + Hybrid RAG 知识库 MVP

这是第四块“文献检索与知识库”的独立实现目录，不依赖也不修改旧项目目录。

## 交付内容

- 多源检索：arXiv、OpenAlex、Semantic Scholar、本地 PDF
- 初始建库：`bootstrap` 阶段联网检索、解析、chunk、入库
- 离线查询：`review` / `ask` 阶段默认只查本地知识库
- Hybrid RAG：Chroma dense retrieval + 内置 BM25 sparse retrieval
- 结构化输出：JSON + TXT
- 模型层：统一 `LLMAdapter`，默认配置 DeepSeek-compatible API，不使用 GLM

## 配置

```text
LLM_PROVIDER=deepseek
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
OPENALEX_MAILTO=your_email@example.com
```

也兼容 DeepSeek 风格变量：

```text
DEEPSEEK_API_KEY=your_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
```

如果没有 API key，系统会使用 deterministic fallback，仍然能生成 JSON/TXT，方便演示和测试。

## 命令

离线样例建库：

```bash
python literature_pipeline.py bootstrap --seed seed_topics.json --limit 5 --demo
```

完全离线样例建库（不启用 Chroma）：

```bash
python literature_pipeline.py bootstrap --seed seed_topics.json --limit 5 --demo --no-dense
```

正常建库：

```bash
python literature_pipeline.py bootstrap --seed seed_topics.json --limit 30
```

联网小流量测试：

```bash
python literature_pipeline.py bootstrap --seed seed_topics.json --limit 10 --skip-pdf-download --no-dense --max-queries 3
```

如果 Semantic Scholar 被限流，可先只测 arXiv + OpenAlex：

```bash
python literature_pipeline.py bootstrap --seed seed_topics.json --limit 10 --skip-pdf-download --no-dense --max-queries 2 --sources arxiv,openalex
```

只用摘要、不下载 PDF：

```bash
python literature_pipeline.py bootstrap --seed seed_topics.json --limit 30 --skip-pdf-download
```

生成综述：

```bash
python literature_pipeline.py review --topic "AI Scientist automated scientific discovery"
```

追问知识库：

```bash
python literature_pipeline.py ask --question "AI Scientist 系统已有研究的主要不足是什么？"
```

测试 LLM：

```bash
python literature_pipeline.py test-llm
```

## 输出

```text
outputs/
  search_manifest.json
  papers.json
  chunks.json
  literature_review.json
  literature_review.txt
  answer.json
  answer.txt
  warnings.txt

data_storage/
  knowledge_base/
  pdfs/
```

`literature_review.txt` 是从 JSON 本地渲染出来的测试/展示文本，保证和 `literature_review.json` 内容一致。
