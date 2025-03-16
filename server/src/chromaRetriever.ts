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
    const verbose = process.env.VERBOSE === 'true';
    
    if (verbose) {
      console.log('\n=== ChromaRetriever Query ===');
      console.log('Query:', query);
      
      const queryEmbedding = await this.embeddings.generate([query]);
      console.log('Generated embedding, length:', queryEmbedding[0].length);
      
      const results = await this.collection.query({
        queryEmbeddings: queryEmbedding,
        nResults: 3,
        include: [
          "metadatas",
          "documents",
          "distances"
        ] as any,
      });

      console.log('\nChroma Results:');
      console.log('Metadatas:', JSON.stringify(results.metadatas, null, 2));
      console.log('Distances:', JSON.stringify(results.distances, null, 2));

      const documents: Document[] = [];
      
      if (results.metadatas && results.metadatas[0]) {
        for (let i = 0; i < results.metadatas[0].length; i++) {
          const metadata = results.metadatas[0][i];
          if (metadata) {
            const doc = new Document({
              pageContent: String(metadata.text || metadata.answer || ''),
              metadata: {
                ...metadata,
                distance: String(results.distances?.[0]?.[i] || '')
              }
            });
            console.log(`\nDocument ${i}:`, {
              content: doc.pageContent,
              metadata: doc.metadata
            });
            documents.push(doc);
          }
        }
      }

      const finalDocs = documents.length > 0
        ? documents
        : [new Document({ 
            pageContent: "GENERAL_QUERY_FLAG", 
            metadata: { isGeneral: true } 
          })];
      
      console.log('\nFinal documents count:', finalDocs.length);
      return finalDocs;
    }

    // Non-verbose path
    const queryEmbedding = await this.embeddings.generate([query]);
    const results = await this.collection.query({
      queryEmbeddings: queryEmbedding,
      nResults: 3,
      include: [
        "metadatas",
        "documents",
        "distances"
      ] as any,
    });

    const documents: Document[] = [];
    
    if (results.metadatas && results.metadatas[0]) {
      for (let i = 0; i < results.metadatas[0].length; i++) {
        const metadata = results.metadatas[0][i];
        if (metadata) {
          documents.push(new Document({
            pageContent: String(metadata.text || metadata.answer || ''),
            metadata: {
              ...metadata,
              distance: String(results.distances?.[0]?.[i] || '')
            }
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