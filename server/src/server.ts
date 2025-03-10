import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import { ChromaClient } from 'chromadb';
import { Ollama } from '@langchain/community/llms/ollama';
import { RunnableSequence } from '@langchain/core/runnables';
import { StringOutputParser } from '@langchain/core/output_parsers';
import { ChromaRetriever } from './chromaRetriever';
import { Document } from '@langchain/core/documents';
import { PromptTemplate } from "@langchain/core/prompts";
import { OllamaEmbeddings } from '@langchain/community/embeddings/ollama';
import { OllamaEmbeddingWrapper } from './ollamaEmbeddingWrapper';
import path from 'path';
import { fileURLToPath } from 'node:url';
import { questionAnswerWithHuggingFace } from './huggingface';
import fs from 'fs/promises';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Add this before dotenv.config()
const envVarsToReset = [
  'OLLAMA_BASE_URL',
  'OLLAMA_MODEL',
  'OLLAMA_EMBED_MODEL',
  'CHROMA_HOST',
  'CHROMA_COLLECTION',
  'CHROMA_PORT',
  'OLLAMA_NUM_PREDICT',
  'OLLAMA_NUM_CTX',
  'OLLAMA_NUM_THREADS',
  'OLLAMA_TOP_P',
  'OLLAMA_TOP_K',
  'OLLAMA_REPEAT_PENALTY',
  'HUGGINGFACE_API_KEY',
  'HUGGINGFACE_MODEL',
  'ELEVEN_LABS_API_KEY',
  'ELEVEN_LABS_VOICE_ID',
  'SYSTEM_TEMPLATE_PATH',
];

envVarsToReset.forEach(variable => {
  if (process.env[variable]) {
    console.log(`Clearing existing ${variable}`);
    delete process.env[variable];
  }
});

// Add after path resolution but before dotenv.config()
try {
  const envPath = path.resolve(__dirname, '../.env');
  console.log('Loading .env from:', envPath);
  
  // const envContents = await fs.readFile(envPath, 'utf-8');
  // console.log('.env file contents:\n', envContents);
} catch (error) {
  console.error('Error reading .env file:', error);
  process.exit(1);
}

// Then load .env
dotenv.config({ path: path.resolve(__dirname, '../.env') });

