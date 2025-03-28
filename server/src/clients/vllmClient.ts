import { RunnableSequence } from '@langchain/core/runnables';
import { StringOutputParser } from '@langchain/core/output_parsers';
import { PromptTemplate } from "@langchain/core/prompts";
import { ChromaRetriever } from './chromaRetriever';
import { AppConfig } from './types';
import { BaseLanguageModelClient } from './baseClient';

export class VLLMClient extends BaseLanguageModelClient {
  constructor(config: AppConfig, retriever: ChromaRetriever) {
    super(config, retriever);
  }

  async checkGuardrail(query: string): Promise<{ safe: boolean }> {
    if (this.verbose) console.log('\n=== VLLM Guardrail Check ===\nQuery:', query);

    try {
      const payload = {
        model: this.config.vllm.model,
        prompt: `${this.config.system.guardrail_prompt}\n\nQuery: ${query}\n\nRespond with ONLY 'SAFE: true' or 'SAFE: false':`,
        max_tokens: this.config.vllm.guardrail_max_tokens || 20,
        temperature: this.config.vllm.guardrail_temperature || 0.0,
        top_p: this.config.vllm.guardrail_top_p || 1.0,
        best_of: this.config.vllm.best_of || 1
      };

      if (this.verbose) console.log('\n=== Guardrail Prompt ===\n', payload.prompt);

      const response = await fetch(`${this.config.vllm.base_url}/v1/completions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const result = (await response.json()).choices?.[0]?.text?.trim();
      if (this.verbose) console.log('\n=== Guardrail Response ===\nResponse:', result);

      if (result === 'SAFE: true') return { safe: true };
      if (result === 'SAFE: false') return { safe: false };
      
      console.warn('Guardrail response invalid format:', result);
      return { safe: true }; // Default to safe
    } catch (error) {
      console.error('Error in guardrail check:', error);
      return { safe: true }; // Default to safe on error
    }
  }

  async createChain(): Promise<RunnableSequence> {
    const self = this;
    return RunnableSequence.from([
      async (input: { query: string }) => {
        if (self.verbose) console.log('\n=== Starting Document Retrieval ===\nQuery:', input.query);
        
        const docs = await self.retriever.getRelevantDocuments(input.query);
        if (self.verbose) console.log('Retrieved documents count:', docs.length);
        
        const context = self.formatDocuments(docs);
        if (self.verbose) console.log('\n=== Final Context ===\n', context);
        
        return context === 'NO_RELEVANT_CONTEXT' 
          ? { context: "NO_RELEVANT_CONTEXT", question: input.query, system: self.config.system.prompt }
          : { context, question: input.query, system: self.config.system.prompt };
      },
      PromptTemplate.fromTemplate(
`<system>
{system}
</system>

<context>
{context}
</context>

<question>
{question}
</question>

<answer>
`),
      async function* (input: any) {
        // Extract prompt text from LangChain object if needed
        const promptText = typeof input === 'string' ? input : input?.kwargs?.value || input.toString();
        
        if (self.verbose) {
          console.log('\n=== Final Prompt to VLLM ===');
          console.log(promptText);
          console.log('Length:', promptText?.length);
        }

        // Build payload using config values
        const payload = {
          model: self.config.vllm.model,
          prompt: promptText,
          max_tokens: parseInt(String(self.config.vllm.max_tokens), 10),
          temperature: parseFloat(String(self.config.vllm.temperature)),
          top_p: parseFloat(String(self.config.vllm.top_p)),
          frequency_penalty: parseFloat(String(self.config.vllm.frequency_penalty)),
          presence_penalty: parseFloat(String(self.config.vllm.presence_penalty)),
          best_of: self.config.vllm.best_of,
          n: self.config.vllm.n,
          logprobs: self.config.vllm.logprobs,
          echo: self.config.vllm.echo,
          stream: self.config.vllm.stream === 'true' || self.config.vllm.stream === true
        };

        try {
          if (self.verbose) console.log('\n=== VLLM Request Payload ===\n', JSON.stringify(payload));

          const response = await fetch(`${self.config.vllm.base_url}/v1/completions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          });

          if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
          }

          // Check if streaming or not
          const useStream = self.config.vllm.stream === 'true' || self.config.vllm.stream === true;
          
          if (useStream) {
            // Handle streaming response
            const reader = response.body?.getReader();
            if (!reader) throw new Error('No reader available');
            
            let buffer = '';
            let decoder = new TextDecoder();
            
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;
              
              const chunk = decoder.decode(value, { stream: true });
              const lines = chunk.split('\n').filter(line => line.trim());
              
              for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                
                try {
                  const data = JSON.parse(line.slice(6));
                  const text = data.choices?.[0]?.text || '';
                  if (text) {
                    buffer += text;
                    yield text;
                  }
                } catch (e) {
                  console.warn('Error parsing VLLM stream chunk:', e);
                }
              }
            }
            
            if (self.verbose) console.log('\n=== VLLM Response ===\n', buffer);
            return buffer;
          } else {
            // Handle non-streaming response
            const responseData = await response.json();
            const result = responseData.choices?.[0]?.text || '';
            
            if (self.verbose) console.log('\n=== VLLM Response ===\n', result);
            
            // Still yield the whole response at once to maintain generator interface
            yield result;
            return result;
          }
        } catch (error) {
          console.error('VLLM request failed:', error);
          throw error;
        }
      },
      new StringOutputParser(),
    ]);
  }
  
  async verifyConnection(): Promise<boolean> {
    try {
      const response = await fetch(`${this.config.vllm.base_url}/v1/models`);
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      if (this.verbose) {
        console.log('VLLM connection successful');
      }
      return true;
    } catch (error) {
      console.error('VLLM connection failed:', error);
      return false;
    }
  }
}