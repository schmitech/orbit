import { Ollama } from '@langchain/community/llms/ollama';
import { RunnableSequence } from '@langchain/core/runnables';
import { StringOutputParser } from '@langchain/core/output_parsers';
import { PromptTemplate } from "@langchain/core/prompts";
import { ChromaRetriever } from './chromaRetriever';
import { AppConfig } from './types';
import { BaseLanguageModelClient } from './baseClient';

export class OllamaClient extends BaseLanguageModelClient {
  private llm: Ollama;

  constructor(config: AppConfig, retriever: ChromaRetriever) {
    super(config, retriever);
    
    this.llm = new Ollama({
      baseUrl: config.ollama.base_url,
      model: config.ollama.model,
      temperature: parseFloat(String(config.ollama.temperature)),
      system: config.system.prompt,
      numPredict: parseInt(String(config.ollama.num_predict)),
      repeatPenalty: parseFloat(String(config.ollama.repeat_penalty)),
      numCtx: parseInt(String(config.ollama.num_ctx)),
      numThread: parseInt(String(config.ollama.num_threads)),
      top_p: parseFloat(String(config.ollama.top_p)),
      top_k: parseInt(String(config.ollama.top_k)),
      stream: config.ollama.stream,
      
      fetch: async (input: RequestInfo, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input.url;
        if (this.verbose) {
          console.log('\n--- Ollama API Call ---');
          console.log('Endpoint:', url.replace(config.ollama.base_url!, ''));
          
          if (init?.body) {
            const body = JSON.parse(init.body.toString());
            console.log('\nFull Request Body:');
            console.log(JSON.stringify(body, null, 2));
            console.log('\nSystem Prompt:', body.system);
            console.log('\nUser Prompt:', body.prompt);
            console.log('\nOptions:', body.options);
          }
          
          const start = Date.now();
          const response = await fetch(input, init);
          console.log(`\nDuration: ${Date.now() - start}ms`);
          console.log('Status:', response.status);
          
          return response;
        }
        return fetch(input, init);
      }
    } as any);
  }

  async createChain(): Promise<RunnableSequence> {
    return RunnableSequence.from([
      async (input: { query: string }) => {
        if (this.verbose) {
          console.log('\n=== Starting Document Retrieval ===');
          console.log('Query:', input.query);
        }
        
        const docs = await this.retriever.getRelevantDocuments(input.query);
        if (this.verbose) {
          console.log('Retrieved documents count:', docs.length);
        }
        
        const context = this.formatDocuments(docs);
        if (this.verbose) {
          console.log('\n=== Final Context ===');
          console.log(context);
        }
        
        // Handle the case where no relevant context is found
        if (context === 'NO_RELEVANT_CONTEXT') {
          return {
            context: "NO_RELEVANT_CONTEXT",
            question: input.query,
            system: this.config.system.prompt,
          };
        }
        
        return {
          context,
          question: input.query,
          system: this.config.system.prompt,
        };
      },
      PromptTemplate.fromTemplate(`SYSTEM: {system}

CONTEXT: {context}

USER QUESTION: {question}

ANSWER:`),
      async (input: string | any) => {
        if (this.verbose) {
          console.log('\n=== Final Prompt to Ollama ===');
          console.log('Complete Prompt:');
          console.log(input);
          console.log('\nPrompt Length:', typeof input === 'string' ? input.length : JSON.stringify(input).length);
        }
        const response = await this.llm.invoke(input);
        if (this.verbose) {
          console.log('\n=== Ollama Response ===');
          console.log(response);
        }
        return response;
      },
      new StringOutputParser(),
    ]);
  }

  async checkGuardrail(query: string): Promise<{ safe: boolean }> {
    if (this.verbose) {
      console.log('\n=== Guardrail Check ===');
      console.log('Query:', query);
    }
    
    try {
      // Create request payload with the guardrail prompt
      const payload = {
        model: this.config.ollama.model,
        prompt: `${this.config.system.guardrail_prompt}\n\nQuery: ${query}\n\nRespond with ONLY 'SAFE: true' or 'SAFE: false':`,
        temperature: 0.0,
        top_p: 1.0,
        top_k: 1,
        repeat_penalty: parseFloat(String(this.config.ollama.repeat_penalty)),
        num_predict: 20,
        stream: false
      };
      
      if (this.verbose) {
        console.log('\n=== Guardrail Prompt ===');
        console.log(payload.prompt);
      }
      
      // Make request to Ollama
      const response = await fetch(`${this.config.ollama.base_url}/api/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });
      
      const responseData = await response.json();
      const result = responseData.response?.trim();
      
      if (this.verbose) {
        console.log('\n=== Guardrail Response ===');
        console.log('Response:', result);
      }
      
      // Check if the response matches the expected format
      if (result === 'SAFE: true') {
        return { safe: true };
      } else if (result === 'SAFE: false') {
        return { safe: false };
      } else {
        console.warn('Guardrail response does not match expected format:', result);
        // Default to safe for non-matching responses, but log the warning
        return { safe: true };
      }
    } catch (error: any) {
      console.error('Error in guardrail check:', error.message);
      // Default to safe on error to prevent complete service failure
      return { safe: true };
    }
  }
  
  async verifyConnection(): Promise<boolean> {
    try {
      const response = await fetch(`${this.config.ollama.base_url}/api/tags`);
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      if (this.verbose) {
        console.log('Ollama connection successful');
      }
      return true;
    } catch (error) {
      console.error('Ollama connection failed:', error);
      return false;
    }
  }
}