// Add this after the environment variables log
async function verifyOllamaConnection() {
  try {
    const response = await fetch(`${process.env.OLLAMA_BASE_URL}/api/tags`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    console.log('Ollama connection successful');
  } catch (error) {
    console.error('Ollama connection failed:', error);
    process.exit(1);
  }
}

// Add this before initializing the Ollama client
await verifyOllamaConnection();

const app = express();
app.use(cors());
app.use(express.json());

const port = 3000;

// Initialize ChromaDB with proper configuration
const client = new ChromaClient({
    path: `http://${process.env.CHROMA_HOST}:${process.env.CHROMA_PORT}`
  });

// Modify the template loading function
async function loadSystemTemplate(templatePath: string): Promise<string> {
  try {
    console.log('Loading system template from:', path.resolve(templatePath));
    const template = await fs.readFile(templatePath, 'utf-8');
    const systemMatch = template.match(/SYSTEM\s*"""\s*([\s\S]*?)\s*"""/);
    const systemPrompt = systemMatch ? systemMatch[1].trim() : '';
    
    console.log('Loaded system prompt (first 100 chars):', systemPrompt.substring(0, 100) + '...');
    return systemPrompt;
  } catch (error) {
    console.error('Error loading system template:', error);
    if (error instanceof Error && 'code' in error && error.code === 'ENOENT') {
      console.error('Template file not found at:', path.resolve(templatePath));
    }
    return '';
  }
}

// Modify Ollama initialization with additional parameters
const systemTemplate = await loadSystemTemplate(process.env.SYSTEM_TEMPLATE_PATH || './templates/default.txt');

const llm = new Ollama({
  baseUrl: process.env.OLLAMA_BASE_URL,
  model: process.env.OLLAMA_MODEL || 'llama3.2:3b',
  temperature: process.env.OLLAMA_TEMPERATURE ? parseFloat(process.env.OLLAMA_TEMPERATURE) : 0.1,
  system: systemTemplate,
  numPredict: process.env.OLLAMA_NUM_PREDICT ? parseInt(process.env.OLLAMA_NUM_PREDICT) : 1024,
  repeatPenalty: process.env.OLLAMA_REPEAT_PENALTY ? parseFloat(process.env.OLLAMA_REPEAT_PENALTY) : 1.0,
  numCtx: process.env.OLLAMA_NUM_CTX ? parseInt(process.env.OLLAMA_NUM_CTX) : 2048,
  numThread: process.env.OLLAMA_NUM_THREADS ? parseInt(process.env.OLLAMA_NUM_THREADS) : 8,
  top_p: process.env.OLLAMA_TOP_P ? parseFloat(process.env.OLLAMA_TOP_P) : 0.9,
  top_k: process.env.OLLAMA_TOP_K ? parseInt(process.env.OLLAMA_TOP_K) : 50,
  // stop: ['<|start_header_id|>', '<|end_header_id|>', '<|eot_id|>'],
  fetch: async (input: RequestInfo, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.url;
    console.log('\n--- Ollama API Call ---');
    console.log('Endpoint:', url.replace(process.env.OLLAMA_BASE_URL!, ''));
    
    if (init?.body) {
      const body = JSON.parse(init.body.toString());
      console.log('Payload:', {
        model: body.model,
        prompt: body.prompt,  // Log full prompt
        system: body.system,  // Log system prompt
        options: body.options
      });
    }
    
    const start = Date.now();
    const response = await fetch(input, init);
    console.log(`Duration: ${Date.now() - start}ms`);
    console.log('Status:', response.status);
    
    return response;
  }
} as any);

// Initialize Ollama embeddings instead of OpenAI
const embeddings = new OllamaEmbeddings({
  baseUrl: process.env.OLLAMA_BASE_URL,
  model: process.env.OLLAMA_EMBED_MODEL || 'bge-m3',
});

// Create the wrapper instance
const embeddingWrapper = new OllamaEmbeddingWrapper(embeddings);

// Use the wrapper in Chroma collection methods
let collection;
try {
  collection = await client.createCollection({
    name: process.env.CHROMA_COLLECTION || 'qa-chatbot',
    embeddingFunction: embeddingWrapper,
    metadata: { "hnsw:space": "cosine" }
  });
} catch (error) {
  collection = await client.getCollection({
    name: process.env.CHROMA_COLLECTION || 'qa-chatbot',
    embeddingFunction: embeddingWrapper
  });
}

const retriever = new ChromaRetriever(collection, embeddingWrapper);

// Helper function to format documents as string
const formatDocuments = (docs: Document[]): string => {
  const verbose = process.env.VERBOSE === 'true';
  
  if (verbose) {
    console.log('\n=== Retrieved Documents ===');
    console.log('Number of documents:', docs.length);
    console.log('First document:', docs[0]);
    console.log('First document metadata:', docs[0]?.metadata);
  }
  
  if (!docs.length || docs[0]?.metadata?.isGeneral) {
    if (verbose) {
      console.log('No relevant documents found or general document returned');
    }
    return 'NO_RELEVANT_CONTEXT';
  }
  
  // If the document has metadata with an answer field, return just that answer
  if (docs[0]?.metadata?.answer) {
    if (verbose) {
      console.log('\n=== Using Answer from Metadata ===');
      console.log('Answer:', docs[0].metadata.answer);
      console.log('Distance:', docs[0].metadata.distance || 'N/A');
    }
    return docs[0].metadata.answer;
  }
  
  // Fallback to original behavior if no metadata
  if (verbose) {
    console.log('\n=== Using Document Content (Fallback) ===');
    console.log('Content:', docs[0].pageContent);
  }
  return docs[0].pageContent;
};

// Add new type for backend selection
type Backend = 'ollama' | 'hf';

// Add command line argument parsing
const backend: Backend = process.argv[2] as Backend || 'ollama';
if (!['ollama', 'hf'].includes(backend)) {
  console.error('Invalid backend specified. Use either "ollama" or "hf"');
  process.exit(1);
}

console.log(`Using ${backend} backend`);

// Add this logging block after backend selection
console.log('Environment Variables:');
const commonVars = {
  CHROMA_HOST: process.env.CHROMA_HOST,
  CHROMA_PORT: process.env.CHROMA_PORT,
  CHROMA_COLLECTION: process.env.CHROMA_COLLECTION,
  SYSTEM_TEMPLATE_PATH: process.env.SYSTEM_TEMPLATE_PATH,
  VERBOSE: process.env.VERBOSE,
};

if (backend === 'ollama') {
  console.log({
    ...commonVars,
    OLLAMA_BASE_URL: process.env.OLLAMA_BASE_URL,
    OLLAMA_MODEL: process.env.OLLAMA_MODEL,
    OLLAMA_EMBED_MODEL: process.env.OLLAMA_EMBED_MODEL,
    OLLAMA_TEMPERATURE: process.env.OLLAMA_TEMPERATURE,
    OLLAMA_NUM_PREDICT: process.env.OLLAMA_NUM_PREDICT,
    OLLAMA_NUM_CTX: process.env.OLLAMA_NUM_CTX,
    OLLAMA_NUM_THREADS: process.env.OLLAMA_NUM_THREADS,
    OLLAMA_TOP_P: process.env.OLLAMA_TOP_P,
    OLLAMA_TOP_K: process.env.OLLAMA_TOP_K,
    OLLAMA_REPEAT_PENALTY: process.env.OLLAMA_REPEAT_PENALTY,
  });
} else {
  console.log({
    ...commonVars,
    HUGGINGFACE_MODEL: process.env.HUGGINGFACE_MODEL,
    // Masking sensitive data
    HUGGINGFACE_API_KEY: process.env.HUGGINGFACE_API_KEY ? '****' : undefined,
  });
}

// Modify the chain creation to add logging
const createChain = (backend: Backend) => {
  const verbose = process.env.VERBOSE === 'true';
  
  if (backend === 'ollama') {
    return RunnableSequence.from([
      async (input: { query: string }) => {
        if (verbose) {
          console.log('\n=== Starting Document Retrieval ===');
          console.log('Query:', input.query);
        }
        
        const docs = await retriever.getRelevantDocuments(input.query);
        if (verbose) {
          console.log('Retrieved documents count:', docs.length);
        }
        
        const context = formatDocuments(docs);
        if (verbose) {
          console.log('\n=== Final Context ===');
          console.log(context);
        }
        
        return {
          context,
          question: input.query,
          system: systemTemplate,
        };
      },
      PromptTemplate.fromTemplate(`SYSTEM: {system}

CONTEXT: {context}

USER QUESTION: {question}

ANSWER:`),
      async (input: string) => {
        if (verbose) {
          console.log('\n=== Final Prompt to Ollama ===\n', input);
        }
        return llm.invoke(input);
      },
      new StringOutputParser(),
    ]);
  } else {
    // HuggingFace QA chain
    return RunnableSequence.from([
      async (input: { query: string }) => {
        const docs = await retriever.getRelevantDocuments(input.query);
        const context = formatDocuments(docs);
        
        if (context === 'NO_RELEVANT_CONTEXT') {
          return {
            answer: "I'm sorry, but I don't have enough relevant information to answer your question accurately.",
          };
        }

        const qaResult = await questionAnswerWithHuggingFace(context, input.query);
        
        // If confidence is too low, fall back to Ollama
        if (qaResult.score < 0.1) {
          return {
            context,
            question: input.query,
            system: systemTemplate,
            useOllama: true,
          };
        }

        return {
          answer: qaResult.answer,
          context,
          score: qaResult.score,
        };
      },
      async (input: any) => {
        if (input.useOllama) {
          const prompt = PromptTemplate.fromTemplate(`SYSTEM: {system}

CONTEXT: {context}

USER QUESTION: {question}

ANSWER:`);
          return prompt.format(input);
        }
        
        return `Based on the provided information (confidence: ${Math.round(input.score * 100)}%), ${input.answer}`;
      },
      input => input.useOllama ? llm : new StringOutputParser(),
      new StringOutputParser(),
    ]);
  }
};

const chain = createChain(backend);

app.post('/chat', async (req, res) => {
  const { message, voiceEnabled } = req.body;

  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');

  try {
    let textBuffer = '';
    let isFirstChunk = true;
    
    const stream = await chain.stream({ query: message });
    
    for await (const chunk of stream) {
      if (chunk) {
        textBuffer += chunk;
        res.write(JSON.stringify({ type: 'text', content: chunk }) + '\n');

        // Start voice generation earlier with smaller first chunk
        if (voiceEnabled && isFirstChunk && textBuffer.length >= 50) {  // Reduced from 100 to 50
          const currentText = textBuffer;
          textBuffer = '';
          isFirstChunk = false;

          // Reduced initial delay
          await new Promise(resolve => setTimeout(resolve, 300));  // Reduced from 1000 to 300
          try {
            await generateAudioChunk(currentText, res);
          } catch (error) {
            console.error('First chunk audio generation failed:', error);
          }
        }
        // Process subsequent chunks more frequently
        else if (voiceEnabled && !isFirstChunk && (
          (textBuffer.match(/[.!?]\s*$/) && textBuffer.length >= 30) ||  // Reduced from 50 to 30
          textBuffer.length >= 100  // Reduced from 150 to 100
        )) {
          const currentText = textBuffer;
          textBuffer = '';

          // Reduced delay between chunks
          await new Promise(resolve => setTimeout(resolve, 200));  // Reduced from 800 to 200
          try {
            await generateAudioChunk(currentText, res);
          } catch (error) {
            console.error('Audio generation failed:', error);
          }
        }
      }
    }
    
    // Handle any remaining text with minimal delay
    if (voiceEnabled && textBuffer.trim()) {
      await new Promise(resolve => setTimeout(resolve, 100));  // Reduced from 800 to 100
      try {
        await generateAudioChunk(textBuffer.trim(), res, true);
      } catch (error) {
        console.error('Final chunk audio generation failed:', error);
      }
    }
    
    res.end();
  } catch (error) {
    console.error('Error:', error);
    res.write(JSON.stringify({ type: 'text', content: 'An error occurred while processing your request.' }) + '\n');
    res.end();
  }
});

async function generateAudioChunk(text: string, res: any, isFinal: boolean = false) {
  console.log('Generating audio for:', text);

  const response = await fetch(
    `https://api.elevenlabs.io/v1/text-to-speech/${process.env.ELEVEN_LABS_VOICE_ID}/stream`,
    {
      method: 'POST',
      headers: {
        'Accept': 'audio/mpeg',
        'Content-Type': 'application/json',
        'xi-api-key': process.env.ELEVEN_LABS_API_KEY || '',
      },
      body: JSON.stringify({
        text,
        model_id: 'eleven_multilingual_v1',
        voice_settings: {
          stability: 0.5,              // Reduced for more natural variation
          similarity_boost: 0.6,       // Reduced for more expressive speech
          style: 0.35,                 // Increased for more casual style
          speaking_rate: 1.1,          // Slightly faster for conversational feel
          use_speaker_boost: true      // Enhanced clarity for voice calls
        },
      }),
    }
  );

  if (!response.ok) {
    throw new Error(`Audio generation failed: ${response.status} ${response.statusText}`);
  }
    
  const audioBuffer = await response.arrayBuffer();
  const base64Audio = Buffer.from(audioBuffer).toString('base64');
    
  console.log('Audio generated successfully, length:', base64Audio.length);

  res.write(JSON.stringify({
    type: 'audio',
    content: base64Audio,
    isFinal,
  }) + '\n');
}

app.listen(port, () => {
  console.log(`Server running at http://localhost:${port}`);
});