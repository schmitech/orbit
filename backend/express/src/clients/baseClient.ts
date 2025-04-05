import { Document } from 'langchain/document';
import { RunnableSequence } from '@langchain/core/runnables';
import { ChromaRetriever } from '../chromaRetriever';
import { AppConfig } from '../types';

/**
 * Abstract base class for LLM clients (Ollama, vLLM, etc.)
 */
export abstract class BaseLanguageModelClient {
  protected config: AppConfig;
  protected retriever: ChromaRetriever;
  protected verbose: boolean;
  protected confidenceThreshold: number;

  constructor(config: AppConfig, retriever: ChromaRetriever) {
    this.config = config;
    this.retriever = retriever;
    this.verbose = config.general?.verbose === 'true';
    this.confidenceThreshold = parseFloat(String(config.chroma.confidence_threshold));
  }

  /**
   * Create a runnable chain for processing queries
   */
  abstract createChain(): Promise<RunnableSequence>;

  /**
   * Format documents for prompt context
   */
  protected formatDocuments(docs: Document[]): string {
    if (docs.length === 0 || (docs.length === 1 && docs[0].metadata.isGeneral)) {
      return 'NO_RELEVANT_CONTEXT';
    }
    
    return docs.map((doc, i) => {
      const confidence = parseFloat(String(doc.metadata.distance || '0'));
      const confidenceStr = (1 - confidence).toFixed(2);
      
      // Format based on document type
      if (doc.metadata.question && doc.metadata.answer) {
        return `[${i+1}] Q: ${doc.metadata.question}\nA: ${doc.metadata.answer}\n(Confidence: ${confidenceStr})`;
      } else {
        return `[${i+1}] ${doc.pageContent}\n(Confidence: ${confidenceStr})`;
      }
    }).join('\n\n');
  }
}