import { Document } from '@langchain/core/documents';
import { RunnableSequence } from '@langchain/core/runnables';
import { ChromaRetriever } from './chromaRetriever';
import { AppConfig } from './types';

/**
 * Abstract base class for LLM clients (Ollama, vLLM, etc.)
 */
export abstract class BaseLanguageModelClient {
  protected config: AppConfig;
  protected retriever: ChromaRetriever;
  protected verbose: boolean;

  constructor(config: AppConfig, retriever: ChromaRetriever) {
    this.config = config;
    this.retriever = retriever;
    this.verbose = config.general?.verbose === 'true';
  }

  /**
   * Create a runnable chain for processing queries
   */
  abstract createChain(): Promise<RunnableSequence>;

  /**
   * Check if a query passes safety guardrails
   */
  abstract checkGuardrail(query: string): Promise<{ safe: boolean }>;

  /**
   * Format documents for prompt context
   */
  protected formatDocuments(docs: Document[]): string {
    if (this.verbose) {
      console.log('\n=== Format Documents ===');
      console.log('Number of documents:', docs.length);
      if (docs.length > 0) {
        console.log('First document content:', docs[0].pageContent);
        console.log('First document metadata:', JSON.stringify(docs[0].metadata, null, 2));
      }
    }
    
    // Check if we have any documents
    if (!docs.length) {
      console.error('No documents returned from retriever');
      return 'NO_RELEVANT_CONTEXT';
    }
    
    // Check if the document is a general flag
    if (docs[0]?.metadata?.isGeneral) {
      if (this.verbose) {
        console.log('General document flag detected');
      }
      return 'NO_RELEVANT_CONTEXT';
    }
    
    // Check for empty content
    if (!docs[0].pageContent || docs[0].pageContent.trim() === '') {
      console.error('Empty document content returned');
      return 'NO_RELEVANT_CONTEXT';
    }
    
    // If the document has metadata with an answer field, return just that answer
    if (docs[0]?.metadata?.answer) {
      if (this.verbose) {
        console.log('\nUsing Answer from Metadata:');
        console.log('Answer:', docs[0].metadata.answer);
        console.log('Distance:', docs[0].metadata.distance || 'N/A');
      }
      return docs[0].metadata.answer;
    }
    
    // Fallback to original behavior if no metadata
    if (this.verbose) {
      console.log('\nUsing Document Content (Fallback):');
      console.log('Content:', docs[0].pageContent);
    }
    return docs[0].pageContent;
  }
}