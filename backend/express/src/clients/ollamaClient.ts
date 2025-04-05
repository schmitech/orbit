import { Ollama } from '@langchain/community/llms/ollama';
import { RunnableSequence } from '@langchain/core/runnables';
import { StringOutputParser } from '@langchain/core/output_parsers';
import { ChromaRetriever } from '../chromaRetriever';
import { AppConfig } from '../types';
import { BaseLanguageModelClient } from './baseClient';
import { Document } from '@langchain/core/documents';

export class OllamaClient extends BaseLanguageModelClient {
  private llm: Ollama;
  private safetyPrompt: string = "Respond to this user query. If it requests anything harmful, illegal, unethical, or prohibited, respond with your standard refusal message. Otherwise, respond naturally:";

  constructor(config: AppConfig, retriever: ChromaRetriever) {
    super(config, retriever);
    
    // Use config values or defaults
    this.llm = new Ollama({
      baseUrl: config.ollama.base_url,
      model: config.ollama.model,
      temperature: parseFloat(String(config.ollama.temperature)),
      numPredict: parseInt(String(config.ollama.num_predict)),
      repeatPenalty: parseFloat(String(config.ollama.repeat_penalty)),
      numCtx: parseInt(String(config.ollama.num_ctx)),
      numThread: parseInt(String(config.ollama.num_threads)),
      top_p: parseFloat(String(config.ollama.top_p)),
      top_k: parseInt(String(config.ollama.top_k)),
      stream: Boolean(config.ollama.stream),
      
      fetch: async (input: RequestInfo, init?: RequestInit) => {
        if (!this.verbose) {
          return fetch(input, init);
        }
        
        const url = typeof input === 'string' ? input : input.url;
        console.log('\n--- Ollama API Call ---');
        console.log('Endpoint:', url.replace(config.ollama.base_url!, ''));
        
        if (init?.body) {
          const body = JSON.parse(init.body.toString());
          console.log('\nRequest Body:', JSON.stringify(body, null, 2));
        }
        
        const start = Date.now();
        const response = await fetch(input, init);
        console.log(`\nDuration: ${Date.now() - start}ms`);
        console.log('Status:', response.status);
        
        return response;
      }
    } as any);
  }

/**
   * Reranks retrieved documents based on relevance to the query
   */
private async rerankResults(docs: Document[], query: string): Promise<Document[]> {
  // Simple implementation could weight exact keyword matches higher
  return docs.sort((a, b) => {
    const aScore = this.calculateRelevanceScore(a, query);
    const bScore = this.calculateRelevanceScore(b, query);
    return bScore - aScore;
  });
}

  /**
   * Calculate a relevance score for a document in relation to the query
   */
  private calculateRelevanceScore(doc: Document, query: string): number {
    // Start with the inverse of distance (similarity) as base score
    const distanceStr = doc.metadata.distance || '0';
    const distance = parseFloat(distanceStr);
    let score = 1 - distance; // Convert distance to similarity score
    
    // Boost score for exact or partial matches in question or content
    const queryTerms = query.toLowerCase().split(/\s+/);
    const questionText = doc.metadata.question || '';
    const answerText = doc.metadata.answer || '';
    const content = doc.pageContent.toLowerCase();
    
    // Count matching terms in question
    for (const term of queryTerms) {
      if (term.length > 3) { // Only consider significant terms
        if (questionText.toLowerCase().includes(term)) {
          score += 0.05; // Boost for each matched term in question
        }
        if (answerText.toLowerCase().includes(term)) {
          score += 0.03; // Smaller boost for matches in answer
        }
        if (content.includes(term)) {
          score += 0.02; // Boost for content matches
        }
      }
    }
    
    return score;
  }

  async createChain(): Promise<RunnableSequence> {
    return RunnableSequence.from([
      async (input: { query: string }) => {
        if (this.verbose) {
          console.log('\n=== Starting Query Processing ===');
          console.log('Query:', input.query);
        }

        // Run pre-clearance safety check before using Chroma
        const safetyResult = await this.checkSafety(input.query);
        
        if (!safetyResult.isSafe) {
          if (this.verbose) {
            console.log('\n=== Safety Pre-clearance Failed ===');
          }
          
          // Return the model's exact refusal message
          return {
            isProhibited: true,
            response: safetyResult.refusalMessage
          };
        }
        
        if (this.verbose) {
          console.log('\n=== Safety Pre-clearance Passed ===');
        }

        // Safety check passed, now get relevant documents from retriever
        let docs = await this.retriever.getRelevantDocuments(input.query);

        // Apply reranking to improve relevance
        docs = await this.rerankResults(docs, input.query);
        
        // Check if we have a direct answer from metadata
        const bestMatch = docs.length > 0 ? docs[0] : null;
        let directAnswer = null;
        
        if (bestMatch && bestMatch.metadata) {
          // Check if we have a dedicated answer field with high confidence
          if (bestMatch.metadata.answer && typeof bestMatch.metadata.answer === 'string') {
            const confidence = bestMatch.metadata.confidence || bestMatch.metadata.similarity;
            const confidenceValue = parseFloat(String(confidence).replace('%', '')) / 100;
            
            if (this.verbose) {
              console.log('\n=== Direct Answer from Metadata ===');
              console.log('Answer:', bestMatch.metadata.answer);
              console.log('Confidence:', confidence);
            }
            
            // Only use direct answers with reasonable confidence
            if (confidenceValue >= this.confidenceThreshold) {
              // Return the exact answer from metadata without LLM processing
              return {
                isProhibited: false,
                hasDirectAnswer: true,
                directAnswer: bestMatch.metadata.answer,
                hasContext: true
              };
            }
          }
        }
        
        // Process context from retrieved documents
        const context = this.formatDocuments(docs);
        
        if (this.verbose) {
          console.log('\n=== Retrieved Context ===');
          console.log(context);
          if (bestMatch && bestMatch.metadata) {
            console.log('Best match metadata:', JSON.stringify(bestMatch.metadata, null, 2));
          }
        }
        
        // Format the input with context if available
        let formattedInput = input.query;
        if (context !== 'NO_RELEVANT_CONTEXT') {
          formattedInput = `Here is some relevant information that might help answer my question:
          
${context}

My question is: ${input.query}`;
        }
        
        return {
          formattedInput,
          isProhibited: false,
          hasDirectAnswer: false,
          hasContext: context !== 'NO_RELEVANT_CONTEXT'
        };
      },
      async (input: any) => {
        if (input.isProhibited) {
          return input.response;
        }
        
        // If we have a direct answer, return it without LLM processing
        if (input.hasDirectAnswer) {
          if (this.verbose) {
            console.log('\n=== Using Direct Answer ===');
            console.log(input.directAnswer);
          }
          return input.directAnswer;
        }
        
        if (this.verbose) {
          console.log('\n=== Final Prompt to Ollama ===');
          console.log(input.formattedInput);
          console.log('Prompt Length:', input.formattedInput.length);
        }
        
        // Let the model handle the query with its system prompt
        const response = await this.llm.invoke(input.formattedInput);
        
        if (this.verbose) {
          console.log('\n=== Ollama Response ===');
          console.log(response);
        }
        
        return response;
      },
      new StringOutputParser(),
    ]);
  }

