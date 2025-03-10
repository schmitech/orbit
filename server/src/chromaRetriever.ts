import { BaseRetriever } from "@langchain/core/retrievers";
import { Document } from "@langchain/core/documents";
import { Collection, IEmbeddingFunction } from 'chromadb';

export class ChromaRetriever extends BaseRetriever {
  // Important: This needs to be on the instance, not static!
  lc_namespace = ['langchain', 'retrievers', 'chroma'];
  
  private collection: Collection;
  private embeddings: IEmbeddingFunction;

  constructor(collection: Collection, embeddings: IEmbeddingFunction) {
    super();
    this.collection = collection;
    this.embeddings = embeddings;
  }

  async getRelevantDocuments(query: string): Promise<Document[]> {
    const queryEmbedding = await this.embeddings.generate([query]);
    
    const results = await this.collection.query({
      queryEmbeddings: queryEmbedding,
      nResults: 3,
      include: [
        "metadatas",
        "documents",
        "distances"
      ] as any, // Type assertion to bypass type checking
    });

    const documents: Document[] = [];
    
    if (results.metadatas && results.metadatas[0]) {
      for (const metadata of results.metadatas[0]) {
        if (metadata && metadata.text) {
          documents.push(new Document({
            pageContent: String(metadata.text),
            metadata: metadata || {}
          }));
        }
      }
    }

    return documents.length > 0
      ? documents
      : [new Document({ 
          pageContent: "GENERAL_QUERY_FLAG", 
          metadata: { isGeneral: true } 
        })];
  }
}