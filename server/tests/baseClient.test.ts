import { BaseLanguageModelClient } from '../src/clients/baseClient';
import { Document } from '@langchain/core/documents';
import { RunnableSequence } from '@langchain/core/runnables';

// Create a mock implementation of the abstract class for testing
class MockLanguageModelClient extends BaseLanguageModelClient {
  async createChain(): Promise<RunnableSequence> {
    return {} as RunnableSequence;
  }

  async checkGuardrail(query: string): Promise<{ safe: boolean }> {
    return { safe: query.toLowerCase().indexOf('unsafe') === -1 };
  }

  // Expose protected method for testing
  public testFormatDocuments(docs: Document[]): string {
    return this.formatDocuments(docs);
  }
}

describe('BaseLanguageModelClient', () => {
  let client: MockLanguageModelClient;
  const mockConfig = {
    general: { verbose: 'true' },
    system: { prompt: 'test prompt' }
  } as any;
  const mockRetriever = {} as any;
  const mockConsoleLog = jest.spyOn(console, 'log').mockImplementation();
  const mockConsoleError = jest.spyOn(console, 'error').mockImplementation();

  beforeEach(() => {
    jest.clearAllMocks();
    client = new MockLanguageModelClient(mockConfig, mockRetriever);
  });

  afterAll(() => {
    mockConsoleLog.mockRestore();
    mockConsoleError.mockRestore();
  });

  describe('formatDocuments', () => {
    it('should return NO_RELEVANT_CONTEXT when no documents are provided', () => {
      const result = client.testFormatDocuments([]);
      
      expect(result).toBe('NO_RELEVANT_CONTEXT');
      expect(mockConsoleError).toHaveBeenCalledWith('No documents returned from retriever');
    });

    it('should return NO_RELEVANT_CONTEXT for general flag documents', () => {
      const docs = [
        new Document({
          pageContent: 'Some content',
          metadata: { isGeneral: true }
        })
      ];
      
      const result = client.testFormatDocuments(docs);
      
      expect(result).toBe('NO_RELEVANT_CONTEXT');
      expect(mockConsoleLog).toHaveBeenCalledWith('General document flag detected');
    });

    it('should return NO_RELEVANT_CONTEXT for empty content', () => {
      const docs = [
        new Document({
          pageContent: '',
          metadata: {}
        })
      ];
      
      const result = client.testFormatDocuments(docs);
      
      expect(result).toBe('NO_RELEVANT_CONTEXT');
      expect(mockConsoleError).toHaveBeenCalledWith('Empty document content returned');
    });

    it('should return answer from metadata if available', () => {
      const docs = [
        new Document({
          pageContent: 'Some content',
          metadata: { answer: 'This is the answer', distance: '0.5' }
        })
      ];
      
      const result = client.testFormatDocuments(docs);
      
      expect(result).toBe('This is the answer');
      expect(mockConsoleLog).toHaveBeenCalledWith('\nUsing Answer from Metadata:');
    });

    it('should return page content as fallback', () => {
      const docs = [
        new Document({
          pageContent: 'This is the page content',
          metadata: {}
        })
      ];
      
      const result = client.testFormatDocuments(docs);
      
      expect(result).toBe('This is the page content');
      expect(mockConsoleLog).toHaveBeenCalledWith('\nUsing Document Content (Fallback):');
    });
  });
});