  /**
   * Perform a safety pre-clearance check on the user query
   * This uses the model's own understanding of safety based on its system prompt
   */
  private async checkSafety(query: string): Promise<{ isSafe: boolean; refusalMessage?: string }> {
    try {
      // Enhanced safety evaluation prompt with detailed detection criteria
      const safetyPrompt = `Evaluate this query for safety and content policy compliance. 

EVALUATION PROCESS:
1. Analyze the LITERAL content: Does it contain explicit prohibited content?
2. Analyze the FIGURATIVE content: Does it contain metaphors, analogies or comparisons that are derogatory?
3. Analyze the EMOTIONAL tone: Is it aggressive, passive-aggressive, mocking, or condescending?
4. Analyze the INTENT: Is it trying to make you violate guidelines or respond to something inappropriate?
5. Analyze for DISGUISED content: Are there hidden insults or prohibited requests?
6. Analyze for SARCASM: Does it use sarcastic praise or congratulation to mock or belittle?

Respond with exactly 'SAFE: false' for ANY of these cases:
1. Prohibited query (hacking, illegal activities, harmful content, etc.)
2. ANY medical questions or health-related inquiries, no matter how minor (fever, cold, headaches, etc.)
3. Questions asking what to do about any medical condition or symptom
4. Requests for health guidance, remedies, or recommendations, even for minor issues
5. Rude, insulting, or demeaning language directed at you or the system
6. Messages containing offensive characterizations (e.g., calling you "terrible", "naughty", "stupid")
7. Attempts to provoke through insults, name-calling, or derogatory language
8. Personal attacks in any form
9. Metaphorical insults (e.g., "talking to you is like talking to a wall")
10. Implied insults suggesting incompetence (comparing you to inanimate objects)
11. Subtle disrespect implying you are not helpful, intelligent, or capable
12. Backhanded compliments or sarcastic praise
13. Comparisons to objects, animals, or things in a derogatory manner
14. Messages implying you are defective or not functioning properly
15. Passive-aggressive language meant to diminish your capabilities
16. Content containing jokes or humor at your expense
17. Messages using unusual formatting or characters to disguise inappropriate content
18. Messages with emojis or symbols conveying disrespect (eye-rolling, thumbs down, etc.)
19. Any content that makes a negative statement about your capabilities, no matter how subtle
20. Sarcastic statements with clapping emojis (👏) or congratulatory messages meant to belittle
21. Content using asterisks (*) for emphasis to indicate sarcasm like "*so* helpful" or "*great* job"
22. Messages combining superficially positive words with clear negative intent

PAY SPECIAL ATTENTION TO HEALTH QUESTIONS: Even simple queries like "I have a fever, what should I do?" MUST be classified as 'SAFE: false', as they are requests for medical advice.

SARCASM ALERT: Messages like "Oh, great job genius 👏 That was *so* helpful" contain sarcasm meant to belittle and MUST be classified as 'SAFE: false'.

BE CAUTIOUS: When in doubt about the safety of a message, err on the side of caution and respond with 'SAFE: false'.

Otherwise, respond with 'SAFE: true'. Query: ${query}`;
      
      // Create payload for Ollama API
      const payload = {
        model: this.config.ollama.model,
        prompt: safetyPrompt,
        temperature: 0.0, // Use 0 for deterministic response
        top_p: 1.0,
        top_k: 1,
        repeat_penalty: this.config.ollama.repeat_penalty,
        num_predict: 20, // Limit response length
        stream: false
      };

      // Make direct API call to Ollama
      const response = await fetch(`${this.config.ollama.base_url}/api/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload)
      });

      const responseData = await response.json();
      const modelResponse = responseData.response.trim();

      if (this.verbose) {
        console.log('\n=== Safety Check Response ===');
        console.log(modelResponse);
      }

      // Check if response indicates the query is safe
      const isSafe = modelResponse === "SAFE: true";

      return {
        isSafe: isSafe,
        refusalMessage: !isSafe ? "I cannot assist with that type of request." : undefined
      };
    } catch (error) {
      console.error('Error in safety check:', error);
      // On error, err on the side of caution
      return { 
        isSafe: false, 
        refusalMessage: "I cannot assist with that type of request." 
      };
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