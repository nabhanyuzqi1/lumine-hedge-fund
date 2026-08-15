#!/bin/bash
# Extract AI_PROVIDERS dari chunk 869.js
ssh -i ~/.ssh/lumine/id_rsa_lumine root@166.88.227.177 "docker exec 9router node -e '
const s = require(\"fs\").readFileSync(\"/app/.next/server/chunks/869.js\",\"utf8\");
const names = [\"opencode\",\"openrouter\",\"deepseek\",\"openai\",\"anthropic\",\"gemini\",\"google\",\"qwen\",\"kimi\",\"glm\",\"siliconflow\",\"moonshot\",\"mistral\",\"groq\",\"fireworks\",\"together\",\"nvidia\",\"cerebras\",\"ollama\",\"claude\",\"grok\",\"xai\",\"minimax\",\"zhipu\",\"baidu\",\"qianfan\",\"volcengine\",\"hunyuan\",\"doubao\",\"perplexity\",\"blackbox\",\"tokenrouter\",\"cu\",\"oc\",\"ag\",\"kr\",\"gh\",\"if\",\"deepinfra\",\"hyperbolic\",\"nebius\",\"cohere\",\"venice\",\"lmstudio\"];
for (const n of names) {
  if (s.indexOf(JSON.stringify(n)) !== -1) console.log(n, \"FOUND\");
}
console.log(\"--- ids ---\");
const ids = [...s.matchAll(/id:\"([a-z0-9-]+)\"/g)].map(m => m[1]);
const uniq = [...new Set(ids)].sort();
console.log(\"ids:\", uniq.slice(0, 100).join(\", \"));
'"